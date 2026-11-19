#!/usr/bin/env python3
"""Freeze the evaluation set. No gold answers: execution is the oracle."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from contract import CHARTIST_USER_TEMPLATE


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=300)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    out = Path("data/testset.jsonl")
    if out.is_file():
        raise SystemExit(
            f"{out} already exists and is frozen. Delete it deliberately if you really "
            "mean to rebuild the eval, and know that every prior eval number becomes "
            "incomparable."
        )

    schemas = {
        r["schema_id"]: r
        for r in (json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)
    }
    questions = [
        r
        for r in (json.loads(l) for l in Path("data/questions.jsonl").read_text(encoding="utf-8").splitlines() if l)
        if r["split"] == "test"
    ]

    import random

    random.Random(args.seed).shuffle(questions)
    # Spread across schemas: round-robin so no schema dominates the eval.
    by_schema: dict[str, list] = {}
    for q in questions:
        by_schema.setdefault(q["schema_id"], []).append(q)
    picked = []
    while len(picked) < args.size and any(by_schema.values()):
        for key in list(by_schema):
            if not by_schema[key]:
                continue
            picked.append(by_schema[key].pop())
            if len(picked) >= args.size:
                break

    rows = []
    for index, q in enumerate(picked):
        schema = schemas[q["schema_id"]]
        rows.append(
            {
                "test_id": f"t{index:04d}",
                "schema_id": q["schema_id"],
                "question": q["question"],
                "chart_bucket": q["chart_bucket"],
                "hard_case": q["hard_case"],
                "fixture_csv": schema["fixture_csv"],
                "prompt": CHARTIST_USER_TEMPLATE.format(
                    task=q["question"],
                    columns=schema["pandas_columns"],
                    dtypes=schema["pandas_dtypes"],
                    sample_rows=schema["sample_rows"],
                ),
            }
        )

    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    Path("data/testset.sha256").write_text(digest + "\n", encoding="utf-8")

    print(json.dumps(
        {
            "rows": len(rows),
            "distinct_schemas": len({r["schema_id"] for r in rows}),
            "by_bucket": dict(Counter(r["chart_bucket"] for r in rows).most_common()),
            "hard_cases": sum(1 for r in rows if r["hard_case"]),
            "sha256": digest[:16],
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
