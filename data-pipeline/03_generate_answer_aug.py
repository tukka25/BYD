#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from pipeline.config import ensure_dirs, load_config
from pipeline.io_utils import extract_message, read_jsonl, stable_hash, write_jsonl
from pipeline.llm_client import LLMClient, LLMSettings
from pipeline.prompts import ANSWER_AUG_SYSTEM_PROMPT, ANSWER_AUG_USER_TEMPLATE
from pipeline.rate_limiter import RequestsPerMinuteLimiter
from pipeline.validators import validate_python_plotly_code


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


def build_repair_prompt(base_prompt: str, invalid_code: str, reasons: list[str], attempt: int) -> str:
    reason_text = ", ".join(reasons) if reasons else "unknown_validation_error"
    return (
        f"{base_prompt}\n\n"
        f"[Validation Feedback]\n"
        f"Previous candidate failed validation on attempt {attempt} with reasons: {reason_text}.\n"
        f"Fix these issues and regenerate a fully valid Plotly Python solution.\n"
        f"Return only executable Python code.\n\n"
        f"[Previous Invalid Candidate]\n"
        f"<invalid_code>\n{invalid_code}\n</invalid_code>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="data-pipeline/config.yaml")
    parser.add_argument("--max-answer-aug", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--max-rpm", type=int, default=None)
    parser.add_argument("--regen-attempts", type=int, default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    ensure_dirs(cfg)

    work_dir = Path(cfg["paths"]["work_dir"])
    seed_rows = read_jsonl(work_dir / "01_seed" / "train_seed.jsonl")

    synth_per_seed = float(cfg["generation"]["target_synth_per_seed"])
    rephrase_ratio = float(cfg["generation"]["rephrase_ratio"])
    target_synth = round(len(seed_rows) * synth_per_seed)
    target_answer_aug = target_synth - round(target_synth * rephrase_ratio)
    cfg_test_max = cfg["generation"].get("test_max_answer_aug")
    if cfg_test_max is not None:
        target_answer_aug = min(target_answer_aug, int(cfg_test_max))
    if args.max_answer_aug is not None:
        target_answer_aug = min(target_answer_aug, int(args.max_answer_aug))

    workers = int(args.workers if args.workers is not None else cfg["generation"].get("answer_aug_workers", 4))
    rpm = args.max_rpm if args.max_rpm is not None else cfg["openai"].get("max_requests_per_minute")
    rpm = None if rpm is None else int(rpm)

    regen_attempts = args.regen_attempts
    if regen_attempts is None:
        regen_attempts = int(cfg["generation"].get("answer_aug_validation_regen_attempts", 2))
    regen_attempts = max(0, int(regen_attempts))

    if target_answer_aug <= 0:
        write_jsonl(work_dir / "03_answer_aug" / "raw_answer_aug.jsonl", [])
        write_jsonl(work_dir / "03_answer_aug" / "answer_aug_failures.jsonl", [])
        print("Generated answer augmentations: 0, failures: 0, target=0")
        return

    limiter = RequestsPerMinuteLimiter(rpm)
    llm = LLMClient(build_settings(cfg), request_gate=limiter.acquire)

    outputs = []
    failures = []
    planned = list(enumerate(plan_indices(len(seed_rows), target_answer_aug), start=1))

    def run_one(seq: int, seed_idx: int):
        seed = seed_rows[seed_idx]
        messages = seed["messages"]
        system = extract_message(messages, "system")
        user = extract_message(messages, "user")
        assistant = extract_message(messages, "assistant")

        base_prompt = ANSWER_AUG_USER_TEMPLATE.format(
            original_user=user,
            original_answer_code=assistant,
        )

        prompt = base_prompt
        final_code = ""
        final_reasons: list[str] = []
        attempts_used = 0

        for attempt in range(1, regen_attempts + 2):
            attempts_used = attempt
            candidate = llm.generate_answer_aug(ANSWER_AUG_SYSTEM_PROMPT, prompt)
            ok, reasons = validate_python_plotly_code(candidate, cfg)
            if ok:
                final_code = candidate
                final_reasons = []
                break

            final_reasons = reasons
            prompt = build_repair_prompt(base_prompt, candidate, reasons, attempt)

        if not final_code:
            raise RuntimeError(
                "validation_failed_after_regen"
                f"|attempts={attempts_used}|reasons={','.join(final_reasons)}"
            )

        rid = stable_hash(f"{seed['id']}::answer_aug::{seq}::{final_code}")

        return {
            "seq": seq,
            "seed_id": seed["id"],
            "row": {
                "id": f"answer_aug_{rid}",
                "kind": "answer_aug",
                "source_id": seed["id"],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": final_code},
                ],
                "meta": {
                    "seq": seq,
                    "validation_regen_attempts_used": attempts_used,
                },
            },
        }

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        future_map = {ex.submit(run_one, seq, seed_idx): (seq, seed_idx) for seq, seed_idx in planned}
        for fut in tqdm(as_completed(future_map), total=len(future_map), desc="Answer Aug"):
            seq, seed_idx = future_map[fut]
            try:
                result = fut.result()
                outputs.append(result["row"])
            except Exception as e:  # noqa: BLE001
                failures.append({
                    "seed_id": seed_rows[seed_idx]["id"],
                    "seq": seq,
                    "kind": "answer_aug_generation_failed",
                    "error": str(e),
                })

    outputs.sort(key=lambda x: int(x.get("meta", {}).get("seq", 0)))

    write_jsonl(work_dir / "03_answer_aug" / "raw_answer_aug.jsonl", outputs)
    write_jsonl(work_dir / "03_answer_aug" / "answer_aug_failures.jsonl", failures)
    print(
        f"Generated answer augmentations: {len(outputs)}, failures: {len(failures)}, "
        f"target={target_answer_aug}, workers={workers}, max_rpm={rpm if rpm is not None else 'unlimited'}, "
        f"regen_attempts={regen_attempts}"
    )


if __name__ == "__main__":
    main()
