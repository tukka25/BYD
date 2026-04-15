# Plotly Synthetic Data Pipeline

This pipeline creates a **rephrasing-heavy synthetic dataset** with strict filtering for Plotly Python fine-tuning.

## What it does

1. Run preflight checks (deps, API key, input files).
2. Prepare seed data and split train/eval.
3. Generate user prompt rephrases (intent-preserving).
4. Generate alternative assistant code answers (equivalent implementations).
5. Filter with syntax + Plotly + intent + dedupe checks.
6. Mix and export final JSONL in your training schema.
7. Build fine-tuning-ready JSONL from mixed output.

## Folder layout

- `config.yaml`: knobs for ratio, model, validation rules.
- `00_check_env.py`
- `01_prepare_seed.py`
- `02_generate_rephrases.py`
- `03_generate_answer_aug.py`
- `04_filter_and_score.py`
- `05_mix_and_export.py`
- `06_build_finetune_dataset.py`
- `pipeline/`: shared logic.
- `runs/default/`: all artifacts and reports.

## Quick start

```bash
cd /Users/abdalrahman/Desktop/fine_tunning_expirements
python3 -m pip install -r data-pipeline/requirements.txt
export OPENAI_API_KEY="<your_key>"

bash data-pipeline/run_pipeline.sh
```

Or run step-by-step:

```bash
python3 data-pipeline/00_check_env.py --config data-pipeline/config.yaml
python3 data-pipeline/01_prepare_seed.py --config data-pipeline/config.yaml
python3 data-pipeline/02_generate_rephrases.py --config data-pipeline/config.yaml
python3 data-pipeline/03_generate_answer_aug.py --config data-pipeline/config.yaml
python3 data-pipeline/04_filter_and_score.py --config data-pipeline/config.yaml
python3 data-pipeline/05_mix_and_export.py --config data-pipeline/config.yaml
python3 data-pipeline/06_build_finetune_dataset.py --config data-pipeline/config.yaml
```

## Cost control knobs

In `config.yaml`:

- `generation.target_synth_per_seed`: main scale factor.
- `generation.rephrase_ratio`: rephrase-heavy target (e.g. `0.60`).
- `generation.test_max_rephrases`: optional cap for pilot runs.
- `generation.test_max_answer_aug`: optional cap for pilot runs.
- `generation.rephrase_workers` / `generation.answer_aug_workers`: parallel worker counts.
- `generation.answer_aug_validation_regen_attempts`: retries for invalid generated code (syntax/Plotly checks) during stage 3.
- `paths.eval_input`: if set, uses a fixed external eval file (no random holdout).
- `models.rephrase_model`: cheap model for paraphrasing.
- `models.answer_aug_model`: stronger model for code alternatives.
- `models.fallback_model`: used on retries/failures.
- `openai.max_requests_per_minute`: global request cap for each generation stage.

Quick pilot example (without changing config):

```bash
python3 data-pipeline/02_generate_rephrases.py --config data-pipeline/config.yaml --max-rephrases 30
python3 data-pipeline/03_generate_answer_aug.py --config data-pipeline/config.yaml --max-answer-aug 20
```

Parallel + safe cap example:

```bash
python3 data-pipeline/02_generate_rephrases.py --config data-pipeline/config.yaml --workers 8 --max-rpm 120
python3 data-pipeline/03_generate_answer_aug.py --config data-pipeline/config.yaml --workers 8 --max-rpm 120
```

Force more in-stage regeneration for answer augmentation:

```bash
python3 data-pipeline/03_generate_answer_aug.py --config data-pipeline/config.yaml --regen-attempts 4
```

Suggested low-cost default:

- `rephrase_model: gpt-5.4-mini`
- `answer_aug_model: gpt-5.4-mini`
- `fallback_model: o3-mini`

## Outputs

Main output:

- `data-pipeline/runs/default/05_final/plotly_qwen_train_synthetic_mix.jsonl`
- `data-pipeline/runs/default/06_finetune/plotly_qwen_finetune.jsonl` (messages-only, training-ready)

Reports:

- `01_seed/seed_manifest.json`
- `04_filtered/filter_report.json`
- `05_final/mix_manifest.json`
- `06_finetune/plotly_qwen_finetune_manifest.json`

Rejected rows:

- `04_filtered/rejects.jsonl`

## Error handling

- API calls have retry + fallback model.
- Per-row failures are logged and skipped.
- Pipeline can be rerun from any stage.

## Notes

- All rows keep chat format: `messages = [system, user, assistant]`.
- Rephrase generation now uses two inputs as context: original user question + original assistant code.
- Rephrase rows keep original assistant code in the output dataset.
- Answer augmentation generation now uses two inputs as context: original user question + original assistant code.
- Answer augmentation rows keep original user prompt in the output dataset.
