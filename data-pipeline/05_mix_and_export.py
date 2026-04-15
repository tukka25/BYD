#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.config import ensure_dirs, load_config
from pipeline.io_utils import read_jsonl, write_jsonl
from pipeline.mixing import select_mix
from pipeline.reporting import write_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="data-pipeline/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    ensure_dirs(cfg)
    work_dir = Path(cfg["paths"]["work_dir"])

    real_rows = read_jsonl(work_dir / "01_seed" / "train_seed.jsonl") if cfg["export"]["include_seed_rows"] else []
    rephrase_rows = read_jsonl(work_dir / "04_filtered" / "rephrases_clean.jsonl")
    aug_rows = read_jsonl(work_dir / "04_filtered" / "answer_aug_clean.jsonl")

    final_rows, stats = select_mix(real_rows, rephrase_rows, aug_rows, cfg)

    out_name = cfg["export"]["output_file"]
    out_path = work_dir / "05_final" / out_name
    write_jsonl(out_path, final_rows)

    write_report(
        work_dir / "05_final" / "mix_manifest.json",
        {
            **stats,
            "output_path": str(out_path),
            "available_rephrases": len(rephrase_rows),
            "available_answer_aug": len(aug_rows),
        },
    )

    print(f"Exported final dataset: {out_path}")
    print(stats)


if __name__ == "__main__":
    main()
