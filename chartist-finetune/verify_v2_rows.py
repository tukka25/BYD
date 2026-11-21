#!/usr/bin/env python3
"""Check every v2 row the way the trainer will see it, before renting a GPU.

cloud/train_lora.py masks the prompt by splitting the rendered chat on TEXT and
skips any row whose full render does not start with its prompt render. This
runs the same check with the real tokenizer and reports token lengths, so a
row the trainer would silently skip is found here instead of on a pod.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from check_token_lengths import encoded_length, load_tokenizer


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/mlx_v2")
    ap.add_argument("--model", default="models/qwen3.5-9b-4bit")
    args = ap.parse_args()
    tokenizer, route = load_tokenizer(args.model)
    print(f"tokenizer: {route}")
    failed = False
    for split in ("train", "valid"):
        lengths, mismatched = [], 0
        for line in (Path(args.data) / f"{split}.jsonl").read_text(encoding="utf-8").splitlines():
            messages = json.loads(line)["messages"]
            full = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
            prompt = tokenizer.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True)
            if not full.startswith(prompt):
                mismatched += 1
            # The same count cap_dataset.py caps on.
            lengths.append(encoded_length(tokenizer, messages))
        lengths.sort()

        def pick(q: float) -> int:
            return lengths[min(len(lengths) - 1, int(q * len(lengths)))]

        print(f"{split}: {len(lengths)} rows, prefix mismatches {mismatched}, tokens p50 {pick(0.5)} "
              f"p95 {pick(0.95)} p99 {pick(0.99)} max {lengths[-1]}, "
              f"over 1536: {sum(l > 1536 for l in lengths)}, over 2048: {sum(l > 2048 for l in lengths)}, "
              f"over 3072: {sum(l > 3072 for l in lengths)}")
        failed = failed or mismatched > 0
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
