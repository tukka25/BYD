#!/usr/bin/env python3
"""Score a CUDA LoRA adapter on the frozen 300 by executing everything it writes.

The CUDA counterpart of evaluate.py (which is MLX-only and cannot run on a pod).
It deliberately imports the SAME executor, chart_types and contract modules, so
the oracle, the chart-type quota and the system prompt are identical across both
— only the generation backend differs.

Two things here are specific to this model and easy to get wrong:

* Qwen3.5 is a thinking model. Generation begins after "<think>\\n", so the text
  it returns starts "\\n</think>\\n\\n" before any code. That prefix is stripped
  before scoring; left in, every single candidate would be a SyntaxError and the
  render rate would read 0% for a model that is working perfectly.
* Batched decoder-only generation needs LEFT padding. With the tokenizer's
  default right padding, short prompts end with pad tokens and the model
  continues from padding instead of from the prompt — producing fluent garbage
  rather than an error, which is the worst kind of bug to have in an eval.

    python3 evaluate_cuda.py --label base    --adapter-path none
    python3 evaluate_cuda.py --label lora-v1 --adapter-path /workspace/outputs/lora-v1
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

import chart_types
from executor import run_candidates

try:
    from contract import CHARTIST_SYSTEM_PROMPT as SYSTEM_FALLBACK
except Exception:  # pragma: no cover
    SYSTEM_FALLBACK = ""

THINK_PREFIX = re.compile(r"^.*?</think>\s*", re.DOTALL)
FENCE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def clean(text: str) -> str:
    """Strip the reasoning block and any markdown fence, leaving bare Python.

    The fence is a formatting artefact rather than a modelling failure, and the
    backend's own sanitizer strips it too, so removing it measures what the app
    would actually see.
    """
    if "</think>" in text:
        text = THINK_PREFIX.sub("", text, count=1)
    match = FENCE.search(text)
    if match:
        text = match.group(1)
    return text.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen3.5-9B")
    ap.add_argument("--adapter-path", default="none", help='path, or "none" for the base model')
    ap.add_argument("--label", required=True)
    ap.add_argument("--testset", default="data/testset.jsonl")
    ap.add_argument("--out", default="data/eval_report.json")
    ap.add_argument("--limit", type=int, default=None, help="smoke tests only; full 300 for real numbers")
    # Must equal CHARTIST_MAX_TOKENS in backend/.../chartist_contract.py. Written
    # as a literal only because the backend is not on the pod to import from.
    # lora-v1's recorded 91.3% was measured at the old default of 800.
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument("--batch-size", type=int, default=16)
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.testset).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        rows = rows[: args.limit]
        print("  WARNING --limit is set; at n<300 the base-vs-tuned gap is not reliably measurable")
    print(f"{args.label}: {len(rows)} test rows", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(args.base)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"  # see the module docstring; not optional

    model = AutoModelForCausalLM.from_pretrained(args.base, dtype=torch.bfloat16, device_map="cuda")
    if args.adapter_path not in ("none", "None", ""):
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, args.adapter_path)
        print(f"  adapter loaded from {args.adapter_path}", flush=True)
    else:
        print("  base model, no adapter", flush=True)
    model.eval()

    prompts = [
        tokenizer.apply_chat_template(
            [
                {"role": "system", "content": row.get("system") or SYSTEM_FALLBACK},
                {"role": "user", "content": row["prompt"]},
            ],
            tokenize=False,
            add_generation_prompt=True,
        )
        for row in rows
    ]

    generations: list[str] = []
    started = time.time()
    for start in range(0, len(prompts), args.batch_size):
        chunk = prompts[start : start + args.batch_size]
        batch = tokenizer(chunk, return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
        with torch.no_grad():
            out = model.generate(
                **batch,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,  # greedy: two runs of one adapter must agree
                pad_token_id=tokenizer.pad_token_id,
            )
        new = out[:, batch["input_ids"].shape[1] :]
        generations.extend(tokenizer.batch_decode(new, skip_special_tokens=True))
        done = min(start + args.batch_size, len(prompts))
        rate = done / max(1e-9, time.time() - started)
        print(f"  generated {done}/{len(prompts)} ({rate*60:.1f}/min, eta {(len(prompts)-done)/max(1e-9,rate)/60:.1f} min)", flush=True)

    codes = [clean(t) for t in generations]
    print(f"  scoring {len(codes)} candidates by execution...", flush=True)
    verdicts = run_candidates([(c, r["fixture_csv"]) for c, r in zip(codes, rows)], max_workers=8)

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
            # without this tie-break.
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
        chart_types.QUOTA.get(b, 0.0) * (c["renders"] / c["n"]) for b, c in per_bucket.items() if c["n"]
    )
    covered = sum(chart_types.QUOTA.get(b, 0.0) for b in per_bucket)

    report = {
        "label": args.label,
        "base": args.base,
        "adapter_path": args.adapter_path,
        "n": totals["n"],
        "render_rate": round(totals["renders"] / n, 4),
        "render_rate_quota_weighted": round(weighted / covered, 4) if covered else None,
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
        delta = (report["render_rate"] - existing["base"]["render_rate"]) * 100
        print(f"\nbase {existing['base']['render_rate']:.1%} -> {args.label} {report['render_rate']:.1%}  delta {delta:+.1f} pp")
        print("  at n=300 per arm, a gap under ~11 pp is not distinguishable from noise")
    return 0


if __name__ == "__main__":
    sys.exit(main())
