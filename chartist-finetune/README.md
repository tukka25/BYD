# chartist-finetune

Builds a fine-tuning dataset for the BYD chartist — the agent that turns a dataframe schema and a natural question into Plotly code.

Generation is **schema-first**: synthesise business table schemas, materialise a real CSV per schema, write natural dashboard questions against them, then generate code targets. **Every target is gated by executing it against its CSV** and checking the resulting figure. Nothing enters the dataset on the strength of looking plausible.

## Why this exists

The original dataset (`web-crawler/dataset/`) was 970 rows scraped from plotly.com/python. Measured against what the runtime chartist actually requires, it taught close to the opposite:

| | scraped data | this dataset |
|---|---|---|
| ends with `print(fig.to_json())` | 0% | **100%** |
| calls `fig.show()` | 96.1% | **0** |
| reads a file or URL | 46.9% | **0** |
| prompts mentioning columns | 3.3% | **100%** |
| prompt phrasing | 3 docs-page templates | natural user questions |

## Final dataset

| File | Rows | What it is |
|---|---|---|
| `data/mlx/train.jsonl` | **1,929** | 1,675 synthetic + 254 docs |
| `data/mlx/valid.jsonl` | **260** | 222 synthetic + 38 docs |
| `data/testset.jsonl` | **300** | **FROZEN.** 60 schemas, no gold answers — execution is the oracle |

- 206 train schemas / 28 valid schemas / 60 test schemas. The frozen test set is genuinely clean: no schema id, schema block or question text is shared with train or valid. Train versus valid is disjoint **by schema id only**: 14 identical schema blocks appear under different `docs-*` ids across train and valid, and 2 questions repeat across them. Valid loss is therefore partly in-distribution, so any overfitting call made from it is optimistic.
- 34 distinct Plotly trace types, including candlestick, sankey, funnel, waterfall, choropleth, violin, parcoords, splom, sunburst, icicle, ohlc.
- Hard cases are ~39% of the synthetic rows: multi-column aggregation, date resampling, grouped/faceted, missing-field, ambiguous.

**The frozen test set must not be regenerated.** Every eval number is comparable only against `data/testset.sha256`. It was re-frozen twice before any eval ran — once to stratify by chart bucket, once to fix a schema-spread bug — and is final.

## Spend

$5.47 of a $30 budget. Haiku wrote the schemas and questions; Sonnet wrote the code targets.

| Stage | Model | Cost |
|---|---|---|
| Code targets (1,920 questions) | `claude-sonnet-5-5` | $5.2339 |
| Questions (2,880) | `claude-haiku-5-5` | $0.1269 |
| Schemas (180) | `claude-haiku-5-5` | $0.0517 |
| Docs-layer questions (437) | `claude-haiku-5-5` | $0.0216 |
| Label grounding + diagnostics | both | $0.0367 |
| **Total** | | **$5.4708** |

Two decisions account for the underspend against the $14 line: dropping a false-positive rejection gate took target yield from 0.80 to 0.99, and generating one candidate per question instead of two halved the largest batch. The remaining ~$24 is reserve, to be spent after the first eval against whatever it shows is weak.

## Environment

The host Python is PEP 668 externally managed. **Every command uses the project venv**; a bare `pip install` fails.

```bash
cd chartist-finetune && .venv/bin/python -m pytest -v
```

The API key is read from `<repo>/.env` as `CLAUDE_API_KEY` — not a name the Anthropic SDK resolves on its own, so `client.py` reads it and passes it explicitly. `.env` is gitignored and the key is never logged.

### The oracle's environment is the contract

`executor.py` decides what enters the dataset, so **whatever it can execute is what the model learns to emit.** It must stay in sync with the backend's execution environment at `backend/app/utils/executor.py`. Today neither has `statsmodels`, which is why 42 `trendline="ols"` targets were correctly rejected — that code would crash in production too. That alignment was luck, not design. If you add a plotting dependency to one, add it to the other, or the filter will start admitting code that crashes in production or rejecting code that works.

## Pipeline (stages 1–8, complete)

Run from `chartist-finetune/`. Stages are ordered; later ones consume earlier output.

```bash
.venv/bin/python gen_schemas.py
```

```bash
.venv/bin/python gen_questions.py
```

```bash
.venv/bin/python freeze_testset.py
```

```bash
.venv/bin/python gen_targets.py --limit 200
```

```bash
.venv/bin/python gen_targets.py --offset 200 --max-spend 14.00
```

```bash
.venv/bin/python rewrite_docs.py
```

```bash
.venv/bin/python export_mlx.py --valid-ratio 0.12
```

**Pass `--valid-ratio 0.12` explicitly.** The script's default is still `0.08`, and the manifest does not record which was used — re-running without the flag silently produces a different split from the committed one.

`freeze_testset.py` refuses to overwrite an existing frozen set. That guard is deliberate; do not remove it.

## Next: training (stages 9–11)

Not yet run. Needs a ~20 GB download and multi-hour training.

### 1. Install mlx-lm and confirm Metal

```bash
cd chartist-finetune && .venv/bin/python -m pip install -U mlx-lm
```

```bash
cd chartist-finetune && .venv/bin/python -c "import mlx.core as mx; print(mx.default_device())"
```

A CPU device means stop — LoRA on CPU is not worth running here.

### 2. Capture the real CLI surface

Guides disagree on `convert` and `fuse` flags across mlx-lm versions. **The help output wins over any command below.**

```bash
cd chartist-finetune && for m in lora convert fuse generate; do .venv/bin/python -m mlx_lm.$m --help; done 2>&1 | tee runs/mlx_help.txt
```

### 3. Get the base model — download the prebuilt 4-bit, don't convert

```bash
cd chartist-finetune && .venv/bin/hf download mlx-community/Qwen3.5-9B-MLX-4bit --local-dir models/qwen3.5-9b-4bit
```

**5.98 GB**, already 4-bit MLX, and ships its own `chat_template.jinja`. Measured against the alternative below, this is 3.2× less to download and skips the conversion step entirely.

**It does carry a vision tower**, contrary to what earlier drafts of this file claimed: the shards hold 333 `vision_tower.*` tensors totalling **0.85 GB** of the 5.54 GB on disk, and `config.json` has a `vision_config`, `image_token_id` and `video_token_id`. The architecture is `Qwen3_5ForConditionalGeneration`.

But mlx-lm does **not** load them: the loaded model's only top-level submodule is `language_model`, and a scan of its modules finds nothing matching `vision`. So the vision tower costs 0.85 GB of disk and **nothing** in GPU memory, and the 8,953.8M parameters mlx-lm reports are the language model alone. There is no memory to reclaim by stripping it — checked, because at this margin 0.85 GB would have mattered.

The convert-it-yourself path works too but costs `Qwen/Qwen3.5-9B` at **19.33 GB** of bf16 download, plus conversion time and transient disk, to arrive at the same ~6 GB result:

```bash
cd chartist-finetune && .venv/bin/python -m mlx_lm.convert --hf-path Qwen/Qwen3.5-9B --mlx-path models/qwen3.5-9b-4bit -q --q-bits 4
```

Use it only if you want control over the quantisation parameters, or if the community repo disappears. Both repos carry the vision tower — converting it yourself does not avoid that.

**An `HF_TOKEN` will not make either download faster.** A token governs access, not bandwidth — it is needed for gated repos (Llama, some Gemma) and raises API rate limits, but both repos here are public. What does speed it up is `hf_xet`, which `huggingface-hub` 2.4.0 already installed as a dependency and uses automatically for Xet-backed repos. The real lever is picking the 6 GB artefact over the 19 GB one.

### 4. GATE — measure real token lengths before training

**Do not skip this.** If a row exceeds `--max-seq-length`, **mlx-lm silently truncates its tail** — cutting the closing `print(fig.to_json())` and training the model to omit the one line the contract requires.

And the real hazard is worse than a worse model. `iterate_batches` truncates the row and updates its *length* but never clamps the prompt **offset** (`tuner/trainer.py:166`), while `default_loss` computes `sum(ce * mask) / mask.sum()`. So any row whose prompt alone exceeds the cap yields an all-false mask, `ntoks == 0`, and a loss of `0/0 = nan` — and one nan gradient poisons every weight for the rest of the run. mlx-lm prints only `[WARNING]`. Measured: a probe at `--max-seq-length 512` reported a clean `val 0.567` at iter 1 and `nan` by iter 4.

This is why over-length rows must be **dropped, not truncated** — what `cap_dataset.py` does.

```bash
cd chartist-finetune && .venv/bin/python check_token_lengths.py --model models/qwen3.5-9b-4bit --limit 4096
```

**Measured, and the estimate this plan was sized on was 2.25× low.** Run with a stand-in tokenizer while the model was still downloading:

| | chars/4 estimate | measured |
|---|---|---|
| chars per token | 4.0 | **2.75** |
| longest train row | ~1,340 tokens | **3,011 tokens** |
| p50 / p99 | — | 753 / 1,268 |

So `2048` would have truncated several rows and `2560` still truncated three. **Use `--max-seq-length 4096`.** The headroom is nearly free: mlx-lm pads each batch to its own longest sequence rather than to the limit, and p99 is 1,268, so only the rare long batch pays for it. If memory becomes a problem, `--grad-checkpoint` is the lever, or drop the three outlier rows.

Re-run the gate with the real Qwen tokenizer once the model is on disk — its template differs from the stand-in and could move these numbers by roughly ±10%. The gate exits non-zero if any row is over, and `run_overnight.sh` runs it before launching.

### 4b. If training OOMs: read this before touching any flag

The first real run died at iteration 1 with
`[METAL] Command buffer execution failed: Insufficient Memory`. The iter-1
validation pass had already completed (`val 0.672`), so the model and the forward
pass fit; only the backward pass did not. **Measured diagnosis, in the order it was
established:**

| Check | Result |
|---|---|
| `--batch-size 1 --grad-accumulation-steps 2 --grad-checkpoint` | still OOM |
| `--max-seq-length` sweep (batch 1 + checkpointing) | 512 trains, **1024 OOMs** |
| mlx working-set ceiling (`mx.device_info()`) | `max_recommended_working_set_size` **24.96 GB**, mlx `memory_limit` 30.40 GB |
| Physical memory (`vm_stat`) | free **0.06 GB**, compressed **13.07 GB**, wired 7.02 GB |
| Swap (`sysctl vm.swapusage`) | **56.3 GB used of 57.3 GB — 98% full** |
| Sum of all process RSS | only ~11 GB (Chrome 3.4, Claude 2.2, Docker 1.65, VS Code 0.9) |

**So the ceiling was never mlx's.** mlx would happily use 24.96 GB; the GPU could
not obtain physical pages, because the machine had essentially zero free pages and
a saturated swap. Metal buffers must be wired into physical RAM and **cannot be
served from swap**, so an oversubscribed machine fails hard rather than paging.

The same pressure also destroys throughput: the iter-1 validation pass over 260
rows took **851 seconds** (~200 tok/s for a forward-only pass on a 4-bit 9B).
That is thrashing, not compute. Fixing memory is a prerequisite for the run
*finishing*, not only for it starting.

**The fix is to free physical memory, not to shrink the job.** Capping sequence
length cannot rescue this: the ceiling (512-1024) sits below the dataset's median
row (628 tokens), so any cap that fits would discard more than half the data.

What the levers are actually worth:

- **Reboot** — reclaims the 56 GB swap and 13 GB compressed. The only action that
  restores a clean ~25 GB working set. Do this first.
- **Quit Chrome / VS Code / Docker Desktop** — about 6 GB of RSS, but leaves swap
  saturated, so it may not be enough on its own.
- **`sudo sysctl iogpu.wired_limit_mb=28000`** — raises the wired cap. Pointless
  here: the cap was 24.96 GB and the job never got near it. Not persistent across
  reboots. Only reach for this once memory is genuinely free and a *large* run
  still fails.
- **Stripping the vision tower** — worth nothing in memory. mlx-lm never loads it
  (verified: the loaded model's only top-level submodule is `language_model`).

Memory needed, for sizing after a reboot: weights are 4.69 GB resident, and the
per-token cost is dominated by the logits tensor at **vocab 248,320** — 0.95 GB in
fp32 at 1,024 tokens, 2.68 GB at 2,892, each needing a gradient of the same size.
`--grad-checkpoint` does not reduce it, because the LM head sits outside the
checkpointed decoder layers. That is why checkpointing alone never fixed this.

`probe_mem.py` measures peak memory per sequence length directly; run it once the
machine is clean to get real numbers instead of these estimates.

### 4c. Capping the dataset (only if you need headroom)

`cap_dataset.py` writes a length-capped copy of `data/mlx` by **dropping**
over-length rows, keeping `train.jsonl` and `train_fixtures.jsonl` in sync (they
are positionally joined, and it refuses to run if their lengths disagree).

```bash
cd chartist-finetune && .venv/bin/python cap_dataset.py --limit 1536 --out data/mlx_1536
```

Measured cost of each cap, with the real Qwen tokenizer:

| cap | train kept | dropped | valid dropped |
|---|---|---|---|
| 1024 | 1,909 | 20 (1.04%) | 3 |
| 1280 | 1,916 | 13 (0.67%) | 1 |
| **1536** | **1,926** | **3 (0.16%)** | 1 |
| 2048 | 1,926 | 3 (0.16%) | 1 |
| 2892 | 1,929 | 0 | 0 |

A 1536 cap costs 0.16% of the data and buys a 1.9x reduction in worst-case
per-step memory, which is the cheapest insurance available. Remember that
`--iters` counts micro-steps, so re-derive it from the kept row count.

### 5. Train

Measured sizing: 1,929 train rows, 965 steps per epoch at batch size 2, so `--iters 1930` is two epochs.

```bash
cd chartist-finetune && .venv/bin/python -m mlx_lm lora --model models/qwen3.5-9b-4bit --train --data data/mlx --adapter-path runs/lora-v1/adapters --batch-size 2 --max-seq-length 4096 --iters 1930 --steps-per-report 25 --steps-per-eval 200 --save-every 200 2>&1 | tee runs/lora-v1/train.log
```

QLoRA is automatic because `--model` points at a quantised model.

**Read the validation loss, not the clock.** Falls then flattens → let it finish. Falls then **rises** → overfitting; note the iteration where it turned, stop, re-run with `--iters` just below it. Training loss barely moving → add `--learning-rate 1e-4`. On OOM, `sudo sysctl iogpu.wired_limit_mb=28000` (not persistent across reboots).

Valid is 272 rows across 28 schemas. That signal is adequate for the overfitting call but thin for rare chart types — judge those on the frozen test set, not on valid loss.

### 6. Evaluate, base first

```bash
cd chartist-finetune && .venv/bin/python evaluate.py --label base --adapter-path none
```

```bash
cd chartist-finetune && .venv/bin/python evaluate.py --label lora-v1 --adapter-path runs/lora-v1/adapters
```

`evaluate.py` does not exist yet — stage 11 of the plan specifies it. Run the **full 300 rows**, not a subset: at n=300 a ~16pp gap between the two arms is detectable, where n=40 would only show ≥31pp.

Two things to know when reading the numbers. The frozen set is deliberately **not** production-mix — a 15-row floor per chart bucket puts `gauge_or_indicator` at 5.7% against a 2% quota — so the base-versus-tuned comparison is unbiased (both arms see the same rows) but any "what would production look like" figure must be quota-weighted. And the hallucination metric comes from `failure_kind == "hallucinated_column"`, classified from the execution error, not from a static column check; the static one was dropped as a gate because it rejected every chart that derives its own columns.

### 7. Serve

The adapter serves the **chartist role only**. The detective keeps base instruct weights, because its two ReAct agents depend on tool calling, which this adapter is not trained for.

Stage 11 of the plan covers fusing with `--de-quantize`, re-quantising, running `mlx_lm.server`, and the `LLM_BACKEND=mlx` switch in the backend. Its serving step depends on `docs/superpowers/plans/2026-11-19-platform-correctness.md` tasks 4–8 being merged first, since it edits `get_llms()`.

## Layout

| Path | Role |
|---|---|
| `contract.py` | Loads the chartist contract from the backend by path — no copy to drift |
| `executor.py` | The execution oracle. `run_candidate` always returns a verdict and never raises |
| `client.py` | Anthropic client, Batch API runner, cost accounting into `runs/spend.jsonl` |
| `chart_types.py` | The chart-type quota and hard-case mix |
| `gen_schemas.py` → `export_mlx.py` | The eight pipeline stages |
| `data/fixtures/`, `data/fixtures_docs/` | ~474 CSVs, one per schema |
| `runs/` | Logs, spend ledger, rejected candidates. Gitignored |

## Eval note: use `is_area_figure`

`chart_types.TRACE_TYPES` maps line, scatter, area and time_series all to `{scatter, scattergl}`, so a trace-type check alone scores any scatter-family output as the "right shape" on 107 of the 300 frozen test rows. The eval **must** also call `chart_types.is_area_figure(code)` (px.area, `fill=` or `stackgroup=`): area rows require it to be true, line/scatter/time_series rows require it to be false. This separates the two groups perfectly on the committed targets (tested).

## Contract gates

`validate_chart_code` mirrors the production `SafeExecutor.blocked_patterns` (`__import__`, `eval(`, `exec(`, `open(`, os/subprocess imports) and requires exactly one `print(fig.to_json())` as the final statement with no other `print` call, because production `json.loads` all of stdout. `export_mlx.py` re-runs it over every row and refuses to export on any violation. The oracle subprocess runs in a throwaway temp directory.
