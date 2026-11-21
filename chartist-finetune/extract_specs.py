#!/usr/bin/env python3
"""Write the chart plan each existing answer implements.

The v2 chartist learns to follow plans, so each of the 1,897 verified answers
gets the plan it actually draws. Haiku reads the code and writes the plan;
the plan is kept only if it passes the production check against the real
table, every column it names appears in the code, and the chart kind matches
the trace type the answer produced when it was executed.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

import chart_types
import client
from contract import KIND_TRACES, SPEC_RULES, SPEC_SCHEMA, check_spec, columns_by_table, profile_table, render_profiles

SYSTEM = (
    "You read the Python code of one chart and write the chart plan it implements.\n\n"
    + SPEC_RULES
    + "\n\nDescribe what the code actually draws, not what the question asked. Use the exact "
    "column names the code uses. Reply with the plan as JSON."
)
CHUNK = 200
SEP = "\n\nDataFrame `df` schema:"


def question_of(target: dict) -> str:
    """The question in a target's chartist prompt ("Task: <question>\\n\\nDataFrame ...")."""
    return target["messages"][1]["content"].split(SEP)[0][len("Task: "):]


def columns_in_code(spec: dict, code: str) -> bool:
    for key in ("x", "y", "group"):
        value = spec.get(key) or ""
        if value and not re.search(r"['\"]" + re.escape(value) + r"['\"]", code):
            return False
    return True


def consistent(spec: dict, figure_type: str | None, code: str) -> bool:
    if figure_type not in KIND_TRACES.get(spec["chart"], set()):
        return False
    if spec["chart"] == "area":
        return chart_types.is_area_figure(code)
    if spec["chart"] in ("line", "scatter"):
        return not chart_types.is_area_figure(code)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default="data/targets.jsonl")
    ap.add_argument("--out", default="data/v2/target_specs.jsonl")
    ap.add_argument("--limit", type=int, default=None, help="pilot")
    ap.add_argument("--est-cost", type=float, default=None, help="USD per request, from the pilot")
    ap.add_argument("--max-spend", type=float, default=3.00)
    args = ap.parse_args()

    schemas = {
        r["schema_id"]: r
        for r in (json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)
    }
    targets = [json.loads(l) for l in Path(args.targets).read_text(encoding="utf-8").splitlines() if l.strip()]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = (
        {json.loads(l)["question_id"] for l in out.read_text(encoding="utf-8").splitlines() if l.strip()}
        if out.exists() else set()
    )
    targets = [t for t in targets if t["question_id"] not in done]
    if args.limit:
        targets = targets[: args.limit]
    print(f"{len(targets)} answers to plan ({len(done)} already done)")

    profiles = {}
    kept = rejected = 0
    reasons: dict[str, int] = {}
    spent_here = 0.0
    for start in range(0, len(targets), CHUNK):
        chunk = targets[start:start + CHUNK]
        requests = []
        for t in chunk:
            schema = schemas[t["schema_id"]]
            if t["schema_id"] not in profiles:
                profiles[t["schema_id"]] = profile_table(schema["table_name"], pd.read_csv(schema["fixture_csv"]))
            user = (f"Table:\n{render_profiles([profiles[t['schema_id']]])}\n\nQuestion: {question_of(t)}"
                    f"\n\nCode:\n{t['messages'][2]['content']}")
            requests.append(client.json_request(t["question_id"], client.HAIKU, SYSTEM, user, SPEC_SCHEMA,
                                                max_tokens=2000, effort="low"))
        planned = ((args.est_cost * len(requests)) if args.est_cost
                   else client.worst_case_cost(client.HAIKU, len(requests), 2500, 2000))
        if spent_here + planned > args.max_spend:
            raise SystemExit(f"stopping: this script's spend ${spent_here:.2f} + ${planned:.2f} would pass --max-spend")
        client.guard("v2-specs", planned)
        outcome = client.run_batch(requests, label="v2-specs")
        spent_here += client.record_spend("v2-specs", client.HAIKU, outcome.usage,
                                          {"phase": "v2", "requests": len(requests)})
        with out.open("a", encoding="utf-8") as handle:
            for t in chunk:
                payload = outcome.payloads.get(t["question_id"])
                if not payload:
                    rejected += 1
                    reasons["no reply"] = reasons.get("no reply", 0) + 1
                    continue
                schema = schemas[t["schema_id"]]
                payload["table"] = schema["table_name"]
                spec, problems = check_spec(payload, columns_by_table([profiles[t["schema_id"]]]))
                code = t["messages"][2]["content"]
                reason = ("check: " + problems[0].split(";")[0][:60] if spec is None
                          else "column not in code" if not columns_in_code(spec, code)
                          else "kind does not match the figure" if not consistent(spec, t.get("figure_type"), code)
                          else "")
                if reason:
                    rejected += 1
                    reasons[reason] = reasons.get(reason, 0) + 1
                    continue
                spec["question"] = question_of(t)
                handle.write(json.dumps({"question_id": t["question_id"], "schema_id": t["schema_id"],
                                         "spec": spec}, ensure_ascii=False) + "\n")
                kept += 1
        print(f"  {start + len(chunk)}/{len(targets)}: kept {kept}, rejected {rejected}, "
              f"spent ${spent_here:.4f}", flush=True)
    top = sorted(reasons.items(), key=lambda kv: -kv[1])[:8]
    print(f"done: kept {kept}, rejected {rejected}; top reasons {top}; "
          f"v2 spend so far ${client.phase_spend():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
