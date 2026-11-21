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

    .venv/bin/python ab_planner_hint.py --limit 12                 # smoke
    .venv/bin/python ab_planner_hint.py                            # full 300 x 3
    .venv/bin/python ab_planner_hint.py --arms A_control,B_inline \
        --focus area,heatmap,gauge_or_indicator,treemap_funnel_waterfall \
        --others-per-bucket 4                                      # focused, ~25 min
    .venv/bin/python ab_planner_hint.py --summarize-only           # report from saved rows

Rows are saved as they are scored (<out>.rows.jsonl), and the same command
resumes a stopped run.
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

# Not a prompt variant: the control prompt on the BASE weights (every lora_b
# zeroed in place, so the LoRA branch adds nothing) with the chat template's
# thinking switched off. Base Qwen3.5 otherwise opens every answer with a
# "Thinking Process:" essay -- 267 of its 277 failures were that prose -- and
# the template's enable_thinking=False pre-closes the think block, which is
# also the shape every fine-tuning target was rendered in. So this arm asks how
# much of the fine-tune's gain a template flag already gets.
PROMPT_STYLE = {
    "A_control": "control",
    "B_inline": "inline",
    "C_directive": "directive",
    "A_base_nothink": "control",
}
BASE_NOTHINK = {"A_base_nothink"}


def build_prompt(row: dict, arm: str) -> str:
    """Rewrite the Task line only. Schema block is untouched and identical."""
    prompt = row["prompt"]
    style = PROMPT_STYLE.get(arm, "control")
    if style == "control":
        return prompt
    bucket = row["chart_bucket"]
    if bucket not in PHRASE:
        return prompt
    head, sep, tail = prompt.partition("\n\nDataFrame `df` schema:")
    if not sep:  # shape changed; do not guess, leave the row as control
        return prompt
    question = head[len("Task: ") :] if head.startswith("Task: ") else head
    question = question.rstrip()
    if style == "inline":
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


def select_rows(
    rows: list[dict], focus: str = "", others_per_bucket: int = 0, limit: int | None = None
) -> list[dict]:
    """The sample, chosen the same way every time so separate scripts pair up.

    `focus` buckets are taken whole; every other bucket contributes its first
    `others_per_bucket` rows, as a check that a hint does not break what already
    works. The frozen set's own order already mixes buckets, so a run stopped
    part way still spans them.
    """
    if focus:
        keep = {b.strip() for b in focus.split(",") if b.strip()}
        seen: Counter = Counter()
        picked = []
        for r in rows:
            b = r["chart_bucket"]
            if b in keep:
                picked.append(r)
            elif seen[b] < others_per_bucket:
                picked.append(r)
                seen[b] += 1
        rows = picked
    return rows[:limit] if limit else rows


def record(arm: str, row: dict, code: str, verdict, max_tokens: int) -> dict:
    return {
        "arm": arm,
        "test_id": row["test_id"],
        "bucket": row["chart_bucket"],
        "hard_case": row["hard_case"],
        "ok": bool(verdict.ok),
        "right_shape": bool(verdict.ok)
        and is_right_shape(row["chart_bucket"], verdict.figure_type, code),
        "figure_type": verdict.figure_type,
        "failure_kind": verdict.failure_kind,
        "error": (verdict.error or "")[:200],
        "code": code[:600],
        "max_tokens": max_tokens,
    }


def summarize(rows: list[dict], arms: list[str]) -> dict:
    """Score only the rows every arm has reached, so the comparison stays paired
    even for a run that was stopped part way."""
    by_arm = {a: {r["test_id"]: r for r in rows if r["arm"] == a} for a in arms}
    common = set.intersection(*(set(d) for d in by_arm.values())) if by_arm else set()
    n = len(common)
    summary: dict = {}
    per_bucket: dict = defaultdict(dict)
    for a in arms:
        rs = [by_arm[a][t] for t in common]
        summary[a] = {
            "n": n,
            "render_rate": sum(r["ok"] for r in rs) / n if n else 0.0,
            "right_shape_rate": sum(r["right_shape"] for r in rs) / n if n else 0.0,
            "failure_kinds": dict(Counter(r["failure_kind"] for r in rs if not r["ok"])),
        }
        agg: dict[str, Counter] = defaultdict(Counter)
        for r in rs:
            agg[r["bucket"]]["n"] += 1
            agg[r["bucket"]]["ok"] += r["ok"]
            agg[r["bucket"]]["shape"] += r["right_shape"]
        for bucket, c in agg.items():
            per_bucket[bucket][a] = {
                "n": c["n"],
                "render_rate": c["ok"] / c["n"],
                "right_shape_rate": c["shape"] / c["n"],
            }
    paired = {}
    control = arms[0]
    for metric in ("ok", "right_shape"):
        for other in arms[1:]:
            gained = sorted(t for t in common if not by_arm[control][t][metric] and by_arm[other][t][metric])
            lost = sorted(t for t in common if by_arm[control][t][metric] and not by_arm[other][t][metric])
            paired[f"{metric}:{control}_vs_{other}"] = {
                "gained": len(gained),
                "lost": len(lost),
                "net": len(gained) - len(lost),
                "p_value": mcnemar_exact(len(gained), len(lost)),
                "gained_ids": gained[:40],
                "lost_ids": lost[:40],
            }
    return {
        "n_paired": n,
        "summary": summary,
        "per_bucket": dict(per_bucket),
        "paired": paired,
        "rows": {a: [by_arm[a][t] for t in sorted(common)] for a in arms},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/qwen3.5-9b-4bit")
    ap.add_argument("--adapter-path", default="runs/adapters-mlx")
    ap.add_argument("--testset", default="data/testset.jsonl")
    ap.add_argument("--out", default="data/ab_planner_hint.json")
    ap.add_argument("--arms", default=",".join(ARMS), help="comma-separated; the first is the control")
    ap.add_argument("--focus", default="", help="buckets to take whole, comma-separated")
    ap.add_argument("--others-per-bucket", type=int, default=0)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-tokens", type=int, default=CHARTIST_MAX_TOKENS)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument(
        "--summarize-only",
        action="store_true",
        help="rebuild the report from the saved rows without generating anything",
    )
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if a not in PROMPT_STYLE]
    if unknown:
        raise SystemExit(f"unknown arm(s) {unknown}; choose from {tuple(PROMPT_STYLE)}")

    rows = [
        json.loads(l)
        for l in Path(args.testset).read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    rows = select_rows(rows, args.focus, args.others_per_bucket, args.limit)

    # Every scored row is appended here the moment it exists. The first full
    # run kept everything in memory until the end, and stopping it at 452 of
    # 900 generations threw all of them away. Now a stop keeps what it
    # measured, and running the same command again resumes.
    ckpt = Path(args.out).with_suffix(".rows.jsonl")
    saved = (
        [json.loads(l) for l in ckpt.read_text(encoding="utf-8").splitlines() if l.strip()]
        if ckpt.exists()
        else []
    )
    done = {(r["arm"], r["test_id"]) for r in saved}
    started = time.time()

    if not args.summarize_only:
        todo_total = sum(1 for r in rows for a in arms if (a, r["test_id"]) not in done)
        print(
            f"{len(rows)} rows x {len(arms)} arms; {todo_total} generations to go "
            f"({len(done)} already saved in {ckpt})"
        )
        from mlx_lm import batch_generate, load
        from mlx_lm.sample_utils import make_sampler

        adapter = None if args.adapter_path in ("none", "") else args.adapter_path
        print(f"loading {args.model}" + (f" + {adapter}" if adapter else " (base)"))
        model, tokenizer = load(args.model, adapter_path=adapter)
        sampler = make_sampler(temp=0.0)

        real_b = zero_b = None
        if adapter and any(a in BASE_NOTHINK for a in arms):
            import mlx.core as mx

            tensors = mx.load(str(Path(adapter) / "adapters.safetensors"))
            real_b = [(k, v) for k, v in tensors.items() if k.endswith("lora_b")]
            zero_b = [(k, mx.zeros_like(v)) for k, v in real_b]

        def set_weights(arm: str) -> None:
            # In-place lora_b swap (~29 ms), not a reload: zeroed B makes the
            # LoRA branch add exactly nothing, which is the base model.
            if real_b is not None:
                model.load_weights(zero_b if arm in BASE_NOTHINK else real_b, strict=False)

        def tok(text: str, thinking: bool = True) -> list[int]:
            # Only pass the flag to turn thinking OFF, so every other arm's
            # prompt is byte-identical to what the server sends by default.
            extra = {} if thinking else {"enable_thinking": False}
            ids = tokenizer.apply_chat_template(
                [
                    {"role": "system", "content": SYSTEM_FALLBACK},
                    {"role": "user", "content": text},
                ],
                tokenize=True,
                add_generation_prompt=True,
                **extra,
            )
            if isinstance(ids, dict):
                ids = ids.get("input_ids", [])
            if ids and isinstance(ids[0], (list, tuple)):
                ids = ids[0]
            return list(ids)

        generated = 0
        # Arms inside the batch loop, not around it: every arm reaches the same
        # rows before the run moves on, so stopping at any point leaves a paired
        # comparison instead of one finished arm with nothing to compare it to.
        for start in range(0, len(rows), args.batch_size):
            batch = rows[start : start + args.batch_size]
            for arm in arms:
                todo = [r for r in batch if (arm, r["test_id"]) not in done]
                if not todo:
                    continue
                set_weights(arm)
                resp = batch_generate(
                    model,
                    tokenizer,
                    [tok(build_prompt(r, arm), thinking=arm not in BASE_NOTHINK) for r in todo],
                    max_tokens=args.max_tokens,
                    sampler=sampler,
                    verbose=False,
                )
                codes = [strip_fence(t) for t in resp.texts]
                verdicts = run_candidates(
                    [(c, r["fixture_csv"]) for c, r in zip(codes, todo)], max_workers=8
                )
                with ckpt.open("a", encoding="utf-8") as fh:
                    for r, c, v in zip(todo, codes, verdicts):
                        rec = record(arm, r, c, v, args.max_tokens)
                        fh.write(json.dumps(rec) + "\n")
                        saved.append(rec)
                        done.add((arm, r["test_id"]))
                generated += len(todo)
            rate = generated / max(1e-9, time.time() - started)
            left = todo_total - generated
            print(
                f"  {generated}/{todo_total}  ({rate*60:.1f}/min, eta {left/max(1e-9, rate)/60:.1f} min)",
                flush=True,
            )

    wanted = {r["test_id"] for r in rows}
    report = summarize([r for r in saved if r["test_id"] in wanted and r["arm"] in arms], arms)
    report.update(
        {
            "model": args.model,
            "adapter": args.adapter_path,
            "max_tokens": args.max_tokens,
            "arms": arms,
            "focus": args.focus,
            "others_per_bucket": args.others_per_bucket,
            "sample_size": len(rows),
            "minutes_this_run": (time.time() - started) / 60,
        }
    )
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n{report['n_paired']} of {len(rows)} sampled rows reached by every arm")
    print(f"{'arm':14s} {'render':>9s} {'shape':>9s}")
    for a in arms:
        s = report["summary"][a]
        print(f"{a:14s} {s['render_rate']*100:8.1f}% {s['right_shape_rate']*100:8.1f}%")
    print("\npaired, vs the control:")
    for key, p in report["paired"].items():
        print(
            f"  {key:34s} +{p['gained']:3d} / -{p['lost']:3d}  "
            f"net {p['net']:+3d}   p={p['p_value']:.4f}"
        )
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
