#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.config import ensure_dirs, load_config
from pipeline.io_utils import extract_message, read_jsonl, write_jsonl
from pipeline.reporting import write_report
from pipeline.validators import (
    is_duplicate_pair,
    seed_seen_pairs,
    validate_python_plotly_code,
    validate_rephrase,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="data-pipeline/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    ensure_dirs(cfg)
    work_dir = Path(cfg["paths"]["work_dir"])

    seed_rows = read_jsonl(work_dir / "01_seed" / "train_seed.jsonl")
    raw_rephrase = read_jsonl(work_dir / "02_rephrases" / "raw_rephrases.jsonl")
    raw_aug = read_jsonl(work_dir / "03_answer_aug" / "raw_answer_aug.jsonl")

    seen_pairs = set()
    seed_seen_pairs(seed_rows, seen_pairs)

    clean_rephrase = []
    clean_aug = []
    rejects = []

    for row in raw_rephrase:
        messages = row.get("messages", [])
        user = extract_message(messages, "user")
        assistant = extract_message(messages, "assistant")
        original_user = row.get("meta", {}).get("original_user", "")

        ok, reasons = validate_rephrase(original_user, user, cfg)
        if ok and is_duplicate_pair(user, assistant, seen_pairs):
            ok = False
            reasons.append("duplicate_pair")

        if ok:
            clean_rephrase.append(row)
        else:
            rejects.append({"id": row.get("id"), "kind": "rephrase", "reasons": reasons})

    for row in raw_aug:
        messages = row.get("messages", [])
        user = extract_message(messages, "user")
        assistant = extract_message(messages, "assistant")

        ok, reasons = validate_python_plotly_code(assistant, cfg)
        if ok and is_duplicate_pair(user, assistant, seen_pairs):
            ok = False
            reasons.append("duplicate_pair")

        if ok:
            clean_aug.append(row)
        else:
            rejects.append({"id": row.get("id"), "kind": "answer_aug", "reasons": reasons})

    write_jsonl(work_dir / "04_filtered" / "rephrases_clean.jsonl", clean_rephrase)
    write_jsonl(work_dir / "04_filtered" / "answer_aug_clean.jsonl", clean_aug)
    write_jsonl(work_dir / "04_filtered" / "rejects.jsonl", rejects)

    write_report(
        work_dir / "04_filtered" / "filter_report.json",
        {
            "raw_rephrases": len(raw_rephrase),
            "raw_answer_aug": len(raw_aug),
            "clean_rephrases": len(clean_rephrase),
            "clean_answer_aug": len(clean_aug),
            "rejected": len(rejects),
        },
    )

    print(
        "Filtering done. "
        f"clean_rephrases={len(clean_rephrase)} clean_answer_aug={len(clean_aug)} rejected={len(rejects)}"
    )


if __name__ == "__main__":
    main()
