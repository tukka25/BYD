# Cloud training (Runpod)

Local MLX training was abandoned: Qwen3.5 is a hybrid model whose 24 Gated
DeltaNet layers hold a 2 MB recurrent state **per timestep**, and mlx-lm runs the
unfused path during training (`qwen3_5.py:193` passes `use_kernel=not
self.training`). Measured peak was **96.93 GB on a 24.96 GB GPU**. See the main
README section 4b.

On CUDA the same model trains in ~34 minutes on one A100 80GB.

## What ran

| | |
|---|---|
| Pod | A100 SXM 80GB, **$2.19/hr**, Secure Cloud, US-CA-1/2 |
| Image | `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404` (template `runpod-torch-v280`) |
| Volume | 40 GB HIGH_PERFORMANCE network volume at `/workspace`, `HF_HOME=/workspace/hf-cache` |
| Stack | transformers 5.23.0, peft 0.22.0, datasets 5.2.0, torch 2.8.0+cu128 |
| Driving it | the Runpod MCP `exec-pod` tool — no SSH key and no `RUNPOD_API_KEY` needed |
| File transfer | `runpodctl send` / `receive` (croc, one-time code, no API key) |

## The three non-obvious things

1. **`target_modules` must exclude the linear-attention projections.** `all-linear`
   — the usual best-quality setting — would adapt `in_proj_a` (the forget gate)
   and `in_proj_b` (the delta step size), which multiply the recurrent state at
   every timestep. A 0.5% shift in the per-step gate changes long-range retention
   by ~155x over 1,000 tokens; the reported symptom is looping output.
   `train_lora.py` asserts that zero `linear_attn` modules were matched and exits
   if any were. Verified: **128 modules adapted, 0 of them linear_attn**
   (8 attention layers x 4 + 32 MLP layers x 3), 29,097,984 trainable params.

2. **Prompt/answer split on TEXT, not token counts.** Qwen3.5 is a thinking
   model: a generation prompt ends `<think>\n`, while a full turn renders
   `<think>\n\n</think>\n\n<content>`, and the tokeniser merges newlines
   differently across that join. Masking the first `len(prompt_ids)` tokens lands
   one token off and teaches the model to emit `</think>` without the newlines it
   must produce. Text-level prefix was verified to hold on all 1926+259 rows.

3. **Eval must strip the reasoning block and use LEFT padding.** Generation
   starts after `<think>\n`, so output begins `\n</think>\n\n`; left in, every
   candidate is a SyntaxError and the render rate reads 0% for a working model.
   And batched decoder-only generation with the default right padding continues
   from pad tokens, producing fluent garbage rather than an error.

## Cost of the mistakes, recorded so they are not repeated

The first hour produced nothing. Two avoidable bugs, each costing a ~6-minute
model load from the network volume (18 GB at ~55 MB/s):

- `TrainingArguments(warmup_ratio=...)` — **removed in transformers 5.23**; only
  `warmup_steps` exists. Check the signature before the run, not after.
- `apply_chat_template(tokenize=True)` returns a **`BatchEncoding`**, which
  extends `UserDict` and is therefore **not** an instance of `dict`. An
  `isinstance(out, dict)` guard misses it and `list(out)` yields the KEYS, so
  every row became two tokens and was fully masked.

Both would have been caught by probing the dataset and the API surface before
paying for a model load. `train_lora.py` now exits on an empty split *before*
loading the model.

## Run order

```bash
runpodctl send cloud/train_lora.py        # then `runpodctl receive <code>` on the pod
```

```bash
python3 -c "import train_lora as T; tr=T.PromptMaskedRows(T.DATA/'train.jsonl', T.MAXLEN); print(len(tr), tr.prefix_mismatch, tr.dropped_long, tr.dropped_empty)"
```

```bash
setsid sh -c 'export PYTHONUNBUFFERED=1; cd /workspace/chartist && exec python3 train_lora.py' > /workspace/train.log 2>&1 < /dev/null &
```

```bash
python3 evaluate_cuda.py --label base --adapter-path none && python3 evaluate_cuda.py --label lora-v1 --adapter-path /workspace/outputs/lora-v1
```

**The kernels are not installed.** `causal_conv1d` and `flash-linear-attention`
are absent, so `chunk_gated_delta_rule` runs its reference PyTorch path —
"correct but much slower". Measured 4.35 s/it, 482 steps, ~34 min for 2 epochs.
Installing them was judged not worth a restart (another 6-minute model load plus
a source build of `causal_conv1d`) against a 34-minute run. Install them if you
iterate repeatedly.

**Stop the pod the moment the run finishes** — it bills whether or not anything
is using it. The network volume bills per allocated GB from creation until
deleted, independently of the pod.
