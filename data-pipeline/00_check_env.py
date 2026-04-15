#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path

from pipeline.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="data-pipeline/config.yaml")
    args = parser.parse_args()

    failures = []
    has_yaml = True

    for pkg in ["yaml", "openai", "tqdm"]:
        try:
            importlib.import_module(pkg)
        except Exception:
            failures.append(f"missing_python_package:{pkg}")
            if pkg == "yaml":
                has_yaml = False

    cfg = None
    if has_yaml:
        try:
            cfg = load_config(args.config)
        except Exception as e:  # noqa: BLE001
            failures.append(f"config_error:{e}")
    elif not Path(args.config).exists():
        failures.append(f"missing_config:{args.config}")

    if not os.getenv("OPENAI_API_KEY"):
        failures.append("missing_env:OPENAI_API_KEY")

    if cfg is not None:
        seed_input = Path(cfg["paths"]["seed_input"])
        if not seed_input.exists():
            failures.append(f"missing_seed_input:{seed_input}")
        eval_input = cfg["paths"].get("eval_input")
        if eval_input and not Path(eval_input).exists():
            failures.append(f"missing_eval_input:{eval_input}")

    if failures:
        print("Preflight failed:")
        for item in failures:
            print(f"- {item}")
        raise SystemExit(1)

    print("Preflight passed.")


if __name__ == "__main__":
    main()
