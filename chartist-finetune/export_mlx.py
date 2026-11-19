#!/usr/bin/env python3
"""Merge verified targets with the docs base layer and export schema-disjoint splits."""
from __future__ import annotations

import argparse
import json
import random
from contract import CHARTIST_SYSTEM_PROMPT
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", default=["data/targets.jsonl", "data/docs_rows.jsonl"])
    parser.add_argument("--out-dir", default="data/mlx")
    parser.add_argument("--valid-ratio", type=float, default=0.08)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    grouped: dict[str, list[dict]] = defaultdict(list)
    for name in args.inputs:
        path = Path(name)
        if not path.is_file():
            print(f"skipping missing {path}")
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                row = json.loads(line)
                grouped[row["schema_id"]].append(row)

    frozen_test = {
        json.loads(l)["schema_id"]
        for l in Path("data/testset.jsonl").read_text(encoding="utf-8").splitlines()
        if l
    }
    leaked = set(grouped) & frozen_test
    if leaked:
        raise SystemExit(f"LEAK: these schemas are in the frozen test set: {sorted(leaked)[:5]}")

    all_rows = [r for k in grouped for r in grouped[k]]
    n_sys = {r["messages"][0]["content"] for r in all_rows}
    if len(n_sys) != 1 or CHARTIST_SYSTEM_PROMPT not in n_sys:
        raise SystemExit(f"system prompt not unique/canonical: {len(n_sys)} distinct")
    for r in all_rows:
        if [m["role"] for m in r["messages"]] != ["system", "user", "assistant"]:
            raise SystemExit(f"bad roles in {r['question_id']}")

    keys = sorted(grouped)
    random.Random(args.seed).shuffle(keys)
    n_valid = max(1, int(len(keys) * args.valid_ratio))
    splits = {"valid": keys[:n_valid], "train": keys[n_valid:]}

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"seed": args.seed, "counts": {}, "schema_ids": {}, "sources": {}}

    for split, split_keys in splits.items():
        rows = [row for key in split_keys for row in grouped[key]]
        random.Random(args.seed).shuffle(rows)
        with (out_dir / f"{split}.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps({"messages": row["messages"]}, ensure_ascii=False) + "\n")
        with (out_dir / f"{split}_fixtures.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps({"schema_id": row["schema_id"], "question_id": row["question_id"], "fixture_csv": row["fixture_csv"]}) + "\n")
        manifest["counts"][split] = len(rows)
        manifest["schema_ids"][split] = sorted(split_keys)
        manifest["sources"][split] = dict(Counter("docs" if r["schema_id"].startswith("docs-") else "synthetic" for r in rows))

    assert not set(splits["train"]) & set(splits["valid"]), "train/valid overlap"
    (out_dir / "split_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"counts": manifest["counts"], "sources": manifest["sources"]}, indent=2))


if __name__ == "__main__":
    main()
