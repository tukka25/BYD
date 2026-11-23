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


def summarize(rows: list[dict]) -> dict:
    planned = [r for r in rows if r["charts"]]
    return {
        "rows": len(rows),
        "analyst_usable_rate": sum(1 for r in rows if r["directions"]) / len(rows),
        "analyst_retry_rate": sum(1 for r in rows if r["analyst_attempts"] > 1) / len(rows),
        "planner_first_try_rate": sum(1 for r in planned if r["planner_attempts"] == 1) / len(planned) if planned else 0.0,
        "mean_charts": statistics.mean(r["charts"] for r in planned) if planned else 0.0,
        "dropped_per_dashboard": statistics.mean(r["dropped"] for r in planned) if planned else 0.0,
        "tool_calls_per_dashboard": statistics.mean(len(r["tool_calls"]) for r in rows),
        "median_seconds": statistics.median(r["seconds"] for r in rows),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", choices=["on", "off"], required=True)
    ap.add_argument("--testset", default="data/v2/planning_testset.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
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

    all_rows = [json.loads(l) for l in ckpt.read_text(encoding="utf-8").splitlines() if l.strip()]
    summary = {"label": label, **summarize(all_rows)}
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
