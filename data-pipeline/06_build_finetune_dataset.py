#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.config import ensure_dirs, load_config
from pipeline.io_utils import read_jsonl, write_jsonl
from pipeline.reporting import write_report

REQUIRED_ROLES = ("system", "user", "assistant")


def normalize_messages(messages):
    if not isinstance(messages, list):
        return None, ["messages_not_list"]

    by_role = {}
    for item in messages:
        role = item.get("role")
        content = item.get("content")
        if role in REQUIRED_ROLES and isinstance(content, str) and content.strip():
            by_role[role] = content

    missing = [r for r in REQUIRED_ROLES if r not in by_role]
    if missing:
        return None, [f"missing_roles:{','.join(missing)}"]

    normalized = [{"role": r, "content": by_role[r]} for r in REQUIRED_ROLES]
    return normalized, []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="data-pipeline/config.yaml")
    parser.add_argument(
        "--input",
        default=None,
        help="Input mixed dataset JSONL. Defaults to 05_final output from config.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output finetune JSONL path. Defaults to runs/default/06_finetune/plotly_qwen_finetune.jsonl",
    )
    parser.add_argument(
        "--keep-metadata",
        action="store_true",
        help="Keep id/kind/source/meta fields in output rows.",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    ensure_dirs(cfg)

    work_dir = Path(cfg["paths"]["work_dir"])
    default_in = work_dir / "05_final" / cfg["export"]["output_file"]
    input_path = Path(args.input) if args.input else default_in

    default_out = work_dir / "06_finetune" / "plotly_qwen_finetune.jsonl"
    output_path = Path(args.output) if args.output else default_out

    rows = read_jsonl(input_path)
    out_rows = []
    rejects = []

    for i, row in enumerate(rows, start=1):
        messages, reasons = normalize_messages(row.get("messages"))
        if reasons:
            rejects.append({"line": i, "reasons": reasons, "id": row.get("id")})
            continue

        if args.keep_metadata:
            out = dict(row)
            out["messages"] = messages
            out_rows.append(out)
        else:
            out_rows.append({"messages": messages})

    write_jsonl(output_path, out_rows)

    reject_path = output_path.parent / f"{output_path.stem}_rejects.jsonl"
    write_jsonl(reject_path, rejects)

    manifest = {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "keep_metadata": args.keep_metadata,
        "input_rows": len(rows),
        "output_rows": len(out_rows),
        "rejected_rows": len(rejects),
        "rejects_path": str(reject_path),
    }
    write_report(output_path.parent / f"{output_path.stem}_manifest.json", manifest)

    print(f"Built finetune dataset: {output_path}")
    print(manifest)


if __name__ == "__main__":
    main()
