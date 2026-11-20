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

## Results (frozen 300, execution-scored, 2026-11-20)

Both arms greedy-decoded, scored by executing every generated script against its
schema's real CSV through `executor.py` — the same oracle that gated the training
data. `data/testset.sha256` verified on the pod before the run.

| metric | base | lora-v1 | delta |
|---|---|---|---|
| render rate | 7.7% | **91.3%** | **+83.7 pp** |
| render rate, quota-weighted | 6.6% | **93.5%** | +86.9 pp |
| right chart shape | 4.7% | **81.0%** | +76.3 pp |
| hallucinated column | 0.0% | 0.7% | +0.7 pp |

At n=300 per arm the 95% CI half-width on a difference of proportions is ~11 pp,
so +83.7 is far outside noise.

Validation loss during training, 9 passes: **0.671 untrained → 0.2441 → 0.2194 →
0.2016 → 0.1910 → 0.1889 → 0.1808 → 0.1771 → 0.1767 → 0.1767.** Flat on the last
two points and tracking the training loss throughout: converged, no overfitting,
so the final adapter is the one to serve rather than an earlier checkpoint.

**Why the base scores only 7.7%:** 267 of its 277 failures are `syntax_error`,
because it answers in prose ("Thinking Process:\n\n1. **Analyze the Request:**…")
instead of bare Python. Both arms pass through the identical extractor (strip
`</think>`, strip markdown fences), so the comparison is fair — but the number
measures "follows the contract out of the box", not "can write Plotly at all". A
more aggressive code-scraper would lift the base figure somewhat.

### Where it is still weak — the agenda for the next run

| bucket | n | base → lora render | right-shape |
|---|---|---|---|
| **treemap_funnel_waterfall** | 21 | 0% → **24%** | **5%** |
| gauge_or_indicator | 17 | 35% → 82% | 71% |
| heatmap | 23 | 4% → 91% | 61% |
| area | 25 | 8% → 100% | 68% |
| grouped_or_stacked_bar | 27 | 0% → 93% | 89% |
| everything else (7 buckets) | 187 | 3–21% → 96–100% | 91–96% |

Two distinct problems, and they need different fixes:

1. **`treemap_funnel_waterfall` barely moved** (24% render, 5% right-shape). These
   are the exotic constructors, and 21 test rows against a 2% quota means the
   training set had very few of them. This wants targeted data generation, which
   is what the remaining ~$24.53 of Claude budget is for.
2. **`area` and `heatmap` render but are the wrong shape** (100%/68% and
   91%/61%). The code runs and produces a figure, just not the figure that was
   asked for — `is_area_figure` is catching scatter-family output where an area
   chart was requested. That is a labelling/targeting problem in the training
   data, not a syntax one, and it is cheaper to fix than (1).

Remaining lora-v1 failures across all 300: `runtime_error` 23, `hallucinated_column` 2,
`no_figure` 1.

### Artifacts

`cloud/artifacts/out-min/` (gitignored, 111 MB):
`adapter_model.safetensors` + `adapter_config.json`. `cloud/eval_report.json` and
`cloud/adapter_config.json` are tracked. The adapter is fp32 (29,097,984 params x
4 bytes); cast to bf16 before shipping if size matters.

### Cost

Pod uptime 8,668 s (2 h 24 m) on the A100 at $2.19/hr. `list-pod-billing` reports
**$3.134537** (GPU $3.126667 + disk $0.007870); elapsed-time arithmetic gives
~$5.28, so the billing figure was still settling when read. Roughly half of that
time went to avoidable debugging, itemised above. The 40 GB HIGH_PERFORMANCE
network volume `cx8x2n8732` keeps billing until deleted, independently of the pod.

## Serving it locally (the PEFT → MLX conversion)

Training on CUDA produced a peft adapter; mlx-lm loads only adapters it made
itself. The pod could not be restarted to merge the weights instead (a stopped
pod resumes on its original host, and another renter had taken those GPUs), so
`cloud/peft_to_mlx.py` translates the adapter. Verified after loading:
**128/128 trained modules have non-zero `lora_b`, and all 120 `linear_attn` gate
adapters are exactly zero** — mlx inits `lora_b` to zeros, so the gates it wraps
but we never trained are exact identities rather than noise.

```bash
cd chartist-finetune && .venv/bin/python cloud/peft_to_mlx.py --peft cloud/artifacts/out-min --out runs/adapters-mlx
```

```bash
cd chartist-finetune && .venv/bin/python -m mlx_lm server --model models/qwen3.5-9b-4bit --adapter-path runs/adapters-mlx --port 8080
```

No fusing is needed: `mlx_lm server` takes `--adapter-path` directly.

**Measured after conversion**, locally on an M2 Pro, first 40 frozen-test rows:

| | converted MLX 4-bit (n=40) | CUDA bf16 (n=300) |
|---|---|---|
| render rate | 87.5% | 91.3% |
| right chart shape | 85.0% | 81.0% |

At n=40 the 95% CI is ~±10 pp, so the gap is within noise: the conversion and
4-bit quantisation cost nothing measurable. The subset is **not** stratified and
is easier than the full set (78% `easy` versus 62%), so this is a conversion
sanity check, not a re-measurement — 91.3% at n=300 stays the authoritative
number. Local generation runs at 10.8 rows/min, so a full 300-row local eval
takes about 28 minutes.

### Still to do before the app works end to end

1. **`qwen_slm.py` speaks the wrong protocol.** `LocalQwenChatModel` extends
   `ChatOllama` (Ollama's `/api/chat`), while `mlx_lm server` is OpenAI-compatible
   (`/v1/chat/completions`). Pointing `OLLAMA_BASE_URL` at the MLX server will not
   work; it needs a `ChatOpenAI` path behind an `LLM_BACKEND` switch, which is what
   the plan's Task 11 described but never built.
2. Backend dependencies are not installed, and Postgres (docker compose) is not
   running. `app/main.py` creates tables at startup, so the DB has to be up.
3. Frontend dependencies.

Fixed along the way: `run_agent_workflow` discarded the caller's `selected_source`
and `available_sources` and charted a hardcoded CSV on every request (`a413539`).
