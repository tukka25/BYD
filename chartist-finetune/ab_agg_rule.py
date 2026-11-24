#!/usr/bin/env python3
"""A/B: the chartist's system prompt with and without the aggregation rule (CHARTIST_AGG_RULE).

Only the system text differs between the arms: "off" is the prompt lora-v2 was
trained on, "on" appends CHARTIST_AGG_RULE. Each plan is drawn through the app's
own path (run_spec: the chartist, the executor, the repair loop and the drawing
check) on the model behind the mlx_lm server, at temperature 0, by two
ChartistAgent instances that differ only in `agg_rule`. The wording and the
decision (DECISION) were fixed before the first call.

Two sets, in this order:

  live    every distinct plan the api logged on a file table
          (data/v2/live_plans.jsonl, saved from `docker logs` on 2026-11-24; the
          stored files are byte-identical to backend/uploads/web_traffic.csv and
          property_sales.csv, which `make sample-data` writes). It holds the two
          weekday bars the model drew on raw rows (live-10, live-22).
  frozen  the no-harm set: every distinct bar plan the lora-v2 planning
          evaluation saved for the frozen 120 planning requests
          (data/v2/planning_eval_lora-v2.rows.jsonl) and up to PER_KIND plans of
          every other kind (seeded), each on its fixture table.

Items run in a seeded order with both arms back to back, so a stopped run still
leaves a paired sample. Rows are saved as each item finishes; rerunning resumes.

Scored per drawn chart: rendered; the planned kind; repairs; lines run back and
forth (the drawing check's REPEATED_X_FIX); bar traces that repeat a category
(bar_repeats: raw rows Plotly stacks); for a bar plan without a time grain,
whether its bars carry the plan's own groupby values (anything else is "not
checked"); points drawn on agg-none plans; and the code.

    .venv/bin/python ab_agg_rule.py --set live
    .venv/bin/python ab_agg_rule.py --set frozen
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))
os.environ.setdefault("LLM_BACKEND", "mlx")
os.environ.setdefault("MLX_BASE_URL", "http://127.0.0.1:8080/v1")
os.environ.setdefault("MLX_MODEL", "default_model")

import pandas as pd  # noqa: E402

from app.services.agents.chartist_contract import (  # noqa: E402
    CHARTIST_AGG_RULE, CHARTIST_USER_TEMPLATE, NUMBER_COLOUR_FIX, REPEATED_BAR_FIX, REPEATED_X_FIX, bar_repeats,
)
from app.utils.figure_json import decode_typed_arrays  # noqa: E402
from measure_planning import plan_matches  # noqa: E402

ARMS = ("off", "on")
PER_KIND = 10
SEED = 20261124
SPEC_KEYS = ("chart", "table", "x", "y", "group", "agg", "grain", "sort", "top_n")
RELATIVE_TOLERANCE = 0.01
ABSOLUTE_TOLERANCE = 0.005
MAXLEN = 2048
DECISION = {
    "live": ("passes when the off arm draws raw-row bars on at least one plan (otherwise this is not the app's "
             "path), the on arm draws none, the on arm's bars carry the planned values on at least as many plans, "
             "and no plan that renders off fails on"),
    "frozen": ("passes when, against off, the on arm's render rate and planned-kind rate are not lower, its "
               "raw-row bar charts are not more, its bars with the planned values are not fewer, and it collapses "
               "no more agg-none charts (under half the other arm's points) than off does"),
    "default": "CHARTIST_AGG_RULE becomes 'on' only if both sets pass",
}


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def sign_test_p(a: int, b: int) -> float:
    """Exact two-sided sign test on a wins one way and b the other."""
    n = a + b
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(min(a, b) + 1)) / 2 ** n)


def live_items(path: Path = ROOT / "data/v2/live_plans.jsonl") -> list[dict]:
    return [{"item_id": row["plan_id"], "set": "live", "spec": row["spec"], "csv": str(ROOT.parent / row["file"])}
            for row in read_rows(path)]


def frozen_items(rows_path: Path = ROOT / "data/v2/planning_eval_lora-v2.rows.jsonl",
                 schemas_path: Path = ROOT / "data/schemas.jsonl",
                 per_kind: int = PER_KIND, seed: int = SEED) -> list[dict]:
    """Every distinct bar plan, and a seeded sample of up to per_kind plans of each other kind, shuffled."""
    schemas = {row["schema_id"]: row for row in read_rows(schemas_path)}
    seen, bars, others = set(), [], {}
    for row in read_rows(rows_path):
        for n, spec in enumerate(row.get("specs") or [], 1):
            key = (row["schema_id"], json.dumps({k: spec.get(k) for k in SPEC_KEYS}, sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            item = {"item_id": f"{row['request_id']}-c{n}", "set": "frozen", "spec": spec,
                    "csv": str(ROOT / schemas[row["schema_id"]]["fixture_csv"])}
            (bars if spec.get("chart") == "bar" else others.setdefault(str(spec.get("chart")), [])).append(item)
    rng = random.Random(seed)
    picked = list(bars)
    for kind in sorted(others):
        picked += rng.sample(others[kind], min(per_kind, len(others[kind])))
    rng.shuffle(picked)
    return picked


def expected_bar_values(frame: pd.DataFrame, spec: dict) -> list[list[float]] | None:
    """The plan's own groupby, one value per x (and group), for a bar plan without a time grain.

    A list of acceptable answers: a count may count rows or non-empty values.
    None when the plan cannot be checked this way.
    """
    if spec.get("chart") != "bar" or spec.get("grain"):
        return None
    x, y, group = (str(spec.get(key) or "") for key in ("x", "y", "group"))
    agg = str(spec.get("agg") or "none")
    if not x or any(column and column not in frame.columns for column in (x, y, group)):
        return None
    keys = [x] + ([group] if group else [])
    try:
        if agg == "count" or (not y and agg != "none"):
            answers = [frame.dropna(subset=keys).groupby(keys).size()]
            if y:
                answers.append(frame.dropna(subset=keys + [y]).groupby(keys).size())
        elif y and agg in ("sum", "mean", "median", "min", "max"):
            answers = [frame.dropna(subset=keys + [y]).groupby(keys)[y].agg(agg)]
        else:
            return None
        out: list[list[float]] = []
        for series in answers:
            values = [float(value) for value in series.tolist()]
            if values not in out:
                out.append(values)
        return out
    except (TypeError, ValueError):
        return None


def drawn_bar_values(figure: dict) -> list[float] | None:
    """Each bar trace's values summed per category, as Plotly stacks them; None when there is no bar trace."""
    values: list[float] = []
    found = False
    for trace in (figure or {}).get("data") or []:
        if not isinstance(trace, dict) or trace.get("type") != "bar":
            continue
        horizontal = trace.get("orientation") == "h"
        categories, heights = trace.get("y" if horizontal else "x"), trace.get("x" if horizontal else "y")
        if not isinstance(heights, list):
            continue
        if not isinstance(categories, list) or len(categories) != len(heights):
            categories = list(range(len(heights)))
        found = True
        sums: dict = {}
        try:
            for category, height in zip(categories, heights):
                if height is None:
                    continue
                key = tuple(category) if isinstance(category, list) else category
                sums[key] = sums.get(key, 0.0) + float(height)
        except (TypeError, ValueError):
            return None
        values.extend(sums.values())
    return values if found else None


def _close(value: float, target: float) -> bool:
    return abs(value - target) <= RELATIVE_TOLERANCE * abs(target) + ABSOLUTE_TOLERANCE


def values_ok(expected: list[list[float]] | None, drawn: list[float] | None, top_n: int) -> bool | None:
    """Every drawn bar is one of the plan's values (within rounding), and none are missing (top_n drawn
    when the plan asks for it). None when either side is unknown."""
    if expected is None or drawn is None:
        return None
    for answer in expected:
        need = min(len(answer), top_n) if top_n else len(answer)
        if len(drawn) >= need and all(any(_close(value, target) for target in answer) for value in drawn):
            return True
    return False


def _length(value) -> int:
    return len(value) if isinstance(value, list) else 0


def points_drawn(figure: dict) -> int:
    return sum(max(_length(trace.get("x")), _length(trace.get("y")))
               for trace in (figure or {}).get("data") or [] if isinstance(trace, dict))


def times_asked(fix: str, reasons: list[str], error: str) -> int:
    """How many times the drawing check named this fix: each repair asked for, plus a final failure for it."""
    return sum(1 for reason in reasons if fix in reason) + (1 if fix in error else 0)


def score(spec: dict, frame: pd.DataFrame, result: dict) -> dict:
    """One drawn chart, scored as the app would show it."""
    figure = decode_typed_arrays((result.get("execution_result") or {}).get("figure") or {})
    figure = figure if isinstance(figure, dict) else {}
    error = str(result.get("error") or "")
    rendered = bool(figure) and not error
    traces = [trace for trace in figure.get("data") or [] if isinstance(trace, dict)]
    figure_type = (traces[0].get("type") or "scatter") if traces else None
    code = str(result.get("code") or "")
    reasons = [str(reason) for reason in result.get("repair_reasons") or []]
    expected = expected_bar_values(frame, spec)
    if expected is None:
        values = None
    else:
        values = bool(values_ok(expected, drawn_bar_values(figure) or [], int(spec.get("top_n") or 0))) \
            if rendered else False
    raw = bar_repeats(figure) if rendered else []
    return {
        "rendered": rendered,
        "kind_ok": rendered and plan_matches(str(spec.get("chart")), figure_type, code),
        "repairs": int(result.get("repairs") or 0),
        "repeated_x": times_asked(REPEATED_X_FIX, reasons, error),
        "repeated_bars": times_asked(REPEATED_BAR_FIX, reasons, error) + times_asked(NUMBER_COLOUR_FIX, reasons, error),
        "raw_bars": len(raw),
        "raw_bar_notes": raw[:3],
        "values_ok": values,
        "points": points_drawn(figure) if rendered and str(spec.get("agg") or "none") == "none" else None,
        "error": error[:200],
        "code": code,
    }


def summarize(rows: list[dict], arm: str) -> dict:
    drawn = [row["arms"][arm] for row in rows]
    n = len(drawn) or 1
    bars = [row["arms"][arm] for row in rows if row["spec"].get("chart") == "bar"]
    checked = [d for d in bars if d.get("values_ok") is not None]
    seconds = [d.get("seconds", 0.0) for d in drawn]
    return {
        "charts": len(drawn),
        "render_rate": sum(d["rendered"] for d in drawn) / n,
        "planned_kind_rate": sum(d["kind_ok"] for d in drawn) / n,
        "repairs_per_chart": sum(d["repairs"] for d in drawn) / n,
        "lines_back_and_forth": sum(d["repeated_x"] for d in drawn),
        # Rows saved before bars were checked have no count, and had none sent back.
        "bars_sent_back": sum(d.get("repeated_bars", 0) for d in drawn),
        "bar_plans": len(bars),
        "raw_row_bar_charts": sum(1 for d in drawn if d["raw_bars"]),
        "bar_values_checked": len(checked),
        "bar_values_ok": sum(1 for d in checked if d["values_ok"]),
        "median_seconds": statistics.median(seconds) if seconds else 0.0,
    }


def compare(rows: list[dict]) -> dict:
    """Paired counts: items where one arm did better than the other, with an exact sign test."""
    def paired(test) -> dict:
        on_better = off_better = 0
        for row in rows:
            verdict = test(row["arms"]["off"], row["arms"]["on"])
            on_better += verdict == "on"
            off_better += verdict == "off"
        return {"on_better": on_better, "off_better": off_better, "p": sign_test_p(on_better, off_better)}

    def flag(key):
        return lambda off, on: "on" if on[key] and not off[key] else "off" if off[key] and not on[key] else None

    collapsed = {"on_collapsed": 0, "off_collapsed": 0}
    for row in rows:
        if str(row["spec"].get("agg") or "none") != "none":
            continue
        off, on = row["arms"]["off"].get("points"), row["arms"]["on"].get("points")
        if not off or not on:
            continue
        if on * 2 < off:
            collapsed["on_collapsed"] += 1
        elif off * 2 < on:
            collapsed["off_collapsed"] += 1
    return {
        "rendered": paired(flag("rendered")),
        "kind_ok": paired(flag("kind_ok")),
        "raw_bars": paired(lambda off, on: "on" if off["raw_bars"] and not on["raw_bars"]
                           else "off" if on["raw_bars"] and not off["raw_bars"] else None),
        "bar_values": paired(lambda off, on: None if off["values_ok"] is None or on["values_ok"] is None
                             else flag("values_ok")(off, on)),
        "collapsed": collapsed,
    }


def live_decision(rows: list[dict]) -> dict:
    off, on = summarize(rows, "off"), summarize(rows, "on")
    lost = sum(1 for row in rows if row["arms"]["off"]["rendered"] and not row["arms"]["on"]["rendered"])
    decision = {
        "off_draws_raw_row_bars": off["raw_row_bar_charts"] > 0,
        "on_draws_no_raw_row_bars": on["raw_row_bar_charts"] == 0,
        "on_values_not_fewer": on["bar_values_ok"] >= off["bar_values_ok"],
        "no_chart_lost": lost == 0,
    }
    decision["passes"] = all(decision.values())
    return decision


def frozen_decision(rows: list[dict]) -> dict:
    off, on = summarize(rows, "off"), summarize(rows, "on")
    collapsed = compare(rows)["collapsed"]
    decision = {
        "render_not_lower": on["render_rate"] >= off["render_rate"],
        "kind_not_lower": on["planned_kind_rate"] >= off["planned_kind_rate"],
        "raw_bars_not_more": on["raw_row_bar_charts"] <= off["raw_row_bar_charts"],
        "bar_values_not_fewer": on["bar_values_ok"] >= off["bar_values_ok"],
        "collapsed_not_more": collapsed["on_collapsed"] <= collapsed["off_collapsed"],
    }
    decision["passes"] = all(decision.values())
    return decision


def breakdown(rows: list[dict]) -> dict:
    """Outside the pre-registered decision: bar plans with and without a group, each kind, and every chart one
    arm drew and the other did not (or drew with other values), so a net rate cannot hide a loss."""
    def bar_counts(drawn: list[dict]) -> dict:
        checked = [d for d in drawn if d.get("values_ok") is not None]
        return {"plans": len(drawn), "rendered": sum(1 for d in drawn if d["rendered"]),
                "values_checked": len(checked), "values_ok": sum(1 for d in checked if d["values_ok"]),
                "raw_row_bar_charts": sum(1 for d in drawn if d["raw_bars"])}

    def listed(row: dict, arm: str) -> dict:
        return {"item_id": row["item_id"], "chart": row["spec"].get("chart"), "group": row["spec"].get("group") or "",
                "title": row["spec"].get("title") or "", "error": row["arms"][arm].get("error") or ""}

    bars = [row for row in rows if row["spec"].get("chart") == "bar"]
    split = {"grouped": [row for row in bars if row["spec"].get("group")],
             "ungrouped": [row for row in bars if not row["spec"].get("group")]}
    by_kind: dict = {}
    for row in rows:
        kind = by_kind.setdefault(str(row["spec"].get("chart")),
                                  {arm: {"plans": 0, "rendered": 0, "kind_ok": 0} for arm in ARMS})
        for arm in ARMS:
            kind[arm]["plans"] += 1
            kind[arm]["rendered"] += int(bool(row["arms"][arm]["rendered"]))
            kind[arm]["kind_ok"] += int(bool(row["arms"][arm]["kind_ok"]))
    drew = lambda row, arm: bool(row["arms"][arm]["rendered"])  # noqa: E731
    both = [row for row in rows if drew(row, "off") and drew(row, "on")]
    return {
        "note": "not part of the pre-registered decision",
        "bars": {name: {arm: bar_counts([row["arms"][arm] for row in group]) for arm in ARMS}
                 for name, group in split.items()},
        "by_kind": dict(sorted(by_kind.items())),
        "lost_on": [listed(row, "on") for row in rows if drew(row, "off") and not drew(row, "on")],
        "gained_on": [listed(row, "off") for row in rows if drew(row, "on") and not drew(row, "off")],
        "values_better_on": [listed(row, "on") for row in both
                             if row["arms"]["on"]["values_ok"] is True and row["arms"]["off"]["values_ok"] is False],
        "values_worse_on": [listed(row, "on") for row in both
                            if row["arms"]["off"]["values_ok"] is True and row["arms"]["on"]["values_ok"] is False],
    }


def server_prompt_tokens(messages: list[dict]) -> int:
    """Prompt tokens as the model server counts them (its own chat template), from a one-token reply."""
    import urllib.request

    body = json.dumps({"model": os.environ["MLX_MODEL"], "messages": messages, "max_tokens": 1,
                       "temperature": 0}).encode()
    request = urllib.request.Request(os.environ["MLX_BASE_URL"].rstrip("/") + "/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return int(json.load(response)["usage"]["prompt_tokens"])


def prompt_tokens(items: list[dict], agents: dict, context_for, count=server_prompt_tokens, longest: int = 3) -> dict:
    """Each arm's longest chartist prompts (by characters), counted by the server, against MAXLEN, the
    length lora-v2 was trained at."""
    prompts: dict[str, list[list[dict]]] = {arm: [] for arm in ARMS}
    for item in items:
        source = {"type": "file", "name": Path(item["csv"]).name, "path": item["csv"]}
        context = context_for(source, str(ROOT))
        for arm in ARMS:
            variables = agents[arm].prompt_variables(item["spec"].get("question") or "", {}, context, spec=item["spec"])
            prompts[arm].append([{"role": "system", "content": agents[arm].system_prompt},
                                 {"role": "user", "content": CHARTIST_USER_TEMPLATE.format(**variables)}])
    report = {}
    for arm, every in prompts.items():
        size = lambda messages: sum(len(message["content"]) for message in messages)  # noqa: E731
        ranked = sorted(every, key=size, reverse=True)[:longest]
        counted = [count(messages) for messages in ranked]
        report[arm] = {"longest_chars": size(ranked[0]) if ranked else 0, "max_tokens": max(counted, default=0),
                       "over_maxlen": sum(tokens > MAXLEN for tokens in counted), "counted": len(counted)}
    return report


def _status(arm: dict) -> str:
    if not arm["rendered"]:
        return "failed"
    if arm["raw_bars"]:
        return "raw-row bars"
    if arm["values_ok"] is False:
        return "values wrong"
    return "ok" if arm["kind_ok"] else "other kind"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=("live", "frozen"), required=True)
    ap.add_argument("--limit", type=int, default=None, help="first N items only, for a smoke run")
    ap.add_argument("--label", default="", help="suffix for the output files")
    args = ap.parse_args()

    from app.services.agents.chartist import ChartistAgent
    from app.services.agents.spec_runner import context_for, run_spec
    from app.services.llm import get_llm

    items = live_items() if args.set == "live" else frozen_items()
    if args.limit:
        items = items[: args.limit]
    out = ROOT / f"data/v2/ab_agg_rule_{args.set}{'-' + args.label if args.label else ''}.json"
    ckpt = out.with_suffix(".rows.jsonl")
    done = {row["item_id"] for row in read_rows(ckpt)} if ckpt.exists() else set()
    llm = get_llm("chartist")
    agents = {arm: ChartistAgent(llm, chart_type_hint_style="off", agg_rule=arm) for arm in ARMS}
    tokens = prompt_tokens(items, agents, context_for)
    print(f"{len(items)} items, {len(items) - len(done)} to go; prompt tokens {tokens}", flush=True)

    frames: dict[str, pd.DataFrame] = {}
    started = time.perf_counter()
    for item in items:
        if item["item_id"] in done:
            continue
        csv = item["csv"]
        if csv not in frames:
            frames[csv] = pd.read_csv(csv)
        source = {"type": "file", "name": Path(csv).name, "path": csv}
        arms = {}
        for arm in ARMS:
            began = time.perf_counter()
            result = run_spec(item["spec"], source, agents[arm], str(ROOT))
            arms[arm] = {**score(item["spec"], frames[csv], result), "seconds": round(time.perf_counter() - began, 1)}
        record = {"item_id": item["item_id"], "set": item["set"], "csv": str(Path(csv).relative_to(ROOT.parent)),
                  "spec": {key: item["spec"].get(key) for key in SPEC_KEYS + ("title", "question")}, "arms": arms}
        with ckpt.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{item['item_id']} {item['spec']['chart']}: off {_status(arms['off'])} | on {_status(arms['on'])} "
              f"({(time.perf_counter() - started) / 60:.1f} min)", flush=True)

    rows = read_rows(ckpt)
    decide = live_decision if args.set == "live" else frozen_decision
    report = {
        "set": args.set, "items": len(rows), "rule": CHARTIST_AGG_RULE, "decision_rule": DECISION,
        "prompt_tokens": tokens, "off": summarize(rows, "off"), "on": summarize(rows, "on"),
        "paired": compare(rows), "decision": decide(rows), "breakdown": breakdown(rows),
    }
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("off", "on", "paired", "decision")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
