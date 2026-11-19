#!/usr/bin/env python3
"""GATE: measure real token lengths before training. Run after the model download.

Why this exists. The dataset's sizing was estimated at chars/4, which understates
Python source -- code, punctuation, indentation and column names tokenise at
roughly 2.7-3.3 chars per token. The longest row is 5,359 chars, so between about
1,620 and 1,985 real tokens against a 2,048 limit. It straddles the boundary.

Why that is dangerous rather than merely untidy: if a row exceeds
--max-seq-length, mlx-lm silently truncates its tail. The tail is
`print(fig.to_json())` -- the one line the chartist contract requires. A
truncated row therefore teaches the model to omit it, and nothing errors.

Usage:
    .venv/bin/python check_token_lengths.py --model models/qwen3.5-9b-4bit
    .venv/bin/python check_token_lengths.py --model models/qwen3.5-9b-4bit --limit 2560

Exit code 0 means every row fits. Exit code 1 means at least one does not, and
the report names the worst offenders.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_tokenizer(model_path: str):
    """Load just the tokenizer, trying the cheapest route first.

    mlx-lm's internal module layout differs across versions, so this tries three
    routes rather than betting on one. The last resort loads the full model,
    which costs several GB of RAM but always works.
    """
    try:
        from mlx_lm.tokenizer_utils import load_tokenizer as _lt  # type: ignore

        return _lt(Path(model_path)), "mlx_lm.tokenizer_utils.load_tokenizer"
    except Exception:
        pass
    try:
        from transformers import AutoTokenizer  # type: ignore

        return AutoTokenizer.from_pretrained(model_path), "transformers.AutoTokenizer"
    except Exception:
        pass
    from mlx_lm import load  # type: ignore

    _model, tokenizer = load(model_path)
    return tokenizer, "mlx_lm.load (full model)"


def encoded_length(tokenizer, messages: list[dict]) -> int:
    """Token count as mlx-lm will see it, chat template included.

    The template matters: its control tokens are part of the sequence, and
    leaving them out is how an estimate ends up under the real number.
    """
    try:
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
        if isinstance(ids, dict):
            ids = ids.get("input_ids", [])
        if ids and isinstance(ids[0], (list, tuple)):
            ids = ids[0]
        return len(ids)
    except Exception:
        # No usable template: fall back to encoding the concatenated text and
        # add a small allowance for the role markers we could not render.
        text = "\n".join(m["content"] for m in messages)
        return len(tokenizer.encode(text)) + 16


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="path to the converted MLX model")
    parser.add_argument("--data", default="data/mlx")
    parser.add_argument("--limit", type=int, default=2560, help="the --max-seq-length you will train with")
    args = parser.parse_args()

    tokenizer, route = load_tokenizer(args.model)
    print(f"tokenizer loaded via {route}\n")

    worst: list[tuple[int, str, int]] = []
    failed = 0
    total_rows = 0

    for split in ("train", "valid"):
        path = Path(args.data) / f"{split}.jsonl"
        if not path.is_file():
            print(f"  {split:6s} MISSING at {path}")
            continue
        lengths = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            n = encoded_length(tokenizer, json.loads(line)["messages"])
            lengths.append(n)
            worst.append((n, split, index))
            if n > args.limit:
                failed += 1
        lengths.sort()
        total_rows += len(lengths)
        count = len(lengths)
        print(
            f"  {split:6s} n={count:5d}  "
            f"p50={lengths[count // 2]:5d}  "
            f"p90={lengths[int(count * 0.9)]:5d}  "
            f"p99={lengths[int(count * 0.99)]:5d}  "
            f"max={lengths[-1]:5d}"
        )

    worst.sort(reverse=True)
    print(f"\n  limit {args.limit}  |  rows over limit: {failed} of {total_rows}")
    print("\n  longest 5 rows:")
    for n, split, index in worst[:5]:
        marker = "  <-- OVER" if n > args.limit else ""
        print(f"    {n:5d} tokens  {split}.jsonl line {index + 1}{marker}")

    if failed:
        print(
            f"\nFAIL: {failed} row(s) exceed --max-seq-length {args.limit}.\n"
            "Raise --max-seq-length above the max above, or drop those rows.\n"
            "Do NOT train as-is: mlx-lm truncates the tail silently, which cuts\n"
            "the closing print(fig.to_json()) and teaches the model to omit it."
        )
        return 1

    headroom = args.limit - worst[0][0] if worst else 0
    print(f"\nPASS: every row fits, with {headroom} tokens of headroom. Safe to train.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
