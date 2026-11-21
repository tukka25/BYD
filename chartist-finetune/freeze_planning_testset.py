#!/usr/bin/env python3
"""Lock the planning test set before any v2 training data exists.

One written request and the empty request for each of the 60 test-split
schemas. Like data/testset.jsonl for the chartist, it has no answers: the
planning eval scores plans by checking them against the real tables and by
drawing them. This script refuses to overwrite an existing set.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SOURCE = Path("data/v2/requests.jsonl")
TESTSET = Path("data/v2/planning_testset.jsonl")
DIGEST = Path("data/v2/planning_testset.sha256")


def select(rows: list[dict]) -> list[dict]:
    kept: list[dict] = []
    written: set[str] = set()
    empty: set[str] = set()
    for row in rows:
        if row["split"] != "test":
            continue
        if row["request"] and row["schema_id"] not in written:
            written.add(row["schema_id"])
            kept.append(row)
        elif not row["request"] and row["schema_id"] not in empty:
            empty.add(row["schema_id"])
            kept.append(row)
    return kept


def main() -> int:
    if TESTSET.exists():
        raise SystemExit(f"refusing to overwrite the frozen planning test set {TESTSET}")
    rows = [json.loads(l) for l in SOURCE.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept = select(rows)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in kept)
    TESTSET.write_text(text, encoding="utf-8")
    DIGEST.write_text(hashlib.sha256(text.encode("utf-8")).hexdigest() + "\n", encoding="utf-8")
    print(f"froze {len(kept)} rows from {len({r['schema_id'] for r in kept})} test schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
