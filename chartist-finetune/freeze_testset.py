#!/usr/bin/env python3
"""Freeze the evaluation set. No gold answers: execution is the oracle.

Sampling is stratified by chart bucket (floor of 15 per bucket plus the remainder
allocated by chart_types.QUOTA), then round-robin across schemas within a bucket.

This set was re-frozen twice before any eval ran: once to add bucket stratification
(the first version under-sampled area and gauge), and a second time to correct a
schema-spread bug in the stratified selection. It must NOT be regenerated again
once eval numbers exist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from chart_types import QUOTA
from contract import CHARTIST_USER_TEMPLATE

BUCKET_FLOOR = 15


def bucket_targets(size: int) -> dict[str, int]:
    """Floor per bucket, remainder by QUOTA using largest-remainder rounding."""
    rest = size - BUCKET_FLOOR * len(QUOTA)
    assert rest >= 0, "size too small for the per-bucket floor"
    raw = {k: rest * v for k, v in QUOTA.items()}
    extra = {k: int(v) for k, v in raw.items()}
    order = sorted(QUOTA, key=lambda k: -(raw[k] - extra[k]))
    for k in order[: rest - sum(extra.values())]:
        extra[k] += 1
    targets = {k: BUCKET_FLOOR + extra[k] for k in QUOTA}
    assert sum(targets.values()) == size, (sum(targets.values()), size)
    return targets


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
    targets = bucket_targets(args.size)
    by_bucket: dict[str, dict[str, list]] = {}
    for q in questions:
        by_bucket.setdefault(q["chart_bucket"], {}).setdefault(q["schema_id"], []).append(q)
    picked = []
    schema_ids = sorted({q["schema_id"] for q in questions})
    random.Random(args.seed).shuffle(schema_ids)
    rank = {k: i for i, k in enumerate(schema_ids)}
    used = {k: 0 for k in schema_ids}
    for bucket, want in targets.items():
        pools = by_bucket.get(bucket, {})
        supply = sum(len(v) for v in pools.values())
        assert want <= supply, f"bucket {bucket}: target {want} exceeds supply {supply}"
        chosen = 0
        while chosen < want:
            # Round-robin within the bucket, least-used schemas (globally) first so
            # the whole set also spreads across as many schemas as possible.
            ready = [k for k in pools if pools[k]]
            ready.sort(key=lambda k: (used[k], rank[k]))
            for key in ready:
                if chosen < want:
                    picked.append(pools[key].pop())
                    used[key] += 1
                    chosen += 1
    random.Random(args.seed).shuffle(picked)

    assert len(picked) == args.size
    assert all(sum(1 for p in picked if p["chart_bucket"] == b) >= BUCKET_FLOOR for b in QUOTA)
    assert len({p["schema_id"] for p in picked}) >= 55, "schema spread too narrow"

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
