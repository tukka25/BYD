#!/usr/bin/env python3
"""Build Qwen-compatible fine-tuning dataset from scraped Plotly JSONL."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SKIP_SECTION_PATTERNS = (
    "imports",
    "reference",
    "api reference",
)

PROMPT_TEMPLATES = (
    "Create a {graph_name} example in Plotly Python. {section_hint}{description_hint}Return only executable Python code.",
    "Can you create a {graph_name} chart using Plotly Python? {section_hint}{description_hint}Return only Python code.",
    "Build a Plotly Python {graph_name} visualization. {section_hint}{description_hint}Provide only the code.",
)


@dataclass
class BuildConfig:
    input_path: Path
    output_dir: Path
    seed: int
    val_ratio: float
    min_code_chars: int
    include_system: bool


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_title(text: str) -> str:
    text = text or ""
    text = text.replace("¶", "")
    return normalize_ws(text)


def slug_to_words(slug: str) -> str:
    s = (slug or "").strip().lower()
    s = s.replace("-in-python", "")
    s = s.replace("-", " ")
    s = normalize_ws(s)
    return s or "plot"


def should_skip_section(section_title: str) -> str | None:
    lowered = section_title.lower()
    for pattern in SKIP_SECTION_PATTERNS:
        if pattern in lowered:
            return f"skip_section:{pattern}"
    return None


def select_code_block(code_blocks: Any) -> str:
    if not isinstance(code_blocks, list):
        return ""
    for block in code_blocks:
        if not isinstance(block, str):
            continue
        candidate = block.strip()
        if candidate and ("plotly" in candidate.lower() or "fig" in candidate.lower()):
            return candidate
    return ""


def detect_library(row: dict[str, Any], code: str) -> str:
    libs = row.get("libraries_detected") or []
    if isinstance(libs, list):
        if "plotly.express" in libs:
            return "plotly.express"
        if "plotly.graph_objects" in libs:
            return "plotly.graph_objects"
    lower = code.lower()
    if "plotly.express" in lower or " px." in lower:
        return "plotly.express"
    if "plotly.graph_objects" in lower or " go." in lower:
        return "plotly.graph_objects"
    return "plotly"


def build_user_prompt(row: dict[str, Any], idx: int) -> str:
    graph_name = slug_to_words(str(row.get("graph_type", "")))
    section = clean_title(str(row.get("section_title", "")))
    description = clean_title(str(row.get("description", "")))

    section_hint = ""
    if section and section.lower() not in {"", "overview", "what about dash?"}:
        section_hint = f"Focus on: {section}. "

    description_hint = ""
    if description:
        description_hint = f"Details: {description}. "

    template = PROMPT_TEMPLATES[idx % len(PROMPT_TEMPLATES)]
    return normalize_ws(
        template.format(
            graph_name=graph_name,
            section_hint=section_hint,
            description_hint=description_hint,
        )
    )


def make_record(prompt: str, code: str, include_system: bool) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if include_system:
        messages.append(
            {
                "role": "system",
                "content": "You are a Plotly Python coding assistant. Return only executable Python code.",
            }
        )
    messages.append({"role": "user", "content": prompt})
    messages.append({"role": "assistant", "content": code})
    return {"messages": messages}


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stratified_split(
    items: list[dict[str, Any]],
    val_ratio: float,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_graph: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_graph[item["graph_type"]].append(item)

    rng = random.Random(seed)
    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []

    for _, group in by_graph.items():
        rng.shuffle(group)
        n_val = max(1, int(round(len(group) * val_ratio))) if len(group) >= 5 else 1 if len(group) >= 2 else 0
        val.extend(group[:n_val])
        train.extend(group[n_val:])

    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def run(config: BuildConfig) -> None:
    rows = []
    with config.input_path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append((i, json.loads(line)))
            except json.JSONDecodeError:
                rows.append((i, {"__invalid_json__": True}))

    mapping_rows: list[dict[str, Any]] = []
    cleaned_samples: list[dict[str, Any]] = []
    drop_reasons = Counter()
    graph_counter = Counter()
    lib_counter = Counter()

    seen_code_hashes = set()

    for src_line, row in rows:
        page_url = str(row.get("page_url", ""))
        graph_type = str(row.get("graph_type", "unknown"))
        section_title = clean_title(str(row.get("section_title", "")))

        mapping_base = {
            "source_line": src_line,
            "source_url": page_url,
            "graph_type": graph_type,
            "section_title": section_title,
            "kept": False,
            "drop_reason": None,
            "sample_id": None,
            "split": None,
            "library": None,
        }

        if row.get("__invalid_json__"):
            mapping_base["drop_reason"] = "invalid_json"
            drop_reasons["invalid_json"] += 1
            mapping_rows.append(mapping_base)
            continue

        if not page_url:
            mapping_base["drop_reason"] = "missing_page_url"
            drop_reasons["missing_page_url"] += 1
            mapping_rows.append(mapping_base)
            continue

        if not graph_type:
            mapping_base["drop_reason"] = "missing_graph_type"
            drop_reasons["missing_graph_type"] += 1
            mapping_rows.append(mapping_base)
            continue

        section_skip = should_skip_section(section_title)
        if section_skip:
            mapping_base["drop_reason"] = section_skip
            drop_reasons[section_skip] += 1
            mapping_rows.append(mapping_base)
            continue

        code = select_code_block(row.get("code_blocks"))
        if not code:
            mapping_base["drop_reason"] = "missing_code"
            drop_reasons["missing_code"] += 1
            mapping_rows.append(mapping_base)
            continue

        if len(code.strip()) < config.min_code_chars:
            mapping_base["drop_reason"] = "code_too_short"
            drop_reasons["code_too_short"] += 1
            mapping_rows.append(mapping_base)
            continue

        code_hash = stable_hash(normalize_ws(code))
        if code_hash in seen_code_hashes:
            mapping_base["drop_reason"] = "duplicate_code"
            drop_reasons["duplicate_code"] += 1
            mapping_rows.append(mapping_base)
            continue
        seen_code_hashes.add(code_hash)

        prompt = build_user_prompt(row, idx=src_line)
        library = detect_library(row, code)

        sample = {
            "sample_id": f"plotly_{len(cleaned_samples)+1:06d}",
            "graph_type": graph_type,
            "page_url": page_url,
            "section_title": section_title,
            "library": library,
            "prompt": prompt,
            "code": code,
            "record": make_record(prompt=prompt, code=code, include_system=config.include_system),
        }
        cleaned_samples.append(sample)
        graph_counter[graph_type] += 1
        lib_counter[library] += 1

        mapping_base["kept"] = True
        mapping_base["sample_id"] = sample["sample_id"]
        mapping_base["library"] = library
        mapping_rows.append(mapping_base)

    train_rows, val_rows = stratified_split(cleaned_samples, config.val_ratio, config.seed)

    train_ids = {row["sample_id"] for row in train_rows}
    val_ids = {row["sample_id"] for row in val_rows}
    for m in mapping_rows:
        sid = m.get("sample_id")
        if not sid:
            continue
        if sid in train_ids:
            m["split"] = "train"
        elif sid in val_ids:
            m["split"] = "val"

    config.output_dir.mkdir(parents=True, exist_ok=True)
    train_path = config.output_dir / "plotly_qwen_train.jsonl"
    val_path = config.output_dir / "plotly_qwen_val.jsonl"
    mapping_path = config.output_dir / "plotly_qwen_mapping.jsonl"
    stats_path = config.output_dir / "plotly_qwen_stats.json"

    with train_path.open("w", encoding="utf-8") as f:
        for row in train_rows:
            f.write(json.dumps(row["record"], ensure_ascii=False) + "\n")

    with val_path.open("w", encoding="utf-8") as f:
        for row in val_rows:
            f.write(json.dumps(row["record"], ensure_ascii=False) + "\n")

    with mapping_path.open("w", encoding="utf-8") as f:
        for row in mapping_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    stats = {
        "input_path": str(config.input_path),
        "total_input_rows": len(rows),
        "kept_rows": len(cleaned_samples),
        "dropped_rows": len(rows) - len(cleaned_samples),
        "train_rows": len(train_rows),
        "val_rows": len(val_rows),
        "val_ratio": config.val_ratio,
        "seed": config.seed,
        "min_code_chars": config.min_code_chars,
        "drop_reasons": dict(drop_reasons),
        "graph_type_counts": dict(graph_counter.most_common()),
        "library_counts": dict(lib_counter.most_common()),
        "outputs": {
            "train": str(train_path),
            "val": str(val_path),
            "mapping": str(mapping_path),
            "stats": str(stats_path),
        },
    }

    with stats_path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(json.dumps(stats, ensure_ascii=False, indent=2))


def parse_args() -> BuildConfig:
    parser = argparse.ArgumentParser(description="Build Qwen dataset from Plotly scraper output")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("plotly_examples.jsonl"),
        help="Path to scraped Plotly JSONL",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dataset"),
        help="Output directory",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--min-code-chars", type=int, default=120)
    parser.add_argument(
        "--no-system",
        action="store_true",
        help="Disable system message in messages format",
    )

    args = parser.parse_args()
    return BuildConfig(
        input_path=args.input,
        output_dir=args.output_dir,
        seed=args.seed,
        val_ratio=args.val_ratio,
        min_code_chars=args.min_code_chars,
        include_system=not args.no_system,
    )


if __name__ == "__main__":
    run(parse_args())
