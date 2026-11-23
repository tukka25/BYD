#!/usr/bin/env python3
"""Does the planner plan better when it may check the data first?

Runs the backend's own planning code (tool step, analyst, planner, checks) on
the frozen planning test set, over HTTP against the running model server, with
and without the tool step on the same rows. Nothing is drawn; measure_planning.py
covers drawing. Rows are saved as they finish; rerunning resumes.

    cd chartist-finetune
    ../backend/.venv/bin/python measure_planning_tools.py --tools off --limit 40
    ../backend/.venv/bin/python measure_planning_tools.py --tools on --limit 40
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
from app.services.agents.data_tools import ToolBox  # noqa: E402
from app.services.agents.discovery import discover  # noqa: E402
from app.services.agents.planning import finish, plan_charts, propose_directions  # noqa: E402
from app.services.agents.profiler import profile_table  # noqa: E402
from app.services.llm import get_llm  # noqa: E402

SAMPLE_ROWS = 2000


def first_try(r: dict) -> bool:
    return r["planner_attempts"] == 1 and r["charts"] > 0


def sign_test_p(a: int, b: int) -> float:
    """Exact two-sided sign test on a wins one way and b the other."""
    n = a + b
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(a, b) + 1))
    return min(1.0, 2 * tail / 2 ** n)


def read_rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def summarize(rows: list[dict]) -> dict:
    planned = [r for r in rows if r["charts"]]
    asked = [r for r in rows if r["directions"]]
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
        "total_failure_rate": sum(1 for r in asked if r["charts"] == 0) / len(asked) if asked else 0.0,
        "charts_dropped_per_dashboard": statistics.mean(r["directions"] - r["charts"] for r in asked) if asked else 0.0,
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", choices=["on", "off"])
    ap.add_argument("--testset", default="data/v2/planning_testset.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--compare", action="store_true",
                    help="score the two finished arms from their rows files; no model call")
    args = ap.parse_args()
    if args.compare:
        result = compare(read_rows(ROOT / "data/v2/planning_tools_tools-off.rows.jsonl"),
                         read_rows(ROOT / "data/v2/planning_tools_tools-on.rows.jsonl"))
        (ROOT / "data/v2/planning_tools_compare.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.tools is None:
        ap.error("--tools is required unless --compare is given")
    label = f"tools-{args.tools}"

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

    for row in rows:
        if row["request_id"] in done:
            continue
        schema = schemas[row["schema_id"]]
        frame = pd.read_csv(ROOT / schema["fixture_csv"])
        table = schema["table_name"]
        profiles = [profile_table(table, spread_sample(frame, SAMPLE_ROWS))]
        started = time.perf_counter()
        facts, validate, calls = "", None, []
        if explorer is not None:
            toolbox = ToolBox({table: {"type": "file", "name": table}}, str(ROOT), loader=lambda s, d: frame)
            findings = finish(discover(explorer, row["request"], profiles, toolbox))
            facts, validate, calls = findings.note, toolbox.validate_spec, [c.name for c in findings.calls]
        directions = propose_directions(analyst, row["request"], profiles, facts)
        charts = plan_charts(planner, directions.items, profiles, facts, validate) if directions.items else None
        record = {
            "request_id": row["request_id"], "request": row["request"], "tools": args.tools,
            "tool_calls": calls, "facts_chars": len(facts),
            "directions": len(directions.items), "analyst_attempts": directions.attempts,
            "charts": len(charts.items) if charts else 0, "planner_attempts": charts.attempts if charts else 0,
            "dropped": sum(1 for e in (charts.errors if charts else []) if e.startswith("chart ")),
            "seconds": round(time.perf_counter() - started, 1),
        }
        with ckpt.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        print(f"{row['request_id']}: tools {calls} -> {record['charts']} charts, "
              f"planner tries {record['planner_attempts']}, {record['seconds']}s", flush=True)

    all_rows = read_rows(ckpt)
    summary = {"label": label, **summarize(all_rows)}
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
