#!/usr/bin/env python3
"""Does the planner plan better when it may check the data first?

Runs the backend's own planning code (tool step, analyst, planner, checks) on
the frozen planning test set, over HTTP against the running model server, on
the same rows in each arm: tools off, on (an explorer step first) or planner
(the planner holds the tools). With --draw N the first N plans of each
dashboard are drawn through the app's own path (run_spec: chartist, executor,
repair loop) and scored. Rows are saved as they finish; rerunning resumes.

    cd chartist-finetune
    ../backend/.venv/bin/python measure_planning_tools.py --tools off --limit 40
    ../backend/.venv/bin/python measure_planning_tools.py --tools on --limit 40
    ../backend/.venv/bin/python measure_planning_tools.py --tools on --draw 3 --limit 40
    ../backend/.venv/bin/python measure_planning_tools.py --tools planner --draw 3 --limit 40
    ../backend/.venv/bin/python measure_planning_tools.py --compare-planner --draw 3
"""
from __future__ import annotations

import argparse
import json
import math
import os
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

from app.services.agents.architect import spread_sample  # noqa: E402
from app.services.agents.chartist_contract import NUMBER_COLOUR_FIX, REPEATED_BAR_FIX, REPEATED_X_FIX  # noqa: E402
from app.services.agents.data_tools import PLANNER_TOOL_NAMES, ToolBox  # noqa: E402
from app.services.agents.discovery import discover  # noqa: E402
from app.services.agents.planning import finish, plan_charts, propose_directions  # noqa: E402
from app.services.agents.profiler import columns_by_table, profile_table  # noqa: E402
from app.services.llm import get_llm  # noqa: E402
from measure_planning import plan_matches  # noqa: E402

SAMPLE_ROWS = 2000


def first_try(r: dict) -> bool:
    # a checking turn's revision is a second planner call
    return r["planner_attempts"] == 1 and r["charts"] > 0 and not r.get("revisions", 0)


def sign_test_p(a: int, b: int) -> float:
    """Exact two-sided sign test on a wins one way and b the other."""
    n = a + b
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(a, b) + 1))
    return min(1.0, 2 * tail / 2 ** n)


def read_rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def draw_first(specs: list[dict], source: dict, chartist, data_dir: str, n: int, run=None) -> list[dict]:
    """Draw the first n plans through the app's own path and score each one:
    rendered, the planned kind, repairs used, and how many times the model drew
    a line whose x repeats or bars that repeat a category (each time the
    drawing check sent it back, plus a final failure for it)."""
    if run is None:
        from app.services.agents.spec_runner import run_spec as run
    drawn = []
    for spec in specs[:n]:
        started = time.perf_counter()
        result = run(spec, source, chartist, data_dir)
        figure = (result.get("execution_result") or {}).get("figure")
        rendered = bool(figure) and not result.get("error")
        traces = (figure or {}).get("data") or []
        figure_type = (traces[0].get("type") or "scatter") if traces else None
        error = str(result.get("error") or "")
        drawn.append({
            "chart": spec["chart"], "rendered": rendered,
            "kind_ok": rendered and plan_matches(spec["chart"], figure_type, str(result.get("code") or "")),
            "repairs": int(result.get("repairs") or 0),
            "repeated_x": sum(1 for reason in result.get("repair_reasons", []) if REPEATED_X_FIX in reason)
                          + (1 if REPEATED_X_FIX in error else 0),
            "repeated_bars": sum(1 for reason in result.get("repair_reasons", []) + [error]
                                 if REPEATED_BAR_FIX in reason or NUMBER_COLOUR_FIX in reason),
            "error": error[:160],
            "seconds": round(time.perf_counter() - started, 1),
        })
    return drawn


def summarize(rows: list[dict]) -> dict:
    planned = [r for r in rows if r["charts"]]
    asked = [r for r in rows if r["directions"]]
    drawn = [d for r in rows for d in r.get("drawn", [])]
    drew = [r for r in rows if r.get("drawn")]
    rendered = [d for d in drawn if d["rendered"]]
    draws = {
        "charts_drawn": len(drawn),
        "render_rate": len(rendered) / len(drawn),
        # Of the charts that rendered, how many are the kind that was planned (as measure_planning.py).
        "planned_kind_rate": sum(1 for d in rendered if d["kind_ok"]) / len(rendered) if rendered else 0.0,
        "repairs_per_chart": statistics.mean(d["repairs"] for d in drawn),
        "repeated_x_per_dashboard": statistics.mean(sum(d["repeated_x"] for d in r["drawn"]) for r in drew),
        # Rows saved before bars were checked have no count, and drew none sent back.
        "repeated_bars_per_dashboard": statistics.mean(
            sum(d.get("repeated_bars", 0) for d in r["drawn"]) for r in drew),
        "median_draw_seconds": statistics.median(r.get("draw_seconds", 0.0) for r in drew),
    } if drawn else {}
    return {
        "rows": len(rows),
        "analyst_usable_rate": sum(1 for r in rows if r["directions"]) / len(rows),
        "analyst_retry_rate": sum(1 for r in rows if r["analyst_attempts"] > 1) / len(rows),
        "planner_first_try_rate": sum(1 for r in planned if r["planner_attempts"] == 1) / len(planned) if planned else 0.0,
        "mean_charts": statistics.mean(r["charts"] for r in planned) if planned else 0.0,
        "dropped_per_dashboard": statistics.mean(r["dropped"] for r in planned) if planned else 0.0,
        "tool_calls_per_dashboard": statistics.mean(len(r["tool_calls"]) for r in rows),
        "median_seconds": statistics.median(r["seconds"] for r in rows),
        "asked_rows": len(asked),
        "first_try_rate_counting_failures": sum(1 for r in asked if first_try(r)) / len(asked) if asked else 0.0,
        "revisions_per_dashboard": statistics.mean(r.get("revisions", 0) for r in asked) if asked else 0.0,
        "planner_calls_per_dashboard": (
            statistics.mean(r["planner_attempts"] + r.get("revisions", 0) for r in asked) if asked else 0.0),
        "total_failure_rate": sum(1 for r in asked if r["charts"] == 0) / len(asked) if asked else 0.0,
        "charts_dropped_per_dashboard": statistics.mean(r["directions"] - r["charts"] for r in asked) if asked else 0.0,
        **draws,
    }


def compare(off_rows: list[dict], on_rows: list[dict]) -> dict:
    off = {r["request_id"]: r for r in off_rows}
    on = {r["request_id"]: r for r in on_rows}
    ids = [rid for rid in on if rid in off]
    # first try and dropped charts are compared only where both arms asked the analyst
    both = [rid for rid in ids if off[rid]["directions"] and on[rid]["directions"]]
    dropped = lambda r: r["directions"] - r["charts"]  # noqa: E731
    on_better = sum(1 for rid in both if first_try(on[rid]) and not first_try(off[rid]))
    off_better = sum(1 for rid in both if first_try(off[rid]) and not first_try(on[rid]))
    on_fewer = sum(1 for rid in both if dropped(on[rid]) < dropped(off[rid]))
    off_fewer = sum(1 for rid in both if dropped(off[rid]) < dropped(on[rid]))
    on_s = summarize([on[rid] for rid in ids])
    off_s = summarize([off[rid] for rid in ids])
    decision = {
        "first_try_not_lower": on_s["first_try_rate_counting_failures"] >= off_s["first_try_rate_counting_failures"],
        "dropped_not_higher": on_s["charts_dropped_per_dashboard"] <= off_s["charts_dropped_per_dashboard"],
        "analyst_usable_not_lower": on_s["analyst_usable_rate"] >= off_s["analyst_usable_rate"],
        "median_seconds_rise_under_30": on_s["median_seconds"] - off_s["median_seconds"] < 30,
    }
    decision["tools_on_by_default"] = all(decision.values())
    return {
        "paired_rows": len(ids),
        "first_try": {"on_better": on_better, "off_better": off_better,
                      "p": sign_test_p(on_better, off_better)},
        "charts_dropped": {"on_fewer": on_fewer, "off_fewer": off_fewer,
                           "p": sign_test_p(on_fewer, off_fewer)},
        "median_seconds_delta": statistics.median(on[rid]["seconds"] - off[rid]["seconds"] for rid in ids),
        "decision": decision,
    }


def compare_planner(on_rows: list[dict], planner_rows: list[dict]) -> dict:
    """PLANNER_TOOLS=planner against today's on, paired on the same request ids,
    with the rule that decides the default (AGENTS.md)."""
    on = {r["request_id"]: r for r in on_rows}
    planner = {r["request_id"]: r for r in planner_rows}
    ids = [rid for rid in planner if rid in on]
    both = [rid for rid in ids if on[rid]["directions"] and planner[rid]["directions"]]
    planner_better = sum(1 for rid in both if first_try(planner[rid]) and not first_try(on[rid]))
    on_better = sum(1 for rid in both if first_try(on[rid]) and not first_try(planner[rid]))
    on_s = summarize([on[rid] for rid in ids])
    pl_s = summarize([planner[rid] for rid in ids])
    decision = {
        "render_not_lower": pl_s.get("render_rate", 0.0) >= on_s.get("render_rate", 0.0),
        "first_try_not_lower": pl_s["first_try_rate_counting_failures"] >= on_s["first_try_rate_counting_failures"],
        "planned_kind_not_lower": pl_s.get("planned_kind_rate", 0.0) >= on_s.get("planned_kind_rate", 0.0),
        "repeated_x_not_higher": pl_s.get("repeated_x_per_dashboard", 0.0) <= on_s.get("repeated_x_per_dashboard", 0.0),
        "median_seconds_rise_under_30": pl_s["median_seconds"] - on_s["median_seconds"] < 30,
        # A planner arm that calls no tool is the on flow minus the explorer; never the default.
        "planner_uses_tools": pl_s.get("tool_calls_per_dashboard", 0.0) > 0,
        "dropped_not_higher": pl_s["charts_dropped_per_dashboard"] <= on_s["charts_dropped_per_dashboard"],
        "both_drew_charts": on_s.get("charts_drawn", 0) > 0 and pl_s.get("charts_drawn", 0) > 0,
    }
    decision["planner_by_default"] = all(decision.values())
    return {
        "paired_rows": len(ids),
        "on": on_s,
        "planner": pl_s,
        "first_try": {"planner_better": planner_better, "on_better": on_better,
                      "p": sign_test_p(planner_better, on_better)},
        "median_seconds_delta": statistics.median(planner[rid]["seconds"] - on[rid]["seconds"] for rid in ids),
        "decision": decision,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", choices=["on", "off", "planner"])
    ap.add_argument("--testset", default="data/v2/planning_testset.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--draw", type=int, default=0,
                    help="draw the first N plans of each dashboard through run_spec and score them")
    ap.add_argument("--compare", action="store_true",
                    help="score the two finished arms from their rows files; no model call")
    ap.add_argument("--compare-planner", action="store_true",
                    help="score planner against on from the --draw N rows files; no model call")
    args = ap.parse_args()
    if args.compare_planner:
        if not args.draw:
            ap.error("--compare-planner needs the --draw N the two arms ran with")
        result = compare_planner(read_rows(ROOT / f"data/v2/planning_tools_tools-on-draw{args.draw}.rows.jsonl"),
                                 read_rows(ROOT / f"data/v2/planning_tools_tools-planner-draw{args.draw}.rows.jsonl"))
        (ROOT / "data/v2/planning_tools_planner_compare.json").write_text(json.dumps(result, indent=2),
                                                                         encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.compare:
        result = compare(read_rows(ROOT / "data/v2/planning_tools_tools-off.rows.jsonl"),
                         read_rows(ROOT / "data/v2/planning_tools_tools-on.rows.jsonl"))
        (ROOT / "data/v2/planning_tools_compare.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.tools is None:
        ap.error("--tools is required unless --compare or --compare-planner is given")
    # A --draw run gets files of its own, so the committed tools-on/off rows are never resumed into.
    label = f"tools-{args.tools}" + (f"-draw{args.draw}" if args.draw else "")

    schemas = {r["schema_id"]: r for r in (json.loads(l) for l in
               (ROOT / "data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)}
    rows = [json.loads(l) for l in (ROOT / args.testset).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = rows[: args.limit] if args.limit else rows
    out = ROOT / f"data/v2/planning_tools_{label}.json"
    ckpt = out.with_suffix(".rows.jsonl")
    done = ({json.loads(l)["request_id"] for l in ckpt.read_text(encoding="utf-8").splitlines() if l.strip()}
            if ckpt.exists() else set())
    analyst, planner = get_llm("analyst"), get_llm("spec_planner")
    explorer = get_llm("explorer") if args.tools == "on" else None
    chartist = None
    if args.draw:
        from app.services.agents.chartist import ChartistAgent

        chartist = ChartistAgent(get_llm("chartist"))

    for row in rows:
        if row["request_id"] in done:
            continue
        schema = schemas[row["schema_id"]]
        frame = pd.read_csv(ROOT / schema["fixture_csv"])
        table = schema["table_name"]
        profiles = [profile_table(table, spread_sample(frame, SAMPLE_ROWS))]
        started = time.perf_counter()
        facts, validate, calls, planner_box = "", None, [], None
        if explorer is not None:
            toolbox = ToolBox({table: {"type": "file", "name": table}}, str(ROOT), loader=lambda s, d: frame)
            findings = finish(discover(explorer, row["request"], profiles, toolbox))
            facts, validate, calls = findings.note, toolbox.validate_spec, [c.name for c in findings.calls]
        elif args.tools == "planner":
            planner_box = ToolBox({table: {"type": "file", "name": table}}, str(ROOT), loader=lambda s, d: frame,
                                  tools=PLANNER_TOOL_NAMES, kinds=columns_by_table(profiles))
            validate = planner_box.validate_spec
        directions = propose_directions(analyst, row["request"], profiles, facts)
        charts = (plan_charts(planner, directions.items, profiles, facts, validate, toolbox=planner_box)
                  if directions.items else None)
        if planner_box is not None:
            # Counted from planner_box.calls, wherever inside plan_charts they are made; a tool step run
            # outside plan_charts would not be counted.
            calls = [c.name for c in planner_box.calls]
        record = {
            "request_id": row["request_id"], "request": row["request"], "tools": args.tools,
            "tool_calls": calls, "revisions": planner_box.revisions if planner_box is not None else 0,
            "facts_chars": len(facts),
            "directions": len(directions.items), "analyst_attempts": directions.attempts,
            "charts": len(charts.items) if charts else 0, "planner_attempts": charts.attempts if charts else 0,
            "dropped": sum(1 for e in (charts.errors if charts else []) if e.startswith("chart ")),
            "seconds": round(time.perf_counter() - started, 1),
        }
        if args.draw:
            source = {"type": "file", "name": Path(schema["fixture_csv"]).name, "path": str(ROOT / schema["fixture_csv"])}
            drawing = time.perf_counter()
            record["drawn"] = draw_first(charts.items if charts else [], source, chartist, str(ROOT), args.draw)
            record["draw_seconds"] = round(time.perf_counter() - drawing, 1)
        with ckpt.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        drew = (f", drew {sum(d['rendered'] for d in record['drawn'])}/{len(record['drawn'])}"
                if args.draw else "")
        print(f"{row['request_id']}: tools {calls} -> {record['charts']} charts, "
              f"planner tries {record['planner_attempts']}, {record['seconds']}s{drew}", flush=True)

    all_rows = read_rows(ckpt)
    summary = {"label": label, **summarize(all_rows)}
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
