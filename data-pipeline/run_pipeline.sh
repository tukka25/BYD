#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-data-pipeline/config.yaml}"

python3 data-pipeline/00_check_env.py --config "$CONFIG_PATH"
python3 data-pipeline/01_prepare_seed.py --config "$CONFIG_PATH"
python3 data-pipeline/02_generate_rephrases.py --config "$CONFIG_PATH"
python3 data-pipeline/03_generate_answer_aug.py --config "$CONFIG_PATH"
python3 data-pipeline/04_filter_and_score.py --config "$CONFIG_PATH"
python3 data-pipeline/05_mix_and_export.py --config "$CONFIG_PATH"
python3 data-pipeline/06_build_finetune_dataset.py --config "$CONFIG_PATH"
