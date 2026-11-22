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

**The lora-v1 column is a lower bound.** 16 of the 25 failures recorded in
`eval_report.json` are one environment crash in the eval pod, not model errors:
`pyarrow._fs._init_ca_paths` blowing up in `ssl.py` while pyarrow imported. All
16 are in `treemap_funnel_waterfall` (`px.treemap` / `px.sunburst` reach a code
path that imports pyarrow; nothing else in the suite does), and none is in any
other bucket. The code itself was sound — one is a four-level `px.treemap` with
`px.Constant` and a cumulative column. So 21 rows of that bucket scored 5
passes and 16 crashes. The report keeps 25 failure samples of the 26 failures,
so the unrecorded one may be a seventeenth: the real render rate is somewhere
between 91.3% and 97.0%. Re-measure locally, where pyarrow imports, before
quoting a final number.

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

1. **`treemap_funnel_waterfall`'s 24% / 5% is mostly the pyarrow crash above**,
   not the model. The bucket is not short of data either: it has 105 training
   targets, more than `time_series`, which scores 96%. The real gap is inside
   it. By `figure_type` those 105 are **103 treemaps, 2 waterfalls, 0 funnels and
   0 sunbursts**, while the frozen test bucket covers all four. The question
   generator was asked for "treemap, funnel or waterfall" and the answers came
   back as treemaps. Re-score the bucket locally first (free), then generate
   funnel, sunburst and waterfall targets as separate quota keys so it cannot
   collapse to one type again.
2. **`area` and `heatmap` render but are the wrong shape** (100%/68% and
   91%/61%). The code runs and produces a figure, just not the figure that was
   asked for. For area the cause is in the data: area, line, time series and
   scatter targets all build a `scatter` trace (728 of the 1,897 synthetic
   targets), so the trace type carries no signal that separates them and only
   the question's wording does; `is_area_figure` is the scorer's tie-break.
   That is a targeting problem, not a volume one.

Remaining lora-v1 failures across all 300: `runtime_error` 23, `hallucinated_column` 2,
`no_figure` 1.

### Artifacts

`cloud/artifacts/out-min/` (gitignored, 111 MB):
`adapter_model.safetensors` + `adapter_config.json`. `cloud/eval_report.json` and
`cloud/adapter_config.json` are tracked. The adapter is fp32 (29,097,984 params x
4 bytes); cast to bf16 before shipping if size matters.

### Cost

Pod uptime 8,668 s (2 h 24 m) on the A100 at $2.19/hr. Settled billing, read on
2026-11-21 with `list-pod-billing` and `list-network-volume-billing`:

| line | amount |
|---|---|
| pod `kqjhyc60mcvzvs`, GPU | $5.291334 |
| pod `kqjhyc60mcvzvs`, disk | $0.012963 |
| network volume `cx8x2n8732` (40 GB HIGH_PERFORMANCE) | $0.031111 |
| **cloud total** | **$5.335408** |

The $3.134537 recorded here at first was read while billing was still settling;
the elapsed-time estimate of ~$5.28 was the right one. Nothing billed on
2026-11-21, so the pod and the volume are both gone. With $5.4708 of data
generation, the whole fine-tune cost **$10.81**. Roughly half the GPU time went
to avoidable debugging, itemised above.

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
sanity check, not a re-measurement. The n=300 figure is itself a lower bound
because of the pyarrow crash described under the results. Local generation runs at 10.8 rows/min, so a full 300-row local eval
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

## lora-v2 (2026-11-21)

| | |
|---|---|
| Data | `data/mlx_v2_capped`: 7,321 train / 949 valid, MAXLEN 2048, 4.5x v1's text (chartist question + plan forms, analyst, planner) |
| Pod | A100 SXM 80GB, $2.19/hr, Secure Cloud, EU-RO-1 (no HIGH_PERFORMANCE data center had A100 stock that day) |
| Volume | 20 GB STANDARD network volume at `/workspace` for data, checkpoints and logs; `HF_HOME=/root/hf-cache` on the 80 GB container disk, so the 18 GB base model loads from local disk in ~3 s (v1: ~6 min from the network volume) |
| Training | 2 epochs, 1,832 steps, 3.3 h; validation loss 0.157 -> 0.145 -> 0.132 -> 0.131 -> **0.126 (step 1500)** -> 0.127 -> 0.127; `load_best_model_at_end` saved checkpoint-1500 |
| Eval on the pod | frozen 300: render **97.3%**, right shape **87.0%**, invented columns 0.7% (v1's 91.3% / 81.0% there is a lower bound: 16 pyarrow crashes) |
| Pod lifetime | 19:26 -> ~23:16 UTC, deleted with its volume after the adapter was verified locally |
| Cost (settled) | pod **$8.41** (GPU $8.37 + disk $0.04) + volume $0.01 = **$8.42**, read 2026-11-22 with `list-pod-billing` / `list-network-volume-billing`; nothing billed after the 21st. Claude API for the v2 data: $15.62. All of lora-v2: about $24 |

Measured on the Mac, 4-bit base + MLX adapter, the same harness for both
(`data/eval_report_local_v{1,2}.json`, `data/v2/planning_eval_lora-v{1,2}.json`,
`data/role_measure{,_v2}.json`):

| | lora-v1 | lora-v2 |
|---|---|---|
| Frozen 300: renders | 89.3% | **94.3%** |
| Frozen 300: right kind of chart | 76.3% | **82.3%** |
| Frozen 300: invented column | 1.7% | 1.7% |
| Planning 120: dashboards needing a retry | 54.2% | **12.5%** |
| Planning 120: drawn charts that render | 86.4% | **98.9%** |
| Planning 120: drawn as the planned kind | 84.9% | **98.9%** |
| Single-chart planner, 118 questions | 80.5% | 77.1% |
| Narrator, usable titles | 100% | 100% |

- Render on the frozen 300 is paired: 26 questions failed only on v1, 11 only
  on v2 (exact McNemar p = 0.020). 4-bit costs v2 3 points of render against
  bf16 on the pod (97.3% -> 94.3%).
- Where v2 went the other way on the Mac: gauge/indicator 16 -> 13 of 17, box
  22 -> 20 of 23. On the pod gauge went up (82.4% -> 88.2%) and box lost one
  question (23 -> 22), so read these as small buckets plus quantization until
  a bigger set says otherwise.
- The planning eval draws only the first 3 charts of each dashboard, and v2
  opens with KPIs far more often (112 of 357 drawn vs 50 of 352), so its drawn
  mix is easier. Per kind it still wins wherever both have a sample: KPI
  40/50 -> 112/112, line 67/78 -> 106/108, bar 132/138 -> 109/109, heatmap
  26/38 -> 13/13. Dashboards whose 3 drawn charts all rendered: 78 -> 115 of
  120 (p = 3e-9).
- The single-chart planner's drop is not significant (9 lost, 5 gained,
  p = 0.42). The losses are v2's new chart types leaking into its labels:
  "cumulative ... building up" now reads as waterfall, "spread ... split by" as
  heatmap. With `CHARTIST_CHART_TYPE_HINT=off` that label only picks the
  deterministic fallback chart.
- Dashboard smoke (s0016, "watch time by country"): 7 planned, 7 drawn by the
  model, 0 by the backup chart, plans passed the checks first try, 125 s
  (lora-v1: 3 of 7 by the backup, 204 s).

What went wrong, so the next run avoids it:

- **The fast linear-attention kernel produced NaN.** `flash-linear-attention` 0.6.0 does not import with torch 2.8's Triton 3.4; 0.4.2 imports and passes a toy forward/backward, but in training the loss read 0 and grad_norm NaN from the first logged step. Reverted to the reference kernels (same losses as before to the third decimal). Do not install fla on this stack without checking the first logged loss.
- **Per-step time is set by row length.** v2 averaged ~6.5 s/step against v1's 4.35 s at MAXLEN 1536; estimate from tokens, not rows.
- **`evaluate_cuda.py` needs `PYTHONPATH=/workspace/chartist`.** Run as `cloud/evaluate_cuda.py`, Python searches `cloud/` for `chart_types`; the first on-pod eval died on that import (fixed in `RUNBOOK_v2.md`).
- **Self-stop backstop.** Pods carry `RUNPOD_API_KEY` and `RUNPOD_POD_ID`, so `runpodctl stop pod "$RUNPOD_POD_ID"` from inside the pod caps idle billing; a stop keeps the network volume. Kill helper processes by PID from a script file: `pkill -f name` inside `exec-pod` matches its own command line and kills the call.
