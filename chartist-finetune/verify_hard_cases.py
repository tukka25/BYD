#!/usr/bin/env python3
"""Ground missing_field labels against the schema; clear the label when nothing is missing."""
from __future__ import annotations

import json
from pathlib import Path

import client

SYSTEM = """You check whether a dashboard question can be answered entirely from a table's columns.

For the question, list every concept it references (measures, dimensions, filters, time grains) and decide whether each maps to an available column or a category value listed in a column.
- Column names come in many styles (camelCase, snake_case, abbreviations, prefixes). Treat abbreviated or restyled names as matches: tot_rev is total revenue, ADR_AMT is average daily rate.
- Derived quantities count as present when computable from available columns (a monthly rollup from a date column, a share from a measure, a count of rows).
- A concept is absent only if no column or category value could supply it.
Return all_concepts_present true only if every concept is present; otherwise list the absent concepts."""

SCHEMA = {
    "type": "object",
    "properties": {"all_concepts_present": {"type": "boolean"},
                   "absent_concepts": {"type": "array", "items": {"type": "string"}}},
    "required": ["all_concepts_present", "absent_concepts"], "additionalProperties": False,
}


def main() -> None:
    schemas = {j["schema_id"]: j for j in (json.loads(l) for l in Path("data/schemas.jsonl").read_text().splitlines() if l)}
    path = Path("data/questions.jsonl")
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l]
    targets = [r for r in rows if r["hard_case"] == "missing_field"]
    reqs = []
    for r in targets:
        s = schemas[r["schema_id"]]
        cols = [{k: c[k] for k in ("name", "dtype", "categories") if k in c} for c in s["columns"]]
        reqs.append(client.json_request(
            custom_id=r["question_id"], model=client.HAIKU, system=SYSTEM,
            user=f"Table: {s['table_name']} ({s['domain']})\ncolumns: {json.dumps(cols, default=str)}\n\nQuestion: {r['question']}",
            schema=SCHEMA, max_tokens=512, effort="low"))
    out = client.run_batch(reqs, label="verify_hard")
    cost = client.record_spend("verify_hard", client.HAIKU, out.usage, {"requests": len(reqs)})
    relabelled = 0
    for r in targets:
        p = out.payloads.get(r["question_id"])
        if p and p.get("all_concepts_present") is True:
            r["hard_case"] = None; relabelled += 1
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps({
        "checked": len(targets), "no_response": len(targets) - len(out.payloads),
        "relabelled": relabelled,
        "missing_field_now": sum(r["hard_case"] == "missing_field" for r in rows),
        "hard_case_share": round(sum(bool(r["hard_case"]) for r in rows) / len(rows), 3),
        "cost": cost}))


if __name__ == "__main__":
    main()
