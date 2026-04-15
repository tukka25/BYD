#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
from pathlib import Path

from pipeline.config import ensure_dirs, load_config
from pipeline.io_utils import extract_message, read_jsonl, stable_hash, write_jsonl
from pipeline.reporting import write_report


def add_ids(rows):
    out = []
    for row in rows:
        messages = row.get("messages", [])
        user = extract_message(messages, "user")
        assistant = extract_message(messages, "assistant")
        sid = stable_hash(user + "\n###\n" + assistant)
        out.append({
            "id": f"seed_{sid}",
            "kind": "real",
            "messages": messages,
            "meta": {"source": "seed"},
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="data-pipeline/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    ensure_dirs(cfg)

    train_rows_raw = read_jsonl(cfg["paths"]["seed_input"])
    train_rows = add_ids(train_rows_raw)

    eval_input = cfg["paths"].get("eval_input")
    split_mode = "random_holdout"
    holdout_ratio = float(cfg["split"]["holdout_ratio"])

    if eval_input:
        eval_rows_raw = read_jsonl(eval_input)
        eval_rows = add_ids(eval_rows_raw)
        split_mode = "fixed_eval_input"
    else:
        rng = random.Random(cfg["split"]["random_seed"])
        rng.shuffle(train_rows)

        holdout_n = round(len(train_rows) * holdout_ratio)
        eval_rows = train_rows[:holdout_n]
        train_rows = train_rows[holdout_n:]

    work_dir = Path(cfg["paths"]["work_dir"])
    write_jsonl(work_dir / "01_seed" / "train_seed.jsonl", train_rows)
    write_jsonl(work_dir / "01_seed" / "eval_seed.jsonl", eval_rows)

    write_report(
        work_dir / "01_seed" / "seed_manifest.json",
        {
            "split_mode": split_mode,
            "train_input_rows": len(train_rows_raw),
            "train_rows": len(train_rows),
            "eval_rows": len(eval_rows),
            "holdout_ratio": holdout_ratio,
            "eval_input": eval_input,
        },
    )

    print(f"Prepared seed set. train={len(train_rows)} eval={len(eval_rows)}")


if __name__ == "__main__":
    main()
