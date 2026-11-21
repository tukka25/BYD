#!/usr/bin/env python3
"""Write the dashboard requests the planner is trained and tested on.

For each schema, Haiku writes requests a real user would type into "Generate
dashboard" for that table, in different styles. One empty request per schema
is added without a model, because "just build me a dashboard" is the most
common request of all. Test-split schemas get their own requests, which
freeze_planning_testset.py locks before any training data exists.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import client
from contract import profile_table, render_profiles

SYSTEM = """You write the requests a business user types into a dashboard tool's "Generate dashboard" box, for one table.

Write the requested number of requests, each in a different style:
- a focused brief naming a measure and a breakdown, like "churn by country"
- a goal, like "is revenue growing"
- a comparison, like "compare plans by retention"
- a broad ask, like "an overview for the weekly ops meeting"
Use everyday words, not the column names. Each request under 12 words.
Reply as JSON: {"requests": [...]}"""

SCHEMA = {
    "type": "object",
    "properties": {"requests": {"type": "array", "items": {"type": "string"}}},
    "required": ["requests"],
    "additionalProperties": False,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-per-schema", type=int, default=3)
    ap.add_argument("--test-per-schema", type=int, default=2)
    ap.add_argument("--limit-schemas", type=int, default=None, help="pilot")
    ap.add_argument("--max-spend", type=float, default=1.00)
    ap.add_argument("--out", default="data/v2/requests.jsonl")
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} exists; the planning test set is frozen from it, so it is never regenerated")
    schemas = [json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l]
    if args.limit_schemas:
        schemas = schemas[: args.limit_schemas]
    requests = []
    for schema in schemas:
        n = args.train_per_schema if schema["split"] == "train" else args.test_per_schema
        profile = profile_table(schema["table_name"], pd.read_csv(schema["fixture_csv"]))
        user = f"Domain: {schema['domain']}\nNumber of requests: {n}\n\n{render_profiles([profile])}"
        requests.append(client.json_request(schema["schema_id"], client.HAIKU, SYSTEM, user, SCHEMA,
                                            max_tokens=1500, effort="low"))
    client.guard("v2-requests", min(args.max_spend, client.worst_case_cost(client.HAIKU, len(requests), 1500, 1500)))
    outcome = client.run_batch(requests, label="v2-requests")
    client.record_spend("v2-requests", client.HAIKU, outcome.usage, {"phase": "v2", "requests": len(requests)})

    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out.open("w", encoding="utf-8") as handle:
        for schema in schemas:
            wanted = args.train_per_schema if schema["split"] == "train" else args.test_per_schema
            got = [r.strip() for r in outcome.payloads.get(schema["schema_id"], {}).get("requests", []) if r.strip()]
            for n, text in enumerate(got[:wanted] + [""]):
                handle.write(json.dumps({"request_id": f"{schema['schema_id']}-r{n}", "schema_id": schema["schema_id"],
                                         "split": schema["split"], "request": text}, ensure_ascii=False) + "\n")
                written += 1
    print(f"wrote {written} requests for {len(schemas)} schemas; refusals {outcome.refusals}, unparsed {outcome.unparsed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
