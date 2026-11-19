#!/usr/bin/env python3
"""Score a model on the frozen 300-row test set by executing everything it writes.

Loss does not tell you whether the backend will accept a chart. This does: every
generated script is run against its schema's real CSV through the same oracle
that gated the training data, so the headline number is the share of prompts that
produce a figure the app could actually render.

Design notes that matter:

* The model is loaded ONCE and generation is batched via mlx_lm.batch_generate.
  Shelling out to mlx_lm.generate per row would reload ~6 GB three hundred times.
* Decoding is greedy (temp 0.0) so two runs of the same adapter agree.
* Scoring uses executor.run_candidates, which validates in parallel.
* Two render rates are reported. The plain one is the share of the 300 that
  rendered -- correct for comparing base against tuned, since both arms see the
  same rows. The QUOTA-WEIGHTED one re-weights per chart bucket to the production
  mix, because the frozen set deliberately over-samples small buckets (a floor of
  15 rows each puts gauge_or_indicator at 5.7% against a 2% quota). Quote the
  weighted number when asking "what would users see".
* Hallucinated columns are counted from failure_kind, i.e. observed at execution,
  not from a static scan. The static check was dropped as a gate because it
  rejected every chart that derives its own columns.

    .venv/bin/python evaluate.py --label base     --adapter-path none
    .venv/bin/python evaluate.py --label lora-v1  --adapter-path runs/lora-v1/adapters
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import chart_types
from executor import run_candidates

FENCE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def strip_fence(text: str) -> str:
    """Models wrap code in markdown even when told not to. Unwrap before scoring.

    The contract forbids fences, but the fence is a formatting artefact rather
    than a modelling failure, and penalising it would conflate two different
    things. The backend's own sanitizer strips them too, so stripping here
    measures what the app would actually see.
    """
    match = FENCE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/qwen3.5-9b-4bit")
    parser.add_argument("--adapter-path", default="none", help='path, or "none" for the base model')
    parser.add_argument("--label", required=True, help="key under which results are stored")
    parser.add_argument("--testset", default="data/testset.jsonl")
    parser.add_argument("--out", default="data/eval_report.json")
    parser.add_argument("--limit", type=int, default=None, help="for smoke tests only; full 300 for real numbers")
    parser.add_argument("--max-tokens", type=int, default=800)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    rows = [json.loads(l) for l in Path(args.testset).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        rows = rows[: args.limit]
    print(f"{args.label}: {len(rows)} test rows")
    if args.limit:
        print("  WARNING --limit is set; at n<300 the base-vs-tuned gap is not reliably measurable")

    from mlx_lm import batch_generate, load
    from mlx_lm.sample_utils import make_sampler

    adapter = None if args.adapter_path in ("none", "None", "") else args.adapter_path
    print(f"  loading {args.model}" + (f" + adapter {adapter}" if adapter else " (base, no adapter)"))
    model, tokenizer = load(args.model, adapter_path=adapter)

    # Pre-tokenise: batch_generate takes token ids, not strings.
    prompts: list[list[int]] = []
    for row in rows:
        messages = [
            {"role": "system", "content": row.get("system") or SYSTEM_FALLBACK},
            {"role": "user", "content": row["prompt"]},
        ]
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        if isinstance(ids, dict):
            ids = ids.get("input_ids", [])
        if ids and isinstance(ids[0], (list, tuple)):
            ids = ids[0]
        prompts.append(list(ids))

    sampler = make_sampler(temp=0.0)  # greedy: two runs of one adapter must agree

    generations: list[str] = []
    started = time.time()
    for start in range(0, len(prompts), args.batch_size):
        chunk = prompts[start : start + args.batch_size]
        response = batch_generate(
            model, tokenizer, chunk, max_tokens=args.max_tokens, sampler=sampler, verbose=False
        )
        generations.extend(response.texts)
        done = min(start + args.batch_size, len(prompts))
        rate = done / max(1e-9, time.time() - started)
        eta = (len(prompts) - done) / max(1e-9, rate)
        print(f"  generated {done}/{len(prompts)}  ({rate*60:.1f}/min, eta {eta/60:.1f} min)", flush=True)

    codes = [strip_fence(text) for text in generations]
    print(f"  scoring {len(codes)} candidates by execution...")
    verdicts = run_candidates([(code, row["fixture_csv"]) for code, row in zip(codes, rows)], max_workers=8)

    totals: Counter[str] = Counter()
    per_bucket: dict[str, Counter] = defaultdict(Counter)
    per_hard: dict[str, Counter] = defaultdict(Counter)
    failures = []

    for row, code, verdict in zip(rows, codes, verdicts):
        bucket = row["chart_bucket"]
        hard = row["hard_case"] or "easy"
        totals["n"] += 1
        per_bucket[bucket]["n"] += 1
        per_hard[hard]["n"] += 1

        if verdict.ok:
            totals["renders"] += 1
            per_bucket[bucket]["renders"] += 1
            per_hard[hard]["renders"] += 1

            allowed = chart_types.TRACE_TYPES.get(bucket, set())
            right = bool(allowed) and verdict.figure_type in allowed
            # line/scatter/area/time_series all permit a scatter trace, so a
            # scatter-family answer would score "correct" on 107 of 300 rows
            # without this. is_area_figure breaks the tie the data supports.
            if right and bucket == "area":
                right = chart_types.is_area_figure(code)
            elif right and bucket in ("line", "scatter", "time_series"):
                right = not chart_types.is_area_figure(code)
            if right:
                totals["right_shape"] += 1
                per_bucket[bucket]["right_shape"] += 1
        else:
            kind = verdict.failure_kind or (verdict.violations[0] if verdict.violations else "unknown")
            totals[f"fail:{kind}"] += 1
            failures.append(
                {
                    "test_id": row["test_id"],
                    "bucket": bucket,
                    "hard_case": row["hard_case"],
                    "failure_kind": verdict.failure_kind,
                    "violations": verdict.violations,
                    "error": (verdict.error or "")[:300],
                    "code": code[:500],
                }
            )

    n = max(1, totals["n"])
    # Re-weight to the production chart mix; the frozen set over-samples small buckets.
    weighted = sum(
        chart_types.QUOTA.get(b, 0.0) * (c["renders"] / c["n"])
        for b, c in per_bucket.items()
        if c["n"]
    )
    quota_covered = sum(chart_types.QUOTA.get(b, 0.0) for b in per_bucket)

    report = {
        "label": args.label,
        "model": args.model,
        "adapter_path": args.adapter_path,
        "n": totals["n"],
        "render_rate": round(totals["renders"] / n, 4),
        "render_rate_quota_weighted": round(weighted / quota_covered, 4) if quota_covered else None,
        "right_shape_rate": round(totals["right_shape"] / n, 4),
        "hallucinated_column_rate": round(totals["fail:hallucinated_column"] / n, 4),
        "failure_kinds": {k.split(":", 1)[1]: v for k, v in sorted(totals.items()) if k.startswith("fail:")},
        "by_bucket": {
            b: {
                "n": c["n"],
                "render_rate": round(c["renders"] / max(1, c["n"]), 3),
                "right_shape_rate": round(c["right_shape"] / max(1, c["n"]), 3),
            }
            for b, c in sorted(per_bucket.items())
        },
        "by_hard_case": {
            h: {"n": c["n"], "render_rate": round(c["renders"] / max(1, c["n"]), 3)}
            for h, c in sorted(per_hard.items())
        },
        "generation_minutes": round((time.time() - started) / 60, 1),
        "failures": failures[:25],
    }

    out = Path(args.out)
    existing = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    existing[args.label] = report
    out.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    print(json.dumps({k: v for k, v in report.items() if k != "failures"}, indent=2))
    print(f"\nwrote {out} under key {args.label!r}")

    if "base" in existing and args.label != "base":
        base = existing["base"]["render_rate"]
        tuned = report["render_rate"]
        delta = (tuned - base) * 100
        print(f"\nbase {base:.1%} -> {args.label} {tuned:.1%}   delta {delta:+.1f} pp")
        # 95% CI half-width on a difference of proportions at n=300 each.
        print("  at n=300 per arm, a gap under ~11 pp is not distinguishable from noise")
    return 0


SYSTEM_FALLBACK = ""
try:
    from contract import CHARTIST_SYSTEM_PROMPT as SYSTEM_FALLBACK  # noqa: E402
except Exception:
    pass


if __name__ == "__main__":
    sys.exit(main())
