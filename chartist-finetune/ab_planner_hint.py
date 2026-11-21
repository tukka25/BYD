"""Does telling the chartist which chart to draw actually help?

`chartist._task_description()` deliberately sends the user's raw question and
nothing else, so the planner's `visualization_type` never reaches the model. The
stated reason is distribution: the fine-tune saw 1,926 rows whose Task line was a
bare natural question, and generated metadata would be a prompt shape it was
never trained on. That is a hypothesis, not a measurement. This measures it.

Three arms over the SAME frozen rows, one model load, greedy decoding, paired:

  A  control     Task: <question>
  B  inline      Task: <question> Show it as a <type> chart.
  C  directive   Task: <question>\\n\\nChart type: <type>

The hint is the ORACLE type -- the row's own `chart_bucket` -- so this measures
the ceiling. A real planner is wrong some of the time, so whatever an oracle hint
buys is the most a wired planner could ever buy. If the oracle does not help,
nothing downstream of the planner will.

Scoring is identical to evaluate.py: execution decides renders, TRACE_TYPES plus
the area tie-break decides right shape. Because the arms are paired on the same
rows, the verdict is McNemar's exact test on the rows that disagree, not an
unpaired interval -- at n=300 that is the difference between measuring a 6-point
move and being unable to see it.

    .venv/bin/python ab_planner_hint.py --limit 12     # smoke, ~2 min
    .venv/bin/python ab_planner_hint.py                # full 300 x 3
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

import chart_types
from contract import CHARTIST_MAX_TOKENS
from evaluate import SYSTEM_FALLBACK, strip_fence
from executor import run_candidates

# What to call each bucket in a hint. These are the words a planner would emit,
# not the Plotly trace names. Two forms, because a sentence and a metadata field
# read differently: "Show it as an area chart." vs "Chart type: area". Writing
# "as a area chart" would make arm B a test of broken English, not of hinting.
#
# The treemap bucket admits treemap, funnel, waterfall AND sunburst, so no
# oracle can name one type. treemap is 103 of its 105 training targets, so it is
# the hint a planner trained on this data would give -- and it is wrong for
# roughly three quarters of that bucket's test rows. Read that one row of the
# results knowing the oracle is not an oracle there.
PHRASE = {
    "bar": "a bar chart",
    "line": "a line chart",
    "grouped_or_stacked_bar": "a grouped bar chart",
    "scatter": "a scatter plot",
    "pie_or_donut": "a pie chart",
    "area": "an area chart",
    "histogram": "a histogram",
    "box": "a box plot",
    "heatmap": "a heatmap",
    "time_series": "a time series line chart",
    "treemap_funnel_waterfall": "a treemap",
    "gauge_or_indicator": "a single-number KPI indicator",
}
LABEL = {
    "bar": "bar",
    "line": "line",
    "grouped_or_stacked_bar": "grouped bar",
    "scatter": "scatter",
    "pie_or_donut": "pie",
    "area": "area",
    "histogram": "histogram",
    "box": "box",
    "heatmap": "heatmap",
    "time_series": "time series line",
    "treemap_funnel_waterfall": "treemap",
    "gauge_or_indicator": "KPI indicator",
}

ARMS = ("A_control", "B_inline", "C_directive")


def build_prompt(row: dict, arm: str) -> str:
    """Rewrite the Task line only. Schema block is untouched and identical."""
    prompt = row["prompt"]
    if arm == "A_control":
        return prompt
    bucket = row["chart_bucket"]
    if bucket not in PHRASE:
        return prompt
    head, sep, tail = prompt.partition("\n\nDataFrame `df` schema:")
    if not sep:  # shape changed; do not guess, leave the row as control
        return prompt
    question = head[len("Task: ") :] if head.startswith("Task: ") else head
    question = question.rstrip()
    if arm == "B_inline":
        # A second sentence needs the first one to end. Most questions do not.
        if question and question[-1] not in ".?!":
            question += "."
        head = f"Task: {question} Show it as {PHRASE[bucket]}."
    else:
        head = f"Task: {question}\n\nChart type: {LABEL[bucket]}"
    return head + sep + tail


def is_right_shape(bucket: str, figure_type: str | None, code: str) -> bool:
    """Same rule evaluate.py uses, so numbers stay comparable to the report."""
    allowed = chart_types.TRACE_TYPES.get(bucket, set())
    right = bool(allowed) and figure_type in allowed
    if right and bucket == "area":
        right = chart_types.is_area_figure(code)
    elif right and bucket in ("line", "scatter", "time_series"):
        right = not chart_types.is_area_figure(code)
    return right


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact p for paired binary outcomes.

    b = arm1 wrong / arm2 right, c = arm1 right / arm2 wrong. Rows where the two
    arms agree carry no information about which is better, so they are excluded;
    that is the whole point of pairing.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/qwen3.5-9b-4bit")
    ap.add_argument("--adapter-path", default="runs/adapters-mlx")
    ap.add_argument("--testset", default="data/testset.jsonl")
    ap.add_argument("--out", default="data/ab_planner_hint.json")
    ap.add_argument("--limit", type=int, default=None)
    # The first full run (data/ab_planner_hint.json, 2026-11-21) used 800, the
    # old eval default; every arm in a run shares one cap, so its arms are
    # comparable with each other either way.
    ap.add_argument("--max-tokens", type=int, default=CHARTIST_MAX_TOKENS)
    ap.add_argument("--batch-size", type=int, default=8)
    args = ap.parse_args()

    rows = [
        json.loads(l)
        for l in Path(args.testset).read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    if args.limit:
        rows = rows[: args.limit]
    print(f"{len(rows)} rows x {len(ARMS)} arms = {len(rows)*len(ARMS)} generations")

    from mlx_lm import batch_generate, load
    from mlx_lm.sample_utils import make_sampler

    adapter = None if args.adapter_path in ("none", "") else args.adapter_path
    print(f"loading {args.model}" + (f" + {adapter}" if adapter else " (base)"))
    model, tokenizer = load(args.model, adapter_path=adapter)
    sampler = make_sampler(temp=0.0)

    def tok(text: str) -> list[int]:
        ids = tokenizer.apply_chat_template(
            [
                {"role": "system", "content": SYSTEM_FALLBACK},
                {"role": "user", "content": text},
            ],
            tokenize=True,
            add_generation_prompt=True,
        )
        if isinstance(ids, dict):
            ids = ids.get("input_ids", [])
        if ids and isinstance(ids[0], (list, tuple)):
            ids = ids[0]
        return list(ids)

    results: dict[str, list] = {}
    started = time.time()
    total = len(rows) * len(ARMS)
    done_all = 0

    for arm in ARMS:
        prompts = [tok(build_prompt(row, arm)) for row in rows]
        if arm != "A_control":
            changed = sum(
                1 for r in rows if build_prompt(r, arm) != r["prompt"]
            )
            print(f"\n{arm}: {changed}/{len(rows)} prompts carry a hint")
        else:
            print(f"\n{arm}: prompts unchanged")

        gens: list[str] = []
        for start in range(0, len(prompts), args.batch_size):
            resp = batch_generate(
                model,
                tokenizer,
                prompts[start : start + args.batch_size],
                max_tokens=args.max_tokens,
                sampler=sampler,
                verbose=False,
            )
            gens.extend(resp.texts)
            done_all += len(resp.texts)
            rate = done_all / max(1e-9, time.time() - started)
            print(
                f"  {done_all}/{total}  ({rate*60:.1f}/min, "
                f"eta {(total-done_all)/max(1e-9,rate)/60:.1f} min)",
                flush=True,
            )

        codes = [strip_fence(t) for t in gens]
        print(f"  scoring {len(codes)} candidates by execution...")
        verdicts = run_candidates(
            [(c, r["fixture_csv"]) for c, r in zip(codes, rows)], max_workers=8
        )
        results[arm] = [
            {
                "test_id": r["test_id"],
                "bucket": r["chart_bucket"],
                "hard_case": r["hard_case"],
                "ok": bool(v.ok),
                "right_shape": bool(v.ok)
                and is_right_shape(r["chart_bucket"], v.figure_type, c),
                "figure_type": v.figure_type,
                "failure_kind": v.failure_kind,
                "error": (v.error or "")[:200],
                "code": c[:600],
            }
            for r, c, v in zip(rows, codes, verdicts)
        ]

    # ---- report ----
    n = len(rows)
    summary = {}
    for arm in ARMS:
        rs = results[arm]
        summary[arm] = {
            "n": n,
            "render_rate": sum(r["ok"] for r in rs) / n,
            "right_shape_rate": sum(r["right_shape"] for r in rs) / n,
            "failure_kinds": dict(
                Counter(r["failure_kind"] for r in rs if not r["ok"])
            ),
        }

    per_bucket: dict[str, dict] = defaultdict(dict)
    for arm in ARMS:
        agg: dict[str, Counter] = defaultdict(Counter)
        for r in results[arm]:
            agg[r["bucket"]]["n"] += 1
            agg[r["bucket"]]["ok"] += r["ok"]
            agg[r["bucket"]]["shape"] += r["right_shape"]
        for bucket, c in agg.items():
            per_bucket[bucket][arm] = {
                "n": c["n"],
                "render_rate": c["ok"] / c["n"],
                "right_shape_rate": c["shape"] / c["n"],
            }

    paired = {}
    for metric in ("ok", "right_shape"):
        for other in ARMS[1:]:
            a = {r["test_id"]: r[metric] for r in results["A_control"]}
            b = {r["test_id"]: r[metric] for r in results[other]}
            gained = [t for t in a if not a[t] and b[t]]
            lost = [t for t in a if a[t] and not b[t]]
            paired[f"{metric}:A_vs_{other}"] = {
                "gained": len(gained),
                "lost": len(lost),
                "net": len(gained) - len(lost),
                "p_value": mcnemar_exact(len(gained), len(lost)),
                "gained_ids": gained[:40],
                "lost_ids": lost[:40],
            }

    report = {
        "model": args.model,
        "adapter": args.adapter_path,
        "max_tokens": args.max_tokens,
        "n": n,
        "minutes": (time.time() - started) / 60,
        "summary": summary,
        "per_bucket": per_bucket,
        "paired": paired,
        "rows": results,
    }
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n{'arm':14s} {'render':>9s} {'shape':>9s}")
    for arm in ARMS:
        s = summary[arm]
        print(
            f"{arm:14s} {s['render_rate']*100:8.1f}% {s['right_shape_rate']*100:8.1f}%"
        )
    print("\npaired, vs the control:")
    for key, p in paired.items():
        print(
            f"  {key:28s} +{p['gained']:3d} / -{p['lost']:3d}  "
            f"net {p['net']:+3d}   p={p['p_value']:.4f}"
        )
    print(f"\nwrote {args.out}  ({report['minutes']:.1f} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
