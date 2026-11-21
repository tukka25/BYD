"""Do the planner and the narrator suffer from running on the chartist adapter?

By default every model-calling role shares one mlx_lm server, started with the
chartist adapter (`make serve-model`, MLX_MODEL=default_model). So the planner,
asked for one JSON object, and the narrator, asked for a seven-word title, run
on weights trained to emit nothing but Python ending in print(fig.to_json()).
That had never been measured.

This drives both roles over the 300 frozen test questions twice, on ONE loaded
model: with the chartist adapter, and with every lora_b swapped for zeros. With
B = 0 the LoRA branch adds exactly nothing, so that arm IS the base model. The
swap is an in-place weight assignment (measured at 29 ms), not a reload.

Each role runs on its own prompt and its own parser, imported from the backend
rather than copied, so this measures what the app sends:
  planner   _SYSTEM, _EXAMPLES, _parse_chart_type, _keyword_chart
  narrator  _SYSTEM, _EXAMPLES, _clean, _from_question
langchain_core is stubbed only so those modules import; nothing here calls it.

The planner's label is also scored against each row's bucket. That is the
number the chart-type hint depends on: ab_planner_hint.py measures an ORACLE
hint, the most wiring could ever buy, and the planner's accuracy says how much
of that a real planner keeps. If data/ab_planner_hint.json exists, the two are
combined into an estimate for the actual production policy.

    .venv/bin/python measure_roles.py --limit 16    # smoke
    .venv/bin/python measure_roles.py               # all 300, both arms
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
import time
import types
from collections import Counter
from math import comb
from pathlib import Path

from contract import names_a_chart
from evaluate import THINK_PREFIX

AGENTS = Path(__file__).resolve().parent.parent / "backend" / "app" / "services" / "agents"

# Mirrors llm._MAX_TOKENS for these two roles. llm.py itself cannot be imported
# here: it needs pydantic-settings and the app config.
MAX_TOKENS = {"planner": 256, "narrator": 128}

# The chart labels a planner answer may give and still be right for a bucket.
# Same rule the eval scores shapes by: time series may be a line or bars, but an
# area answer is scored wrong for it, so it is wrong here too.
ACCEPT = {
    "bar": {"bar"},
    "line": {"line"},
    "grouped_or_stacked_bar": {"bar"},
    "scatter": {"scatter"},
    "pie_or_donut": {"pie"},
    "area": {"area"},
    "histogram": {"histogram"},
    "box": {"box"},
    "heatmap": {"heatmap"},
    "time_series": {"line", "bar"},
    "treemap_funnel_waterfall": {"treemap", "funnel", "waterfall"},
    "gauge_or_indicator": {"indicator"},
}

# "The adapter made this role write Python." Deliberately not the narrator's
# _CODE_SHAPED, which also matches `{` and would flag every correct JSON reply.
LOOKS_LIKE_CODE = re.compile(r"\bimport\s+\w|\bplotly\b|\bprint\s*\(|\bfig\s*=|\bpx\.\w+\s*\(")


def _load_agent_module(name: str):
    """Import a backend agent module without its LangChain dependency."""
    for mod in ("langchain_core", "langchain_core.prompts", "langchain_core.output_parsers"):
        sys.modules.setdefault(mod, types.ModuleType(mod))
    sys.modules["langchain_core.prompts"].ChatPromptTemplate = object
    sys.modules["langchain_core.output_parsers"].StrOutputParser = object
    spec = importlib.util.spec_from_file_location(f"_agent_{name}", AGENTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unbrace(text: str) -> str:
    """What ChatPromptTemplate sends: `{{` and `}}` are escapes for one brace."""
    return text.replace("{{", "{").replace("}}", "}")


def columns_of(prompt: str) -> list[str]:
    match = re.search(r"^columns: (\[.*\])$", prompt, re.MULTILINE)
    try:
        return [str(c) for c in ast.literal_eval(match.group(1))] if match else []
    except (ValueError, SyntaxError):
        return []


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2**n)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/qwen3.5-9b-4bit")
    ap.add_argument("--adapter-path", default="runs/adapters-mlx")
    ap.add_argument("--testset", default="data/testset.jsonl")
    ap.add_argument("--ab-report", default="data/ab_planner_hint.json")
    ap.add_argument("--out", default="data/role_measure.json")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--batch-size", type=int, default=16)
    args = ap.parse_args()

    planner = _load_agent_module("planner")
    narrator = _load_agent_module("narrator")

    rows = [json.loads(l) for l in Path(args.testset).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        rows = rows[: args.limit]

    import mlx.core as mx
    from mlx_lm import batch_generate, load
    from mlx_lm.sample_utils import make_sampler

    print(f"loading {args.model} + {args.adapter_path}")
    model, tokenizer = load(args.model, adapter_path=args.adapter_path)
    sampler = make_sampler(temp=0.0)

    adapter = mx.load(str(Path(args.adapter_path) / "adapters.safetensors"))
    real_b = [(k, v) for k, v in adapter.items() if k.endswith("lora_b")]
    zero_b = [(k, mx.zeros_like(v)) for k, v in real_b]

    def tokens(messages: list[dict]) -> list[int]:
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        if isinstance(ids, dict):
            ids = ids.get("input_ids", [])
        if ids and isinstance(ids[0], (list, tuple)):
            ids = ids[0]
        return list(ids)

    def planner_messages(question: str) -> list[dict]:
        msgs = [{"role": "system", "content": unbrace(planner._SYSTEM)}]
        for q, a in planner._EXAMPLES:
            msgs += [{"role": "user", "content": q}, {"role": "assistant", "content": unbrace(a)}]
        return msgs + [{"role": "user", "content": question}]

    def narrator_messages(question: str, columns: list[str]) -> list[dict]:
        msgs = [{"role": "system", "content": narrator._SYSTEM}]
        for q, t in narrator._EXAMPLES:
            msgs += [{"role": "user", "content": q}, {"role": "assistant", "content": t}]
        lead = ("Columns: " + ", ".join(columns[:14]) + "\n") if columns else ""
        return msgs + [{"role": "user", "content": lead + question}]

    def generate(prompts: list[list[int]], max_tokens: int, label: str) -> list[str]:
        out: list[str] = []
        for start in range(0, len(prompts), args.batch_size):
            resp = batch_generate(
                model, tokenizer, prompts[start : start + args.batch_size],
                max_tokens=max_tokens, sampler=sampler, verbose=False,
            )
            out.extend(THINK_PREFIX.sub("", t, count=1) if "</think>" in t else t for t in resp.texts)
            print(f"  {label}: {len(out)}/{len(prompts)}", flush=True)
        return out

    p_prompts = [tokens(planner_messages(r["question"])) for r in rows]
    n_prompts = [tokens(narrator_messages(r["question"], columns_of(r["prompt"]))) for r in rows]

    results: dict[str, list[dict]] = {}
    timings: dict[str, float] = {}
    for arm, weights in (("adapter", real_b), ("base", zero_b)):
        t0 = time.perf_counter()
        model.load_weights(weights, strict=False)
        mx.eval(model.parameters())
        print(f"\n[{arm}] lora_b set in {(time.perf_counter()-t0)*1000:.0f} ms")
        started = time.perf_counter()
        p_raw = generate(p_prompts, MAX_TOKENS["planner"], f"{arm} planner")
        n_raw = generate(n_prompts, MAX_TOKENS["narrator"], f"{arm} narrator")
        timings[arm] = time.perf_counter() - started

        arm_rows = []
        for r, praw, nraw in zip(rows, p_raw, n_raw):
            # The planner's own decision chain: model, then keywords, then default.
            label = planner._parse_chart_type(praw)
            source = "llm"
            if label is None:
                label, source = planner._keyword_chart(r["question"]), "keywords"
            if label is None:
                label, source = planner.DEFAULT_CHART, "default"
            title = narrator._clean(nraw)
            arm_rows.append({
                "test_id": r["test_id"],
                "bucket": r["chart_bucket"],
                "question": r["question"],
                "planner_raw": praw[:200],
                "planner_label": label,
                "planner_source": source,
                "planner_correct": label in ACCEPT.get(r["chart_bucket"], set()),
                "planner_wrote_code": bool(LOOKS_LIKE_CODE.search(praw)),
                "narrator_raw": nraw[:200],
                "narrator_title": title or narrator._from_question(r["question"]),
                "narrator_used_model": bool(title),
                "narrator_wrote_code": bool(LOOKS_LIKE_CODE.search(nraw)),
            })
        results[arm] = arm_rows

    model.load_weights(real_b, strict=False)  # leave the model as loaded

    n = len(rows)
    summary = {}
    for arm, rs in results.items():
        summary[arm] = {
            "planner_accuracy": sum(r["planner_correct"] for r in rs) / n,
            "planner_sources": dict(Counter(r["planner_source"] for r in rs)),
            "planner_wrote_code": sum(r["planner_wrote_code"] for r in rs) / n,
            "narrator_used_model": sum(r["narrator_used_model"] for r in rs) / n,
            "narrator_wrote_code": sum(r["narrator_wrote_code"] for r in rs) / n,
            "minutes": timings[arm] / 60,
        }

    paired = {}
    for key in ("planner_correct", "narrator_used_model"):
        a = {r["test_id"]: r[key] for r in results["adapter"]}
        b = {r["test_id"]: r[key] for r in results["base"]}
        base_better = sum(1 for t in a if b[t] and not a[t])
        adapter_better = sum(1 for t in a if a[t] and not b[t])
        paired[key] = {
            "base_better": base_better,
            "adapter_better": adapter_better,
            "p_value": mcnemar_exact(base_better, adapter_better),
        }

    # ---- what the hint is worth with THIS planner, not an oracle ----
    policy = {}
    ab_path = Path(args.ab_report)
    if ab_path.exists() and not args.limit:
        ab = json.loads(ab_path.read_text(encoding="utf-8"))
        by_arm = {arm: {r["test_id"]: r for r in rs} for arm, rs in ab["rows"].items()}
        control = by_arm["A_control"]
        for planner_arm in ("adapter", "base"):
            plan = {r["test_id"]: r for r in results[planner_arm]}
            for hint_arm in ("B_inline", "C_directive"):
                hinted = by_arm[hint_arm]
                counts = Counter()
                ok_lo = ok_hi = shape_lo = shape_hi = 0
                for tid, c in control.items():
                    p = plan.get(tid)
                    if p is None:
                        continue
                    if names_a_chart(p["question"]) or p["planner_source"] == "default":
                        counts["no hint sent"] += 1
                        got = c
                        ok_lo += got["ok"]; ok_hi += got["ok"]
                        shape_lo += got["right_shape"]; shape_hi += got["right_shape"]
                    elif p["planner_correct"]:
                        counts["right hint"] += 1
                        got = hinted[tid]
                        ok_lo += got["ok"]; ok_hi += got["ok"]
                        shape_lo += got["right_shape"]; shape_hi += got["right_shape"]
                    else:
                        # A WRONG hint was never measured: the A/B only ever gave
                        # the right one. Bound it: at best it is ignored and the
                        # row behaves like the control; at worst the model obeys
                        # it and draws the wrong chart (render unaffected).
                        counts["wrong hint"] += 1
                        ok_lo += c["ok"]; ok_hi += c["ok"]
                        shape_hi += c["right_shape"]
                total = sum(counts.values()) or 1
                policy[f"{planner_arm}_planner+{hint_arm}"] = {
                    "rows": dict(counts),
                    "render_rate": ok_lo / total,
                    "right_shape_rate_range": [shape_lo / total, shape_hi / total],
                }
        a_rows = list(control.values())
        policy["control"] = {
            "render_rate": sum(r["ok"] for r in a_rows) / len(a_rows),
            "right_shape_rate": sum(r["right_shape"] for r in a_rows) / len(a_rows),
        }

    report = {
        "model": args.model,
        "adapter": args.adapter_path,
        "n": n,
        "max_tokens": MAX_TOKENS,
        "summary": summary,
        "paired": paired,
        "policy_estimate": policy,
        "rows": results,
    }
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n{'':10s}{'planner acc':>12s}{'wrote code':>12s}{'narrator ok':>13s}{'wrote code':>12s}")
    for arm, s in summary.items():
        print(f"{arm:10s}{s['planner_accuracy']*100:11.1f}%{s['planner_wrote_code']*100:11.1f}%"
              f"{s['narrator_used_model']*100:12.1f}%{s['narrator_wrote_code']*100:11.1f}%")
    for arm, s in summary.items():
        print(f"  {arm} planner sources: {s['planner_sources']}")
    for key, p in paired.items():
        print(f"paired {key}: base better on {p['base_better']}, adapter better on "
              f"{p['adapter_better']}, p={p['p_value']:.4f}")
    if policy:
        print("\nproduction policy with a real planner:")
        print(f"  control: render {policy['control']['render_rate']*100:.1f}%  "
              f"shape {policy['control']['right_shape_rate']*100:.1f}%")
        for k, v in policy.items():
            if k == "control":
                continue
            lo, hi = v["right_shape_rate_range"]
            print(f"  {k:30s} render {v['render_rate']*100:.1f}%  shape {lo*100:.1f}-{hi*100:.1f}%  {v['rows']}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
