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
| `data/mlx/train.jsonl` | **1,924** | 1,664 synthetic + 260 docs |
| `data/mlx/valid.jsonl` | **272** | 238 synthetic + 34 docs |
| `data/testset.jsonl` | **300** | **FROZEN.** 60 schemas, no gold answers — execution is the oracle |

- 207 train schemas / 28 valid schemas / 60 test schemas, all disjoint.
- Zero prompt-text overlap between train, valid and test.
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

`executor.py` decides what enters the dataset, so **whatever it can execute is what the model learns to emit.** It must stay in sync with the backend's execution environment at `backend/app/utils/code_runner.py`. Today neither has `statsmodels`, which is why 42 `trendline="ols"` targets were correctly rejected — that code would crash in production too. That alignment was luck, not design. If you add a plotting dependency to one, add it to the other, or the filter will start admitting code that crashes in production or rejecting code that works.

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

### 3. Convert and quantise the base model

```bash
cd chartist-finetune && .venv/bin/python -m mlx_lm.convert --hf-path Qwen/Qwen3.5-9B --mlx-path models/qwen3.5-9b-4bit -q --q-bits 4
```

Qwen3.5-9B is a vision-language model and `mlx_lm.lora` is text-only. MLX text loaders skip vision weights, but if this fails on the vision tower, search Hugging Face for a text-only MLX conversion of Qwen3.5-9B and pass that repo id instead. Expect ~20 GB transient disk for the bf16 download and ~5–6 GB output.

### 4. GATE — measure real token lengths before training

**Do not skip this.** The sizing below rests on a chars/4 estimate, which understates Python source: code, punctuation, indentation and column names tokenise at roughly 2.7–3.3 chars per token. The longest row is ~1,340 tokens by that estimate but plausibly **1,600–2,000 real tokens** against a 2,048 limit. If a row exceeds `--max-seq-length`, **mlx-lm silently truncates its tail** — cutting the closing `print(fig.to_json())` and training the model to omit the one line the contract requires.

Once the model is downloaded its tokenizer is local. Tokenise every row of `data/mlx/train.jsonl` and `valid.jsonl` and confirm none exceeds 2,048 including chat-template tokens. If any do, raise `--max-seq-length` rather than letting them truncate.

### 5. Train

Measured sizing: 1,924 train rows, 962 steps per epoch at batch size 2, so `--iters 1924` is two epochs.

```bash
cd chartist-finetune && .venv/bin/python -m mlx_lm.lora --model models/qwen3.5-9b-4bit --train --data data/mlx --adapter-path runs/lora-v1/adapters --batch-size 2 --max-seq-length 2048 --iters 1924 --steps-per-report 25 --steps-per-eval 200 --save-every 200 2>&1 | tee runs/lora-v1/train.log
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
