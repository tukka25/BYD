#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from pipeline.config import ensure_dirs, load_config
from pipeline.io_utils import extract_message, read_jsonl, stable_hash, write_jsonl
from pipeline.llm_client import LLMClient, LLMSettings
from pipeline.prompts import REPHRASE_SYSTEM_PROMPT, REPHRASE_USER_TEMPLATE
from pipeline.rate_limiter import RequestsPerMinuteLimiter


def build_settings(cfg):
    return LLMSettings(
        rephrase_model=cfg["models"]["rephrase_model"],
        answer_aug_model=cfg["models"]["answer_aug_model"],
        fallback_model=cfg["models"]["fallback_model"],
        temperature_rephrase=float(cfg["openai"]["temperature_rephrase"]),
        temperature_answer_aug=float(cfg["openai"]["temperature_answer_aug"]),
        max_tokens_rephrase=int(cfg["openai"]["max_tokens_rephrase"]),
        max_tokens_answer_aug=int(cfg["openai"]["max_tokens_answer_aug"]),
        max_generation_retries=int(cfg["generation"]["max_generation_retries"]),
    )


def plan_indices(n_rows: int, target_n: int):
    idx = []
    i = 0
    while len(idx) < target_n:
        idx.append(i % n_rows)
        i += 1
    return idx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="data-pipeline/config.yaml")
    parser.add_argument("--max-rephrases", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--max-rpm", type=int, default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    ensure_dirs(cfg)

    work_dir = Path(cfg["paths"]["work_dir"])
    seed_rows = read_jsonl(work_dir / "01_seed" / "train_seed.jsonl")

    synth_per_seed = float(cfg["generation"]["target_synth_per_seed"])
    rephrase_ratio = float(cfg["generation"]["rephrase_ratio"])
    target_rephrase = round(len(seed_rows) * synth_per_seed * rephrase_ratio)
    cfg_test_max = cfg["generation"].get("test_max_rephrases")
    if cfg_test_max is not None:
        target_rephrase = min(target_rephrase, int(cfg_test_max))
    if args.max_rephrases is not None:
        target_rephrase = min(target_rephrase, int(args.max_rephrases))

    workers = int(args.workers if args.workers is not None else cfg["generation"].get("rephrase_workers", 4))
    rpm = args.max_rpm if args.max_rpm is not None else cfg["openai"].get("max_requests_per_minute")
    rpm = None if rpm is None else int(rpm)

    if target_rephrase <= 0:
        write_jsonl(work_dir / "02_rephrases" / "raw_rephrases.jsonl", [])
        write_jsonl(work_dir / "02_rephrases" / "rephrase_failures.jsonl", [])
        print("Generated rephrases: 0, failures: 0, target=0")
        return

    limiter = RequestsPerMinuteLimiter(rpm)
    llm = LLMClient(build_settings(cfg), request_gate=limiter.acquire)

    outputs = []
    failures = []
    planned = list(enumerate(plan_indices(len(seed_rows), target_rephrase), start=1))

    def run_one(seq: int, seed_idx: int):
        seed = seed_rows[seed_idx]
        messages = seed["messages"]
        system = extract_message(messages, "system")
        user = extract_message(messages, "user")
        assistant = extract_message(messages, "assistant")

        prompt = REPHRASE_USER_TEMPLATE.format(
            original_user=user,
            original_answer_code=assistant,
        )
        rephrased = llm.generate_rephrase(REPHRASE_SYSTEM_PROMPT, prompt)
        rid = stable_hash(f"{seed['id']}::rephrase::{seq}::{rephrased}")

        return {
            "seq": seq,
            "seed_id": seed["id"],
            "row": {
                "id": f"rephrase_{rid}",
                "kind": "rephrase",
                "source_id": seed["id"],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": rephrased},
                    {"role": "assistant", "content": assistant},
                ],
                "meta": {
                    "original_user": user,
                    "seq": seq,
                },
            },
        }

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        future_map = {ex.submit(run_one, seq, seed_idx): (seq, seed_idx) for seq, seed_idx in planned}
        for fut in tqdm(as_completed(future_map), total=len(future_map), desc="Rephrasing"):
            seq, seed_idx = future_map[fut]
            try:
                result = fut.result()
                outputs.append(result["row"])
            except Exception as e:  # noqa: BLE001
                failures.append({
                    "seed_id": seed_rows[seed_idx]["id"],
                    "seq": seq,
                    "kind": "rephrase_generation_failed",
                    "error": str(e),
                })

    outputs.sort(key=lambda x: int(x.get("meta", {}).get("seq", 0)))

    write_jsonl(work_dir / "02_rephrases" / "raw_rephrases.jsonl", outputs)
    write_jsonl(work_dir / "02_rephrases" / "rephrase_failures.jsonl", failures)
    print(
        f"Generated rephrases: {len(outputs)}, failures: {len(failures)}, target={target_rephrase}, "
        f"workers={workers}, max_rpm={rpm if rpm is not None else 'unlimited'}"
    )


if __name__ == "__main__":
    main()
