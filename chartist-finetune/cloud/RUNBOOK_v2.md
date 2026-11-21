# lora-v2 on Runpod — runbook

One adapter, three jobs: the chartist (question form and plan form), the
dashboard analyst, and the dashboard planner. Same recipe as lora-v1 (see
`README.md` for what ran and the three non-obvious things); only the data and
the length cap change.

## 0. Gate

**Do not create anything until the user has approved this run in chat.**
Creating a pod or a volume is billable from the moment it exists.

## 1. Inputs, checked locally first

| | |
|---|---|
| Data | `data/mlx_v2_capped/{train,valid}.jsonl` (+ `_fixtures.jsonl`, `split_manifest.json`) |
| Rows | 7,321 train / 949 valid; 4.5x lora-v1's training text |
| Length cap | `MAXLEN=2048`: 4 rows of 8,274 are longer (cap_dataset dropped them); 1536 would drop 5% |
| Prompt/answer split | `verify_v2_rows.py`: 0 prefix mismatches in both splits |
| Leak check | `export_v2.py` refuses to write a row from either frozen test set |
| LoRA | r=16, alpha=32, dropout 0.05, q/k/v/o + gate/up/down, linear attention excluded (unchanged) |

## 2. Cost read, then the price stated to the user

Read A100 80GB stock and price with the Runpod MCP:
`list-gpu-types` with `include: ["AVAILABILITY"]`, `product: ["POD"]`.
lora-v1 paid $2.19/hr (A100 SXM 80GB, Secure Cloud) and trained 2 epochs in
~34 minutes. v2 has 4.5x the text, so expect ~2.5 hours of training, and about
3 hours of pod time in all (model load ~6 min, evaluation ~20 min, transfers):
roughly $6.5–7.5, plus a few cents of volume storage. `EPOCHS=1` would halve the
training time; the recipe default stays at lora-v1's 2 unless the user chooses.

## 3. Create

1. A 40 GB `HIGH_PERFORMANCE` network volume in a data center that shows A100
   80GB stock and lists network storage.
2. A Secure Cloud pod in that data center: image
   `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`, `gpu.minCudaVersion: "12.8"`,
   the volume mounted at `/workspace`, `HF_HOME=/workspace/hf-cache`, no SSH and
   no public ports (driven with `exec-pod`).
3. Read the pod back (`get-pod`) and confirm it is RUNNING with the volume mounted.

## 4. Upload

From `chartist-finetune/`, with `runpodctl send` (one-time code, no API key):

- `data/mlx_v2_capped/`, `data/testset.jsonl`, `data/schemas.jsonl`,
  `data/fixtures/`, `data/fixtures_docs/`
- `cloud/train_lora.py`, `cloud/evaluate_cuda.py`
- `executor.py`, `_candidate_runner.py`, `chart_types.py`, `contract.py`
- the backend files `contract.py` loads by path (`executor.py` imports
  `contract`, which now loads all three):
  `backend/app/services/agents/{chartist_contract,planning_contract,profiler}.py`

Receive the fine-tune files into `/workspace/chartist/` and the three backend
files into `/workspace/backend/app/services/agents/` — `contract.py` resolves
them as `../backend/...` from its own folder. Check before training:
`cd /workspace/chartist && python -c "import executor, contract; print(contract.CHART_KINDS)"`.

## 5. Install

```bash
pip install transformers==5.23.0 peft==0.22.0 accelerate datasets==5.2.0 plotly pandas certifi
python -c "import pyarrow.fs" || pip uninstall -y pyarrow
```

`evaluate_cuda.py` now refuses to start when pyarrow is installed but broken —
the failure that cost lora-v1's eval 16 treemap rows.

## 6. Train

```bash
cd /workspace/chartist
DATA=/workspace/chartist/data/mlx_v2_capped OUT=/workspace/outputs/lora-v2 \
  MAXLEN=2048 EPOCHS=2 EVAL_STEPS=150 SAVE_STEPS=300 python cloud/train_lora.py
```

2 epochs is 1,830 optimizer steps; validation loss is measured every 150
(about 12 points) and the adapter saved at the end is the lowest-validation-loss
checkpoint (`load_best_model_at_end`). lora-v1's curve for the record: 0.191 at
the end of epoch 1, 0.177 at the end of epoch 2, flat at the end.

The script asserts that zero linear-attention modules were matched and exits
on an empty split before loading the model. lora-v1 fit at MAXLEN 1536 with
`BATCH=4 ACCUM=2`; if 2048 runs out of memory, use `BATCH=2 ACCUM=4` (same
effective batch).

## 7. Evaluate on the pod

```bash
python cloud/evaluate_cuda.py --label lora-v2 --adapter-path /workspace/outputs/lora-v2 \
  --out /workspace/eval_report_v2.json
```

The frozen 300, question form, at the production cap of 1024 tokens.

## 8. Download, then delete everything

1. `runpodctl send` the adapter directory and `eval_report_v2.json` from the pod;
   receive into `cloud/artifacts/out-v2/` and `cloud/eval_report_v2.json`.
2. Delete the pod, then the volume. Confirm both are gone with `list-pods` and
   `list-network-volumes`.
3. The next day, read the settled cost with `list-pod-billing` and
   `list-network-volume-billing`, and record it in `README.md`.

## 9. Home

`peft_to_mlx.py --peft cloud/artifacts/out-v2 --out runs/adapters-mlx-v2`, then
the local evals: `evaluate.py` (frozen 300), `measure_planning.py --label lora-v2`
and `measure_roles.py`, all against lora-v1's numbers on the same harness.
