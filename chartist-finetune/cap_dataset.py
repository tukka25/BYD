#!/usr/bin/env python3
"""Write a length-capped copy of the MLX dataset by DROPPING over-length rows.

Why drop rather than truncate. mlx-lm's iterate_batches truncates any row longer
than --max-seq-length (trainer.py:166) and only warns. The tail of every row here
is `print(fig.to_json())`, the one line the chartist contract requires, so a
truncated row actively teaches the model to omit it. Dropping loses a row;
truncating corrupts it. Dropping is strictly better.

Why this exists at all: training OOMs on this machine well below the longest row.
Peak memory is dominated by per-token terms -- chiefly the logits tensor, which is
seq_len x 152k vocab and is NOT reduced by --grad-checkpoint -- so the only lever
that moves the ceiling is the longest sequence actually fed to the model.

Length is measured with the SAME function as the token gate, so "fits under the
cap" means the same thing in both places.

    .venv/bin/python cap_dataset.py --limit 1536 --out data/mlx_1536
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

from check_token_lengths import encoded_length, load_tokenizer


def load_meta() -> dict[str, dict]:
    """question_id -> {chart_bucket, hard_case}, so a drop report names what is lost."""
    meta: dict[str, dict] = {}
    for name in ("data/targets.jsonl", "data/docs_rows.jsonl"):
        path = Path(name)
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            qid = row.get("question_id")
            if qid:
                meta[qid] = {
                    "chart_bucket": row.get("chart_bucket", "?"),
                    "hard_case": row.get("hard_case") or "easy",
                }
    return meta


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/qwen3.5-9b-4bit")
    parser.add_argument("--data", default="data/mlx")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, required=True)
    args = parser.parse_args()

    tokenizer, route = load_tokenizer(args.model)
    print(f"tokenizer: {route}")
    meta = load_meta()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {"limit": args.limit, "source": args.data, "splits": {}}

    for split in ("train", "valid"):
        src = Path(args.data) / f"{split}.jsonl"
        src_fix = Path(args.data) / f"{split}_fixtures.jsonl"
        rows = [l for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
        fixes = [l for l in src_fix.read_text(encoding="utf-8").splitlines() if l.strip()]
        # These two files are positionally joined -- a filter that drops from one
        # and not the other silently corrupts every downstream fixture lookup.
        if len(rows) != len(fixes):
            raise SystemExit(
                f"{split}: {len(rows)} rows but {len(fixes)} fixtures -- refusing to filter "
                "positionally aligned files of different lengths"
            )

        kept_rows, kept_fixes = [], []
        dropped = []
        for row_line, fix_line in zip(rows, fixes):
            n = encoded_length(tokenizer, json.loads(row_line)["messages"])
            if n <= args.limit:
                kept_rows.append(row_line)
                kept_fixes.append(fix_line)
            else:
                qid = json.loads(fix_line).get("question_id", "?")
                info = meta.get(qid, {"chart_bucket": "?", "hard_case": "?"})
                dropped.append({"question_id": qid, "tokens": n, **info})

        (out_dir / f"{split}.jsonl").write_text("\n".join(kept_rows) + "\n", encoding="utf-8")
        (out_dir / f"{split}_fixtures.jsonl").write_text("\n".join(kept_fixes) + "\n", encoding="utf-8")

        pct = 100.0 * len(dropped) / max(1, len(rows))
        print(f"\n  {split}: kept {len(kept_rows)} of {len(rows)}, dropped {len(dropped)} ({pct:.2f}%)")
        if dropped:
            buckets = Counter(d["chart_bucket"] for d in dropped)
            hards = Counter(d["hard_case"] for d in dropped)
            print(f"    buckets hit: {dict(buckets.most_common())}")
            print(f"    hard cases:  {dict(hards.most_common())}")
            print(f"    longest dropped: {max(d['tokens'] for d in dropped)} tokens")
        summary["splits"][split] = {
            "kept": len(kept_rows),
            "dropped": len(dropped),
            "dropped_pct": round(pct, 3),
            "dropped_rows": dropped,
        }

    manifest = Path(args.data) / "split_manifest.json"
    if manifest.is_file():
        shutil.copy(manifest, out_dir / "split_manifest.json")
    (out_dir / "cap_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    train_kept = summary["splits"]["train"]["kept"]
    print(f"\nwrote {out_dir}")
    print(f"  one epoch at --batch-size 1 is {train_kept} iters; two epochs is {train_kept * 2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
