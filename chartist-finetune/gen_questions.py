#!/usr/bin/env python3
"""Generate natural dashboard questions per schema, under the chart-type quota."""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import chart_types
import client

SYSTEM = """You write the questions a business user types into a dashboard tool.

Rules:
- Never mention Plotly, Python, code, charts-as-examples, or column names verbatim unless a person naturally would.
- Write like a person asking for something, not like documentation. 4 to 18 words.
- The question must be answerable from the given table, and must suit the requested chart shape.
- Vary phrasing across the batch: questions, imperatives, and fragments all appear in real usage.
- No greetings, no "please", no "could you".

Hard-case kinds, when requested:
- multi_column_aggregation: needs a group-by and a sum/mean across more than one column.
- date_parsing_and_resampling: needs the date column rolled up by month, quarter, or week.
- grouped_or_faceted: needs a second dimension as colour, group, or facet.
- missing_field: asks about something NOT in this table, so the answer must work with what is there.
- ambiguous_question: genuinely underspecified, the kind a real user types."""

SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "chart_bucket": {"type": "string"},
                    "hard_case": {"type": "string"},
                },
                "required": ["question", "chart_bucket"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-schema", type=int, default=16)
    parser.add_argument("--limit-schemas", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    schemas = [json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l]
    if args.limit_schemas:
        schemas = schemas[: args.limit_schemas]

    rng = random.Random(args.seed)
    requests = []
    assignments = {}

    # Allocate the quota globally, then deal the pool out to schemas. Allocating
    # per schema with a small budget (16) rounds the three smallest buckets to
    # zero and inflates the largest, so the quota would never be met.
    pool = [
        b
        for b, n in chart_types.allocate(args.per_schema * len(schemas)).items()
        for _ in range(n)
    ]
    rng.shuffle(pool)

    for si, schema in enumerate(schemas):
        wanted = pool[si * args.per_schema : (si + 1) * args.per_schema]
        hard_flags = [
            rng.choice(chart_types.HARD_CASE_KINDS)
            if rng.random() < chart_types.HARD_CASE_SHARE
            else None
            for _ in wanted
        ]
        spec = "\n".join(
            f"{i + 1}. chart shape: {bucket}"
            + (f", hard case: {hard}" if hard else "")
            for i, (bucket, hard) in enumerate(zip(wanted, hard_flags))
        )
        assignments[schema["schema_id"]] = list(zip(wanted, hard_flags))
        requests.append(
            client.json_request(
                custom_id=schema["schema_id"],
                model=client.HAIKU,
                system=SYSTEM,
                user=(
                    f"Table: {schema['table_name']} ({schema['domain']})\n"
                    f"columns: {json.dumps(schema['columns'], default=str)}\n\n"
                    f"Write exactly {len(wanted)} questions, one per line item below, "
                    f"returning them in the same order with the chart_bucket copied "
                    f"and hard_case set when given:\n{spec}"
                ),
                schema=SCHEMA,
                max_tokens=4096,
                effort="low",
            )
        )

    outcome = client.run_batch(requests, label="questions")
    cost = client.record_spend("questions", client.HAIKU, outcome.usage, {"requests": len(requests)})

    rows = []
    align = {"schemas": 0, "count_mismatch_schemas": 0, "items": 0, "echo_valid": 0, "echo_disagree": 0}
    for schema in schemas:
        payload = outcome.payloads.get(schema["schema_id"])
        if not payload:
            continue
        wanted = assignments[schema["schema_id"]]
        items = payload.get("questions", [])
        align["schemas"] += 1
        if len(items) != len(wanted):
            align["count_mismatch_schemas"] += 1
        for index, item in enumerate(items):
            text = (item.get("question") or "").strip()
            if len(text) < 8:
                continue
            pos_bucket, pos_hard = wanted[index] if index < len(wanted) else (None, None)
            echo = item.get("chart_bucket")
            align["items"] += 1
            if echo in chart_types.QUOTA:
                align["echo_valid"] += 1
                bucket = echo
                agree = pos_bucket is None or echo == pos_bucket
                if not agree:
                    align["echo_disagree"] += 1
            else:
                bucket = pos_bucket if pos_bucket in chart_types.QUOTA else "bar"
                agree = True
            echo_hard = item.get("hard_case")
            if echo_hard in chart_types.HARD_CASE_KINDS:
                hard = echo_hard
            else:
                hard = pos_hard if agree else None
            rows.append(
                {
                    "question_id": f"{schema['schema_id']}-q{index:02d}",
                    "schema_id": schema["schema_id"],
                    "split": schema["split"],
                    "question": text,
                    "chart_bucket": bucket,
                    "hard_case": hard,
                }
            )

    out = Path("data/questions.jsonl")
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "questions": len(rows),
        "by_split": dict(Counter(r["split"] for r in rows)),
        "by_bucket": dict(Counter(r["chart_bucket"] for r in rows).most_common()),
        "hard_case_share": round(sum(1 for r in rows if r["hard_case"]) / max(1, len(rows)), 3),
        "alignment": {
            **align,
            "count_mismatch_rate": round(align["count_mismatch_schemas"] / max(1, align["schemas"]), 4),
            "echo_disagree_rate": round(align["echo_disagree"] / max(1, align["echo_valid"]), 4),
        },
        "batch_cost_usd": cost,
        "refusals": int(outcome.refusals), "unparsed": int(outcome.unparsed), "errored": int(outcome.errored),
    }
    Path("runs").mkdir(exist_ok=True)
    Path("runs/questions_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
