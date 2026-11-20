# SLM harness evaluation — PromptDash agents

Reviewed 2026-11-20, against the harness as it stood before the changes in commit
`e296745`. The target model is small and local: a 4-bit Qwen3.5-9B on Apple
silicon, with a LoRA fine-tune covering the chartist role only.

The harness is four stages — **planner** (choose a chart type), **detective**
(choose a data source), **chartist** (write Plotly code), **executor** (run it in
a subprocess). The chartist was already well designed: a contract in the system
prompt, static validation of the output, and a deterministic fallback. The two
stages before it were built as though a frontier model were serving them.

Every claim below was checked against the code or measured against the running
model. Where a number appears, it came from a run.

---

## 1. The chartist was being fed out-of-distribution prompts

**Severity: high.** This one silently wasted the fine-tune.

`CHARTIST_USER_TEMPLATE` is shared between training and serving by construction —
the dataset generator loads it from the backend by path specifically so it cannot
drift — and it renders as:

```
Task: {task}

DataFrame `df` schema:
columns: {columns}
dtypes: {dtypes}
first rows: {sample_rows}

Write the Python now.
```

In training, `{task}` was a natural dashboard question: *"Show square footage
against sale price for sales made in each quarter"*. All 1,926 rows looked like
that. At serve time, `_task_description()` substituted generated prose:

```
Build a bar chart. Style: {'theme': 'plotly_white'}. Prefer these columns: [...].
Suggested encoding: ... Unavailable, do not use: [...]
```

So the one field the model was trained to read was replaced with something it had
never seen. **Fixed:** the Task line is the user's question. The chart type is
inferred from the question, exactly as in training.

A related dead end: `_task_description` read `dataframe_plan["plotly_ready_spec"]`,
which the detective never produced — the key did not exist in its output. That
branch could never fire.

## 2. The planner asked for a schema it never sent

**Severity: high**, and a clean example of an SLM-hostile prompt.

The prompt ended *"Return the output strictly in JSON format matching the TaskPlan
schema"* — but the template had no `{format_instructions}` placeholder and no
partial variables, so **the schema was never in the prompt**. The model was asked
to conform to something it had not been shown.

Compounding it:

| Problem | Why it hurts a small model |
|---|---|
| Four fields at once (`steps`, `visualization_type`, `style_config`, `data_requirements`) | Accuracy falls off sharply with the number of simultaneous obligations. Only `visualization_type` was used downstream; `steps` reached a log line and `data_requirements` nothing at all. |
| No closed label set | `visualization_type` could come back as any string, and nothing validated it. |
| No examples | Few-shot is the cheapest accuracy available at this size, and pins output shape better than describing it. |
| Indented multi-line prose | Tokens spent on manners rather than the decision. |
| `except` → always `bar` | A parse failure lost all signal from the question. |

**Fixed:** one decision, twelve allowed values listed explicitly, the output shape
shown literally (`{"chart_type": "<one allowed value>"}`), two few-shot examples,
lenient parsing (strict JSON → any JSON object in the reply → a single unambiguous
label mention), and a keyword fallback.

Measured on the lenient parser: `{"chart_type": "line"}` → `line`;
`Sure! {"chart_type":"pie"} hope that helps` → `pie`;
`</think>\n\n{"chart_type": "heatmap"}` → `heatmap`; `I think a scatter plot` →
`scatter`; `bar or line maybe` → `None`, correctly refusing to guess.

## 3. The detective asked a small model to do the hardest possible thing

**Severity: high**, three distinct faults.

It ran **two ReAct tool-calling agents per request** — one to pick a source, one
to "build a dataframe plan". Multi-turn tool calling requires emitting well-formed
calls, reading results, and deciding when to stop, repeatedly. It is the weakest
area for models this size. The tell was already in the code: both agents had
keyword-overlap fallbacks for when they returned nothing usable.

**Both agents used a fixed `thread_id`** — `"detective-source-detection-stage"`
and `"detective-dataframe-builder-stage"` — against a `MemorySaver`. Every request
appended to the *same* conversation thread. That is unbounded memory growth, and
request *N* could read request *N−1*'s messages: a correctness and a privacy
defect, not just a leak.

And it cost **two LLM round-trips before a single line of chart code**.

**Fixed** by inverting the default — compute first, ask only when genuinely stuck:

1. An explicitly selected source is used directly, **with no LLM call at all**.
   This is the common case when a user picks a file in the UI.
2. One candidate, one answer.
3. Otherwise rank by token overlap between the question and each source's name and
   columns. A clear winner (margin ≥ 0.15) is taken as-is.
4. Only a near-tie reaches the model, as **one single-shot multiple-choice
   question**: "reply with only the number". No tool protocol to get wrong, and
   the answer either parses or it does not.

Column selection is no longer asked of a model at all. The chartist is fine-tuned
to read a schema block and choose its own columns — that is what its training
rows taught it — so a second opinion only adds a round-trip and a disagreement.

### A latent bug that made the ranking useless anyway

The tokeniser was `re.findall(r"[a-z0-9]+", value.lower())`, which **never splits
camelCase**. `squareFootage` became the single token `squarefootage`, so a question
about "square footage" could not match it. Combined with dividing by the full
query length including stopwords, **every candidate scored 0.0** and ranking
collapsed to alphabetical order.

Measured before and after, over the four sample datasets:

| Question | Before | After |
|---|---|---|
| square footage against sale price by neighborhood | ecommerce_orders (0.00) | **property_sales (0.57)** |
| monthly mrr trend by plan tier | ecommerce_orders (0.00) | **saas_revenue (0.36)** |
| sessions by weekday and hour of day | web_traffic (0.086) | **web_traffic (0.60)** |
| revenue by product category | — | ecommerce_orders (0.20) vs saas_revenue (0.13) → correctly ambiguous, goes to the model |

All three clear cases now resolve with **no LLM call**.

## 4. Serving: the model id is load-bearing

**Severity: high**, and non-obvious enough to be worth recording.

`mlx_lm server` honours the `model` field in each request body and loads that
model on demand, *ignoring* the `--model` and `--adapter-path` it was started
with. From `server.py`:

```python
self._adapter_map["default_model"] = self.cli_args.adapter_path   # line 394
adapter_path = self._adapter_map.get(model_path, adapter_path)    # line 478
```

The adapter is registered under the literal key `"default_model"`. **Any other
model id loads the base weights with no adapter**, and a HuggingFace repo id makes
the server download that model first.

Measured on one chartist request, same prompt:

| `model` sent | Result |
|---|---|
| `Qwen/Qwen3.5-9B` | downloaded 13 files from HF, then rambled: 1024 tokens, `finish_reason=length`, `content=null` |
| the real local path | base weights, no adapter: 900 tokens, `finish_reason=length`, `content=null` |
| **`default_model`** | **valid Plotly in 15.1s, 186 tokens, `finish_reason=stop`, contract violations `[]`** |

The default is now `default_model` in both `config.py` and `docker-compose.yml`.
Two further notes for anyone debugging this: when a thinking model does not close
its block, `mlx_lm server` returns the text in `message.reasoning` and leaves
`message.content` as `null`; and a `content=null` reply reaches the chartist as an
empty string, fails the contract check, and silently becomes a fallback chart.

## 5. A test that could not fail

My own first smoke test reported **PASS** while the chart had actually been drawn
by the deterministic fallback — the model's output had been rejected by the
contract check. The test only asked "did a figure render", which cannot
distinguish a working model from a working fallback.

**Fixed:** fallback code now carries a marker comment, `/generate` returns the
generated code and a `used_fallback` flag, and the smoke test treats a fallback
chart as a failure with the offending code attached.

---

## Other defects found and fixed

| | Severity |
|---|---|
| `run_agent_workflow` discarded the caller's source and charted a hardcoded `abu_dhabi_population_density.csv` on **every** request | high |
| `POST /generate` had **no authentication** — the only open route on the router, and the most expensive operation in the API. The Next proxy also dropped the bearer token, which is *why* it had to be open | high |
| The graph had no error routing. A detective failure returned a message, then the chartist ran against an empty schema and the executor raised `KeyError` — a failed lookup crashed the request instead of reporting itself | high |
| `UPLOAD_DIR` defaulted to a CWD-relative `backend/uploads`, resolving to `backend/backend/uploads` when uvicorn ran from `backend/` | medium |
| Agents and the compiled graph were built at import time, opening three chat clients on import | medium |
| `SECRET_KEY` and a real Fernet `ENCRYPTION_KEY` are committed to the repo, so tokens can be forged and stored DB credentials decrypted by anyone with the source | high, **not fully fixed** |
| Debug `print()` calls throughout, including one dumping the whole generated program to stdout | low |
| ~800 lines unreachable (`langgraph_detective_agent.py`, `langgraph_tools.py`, `tool_registry.py`) | low |

---

## Principles worth keeping

1. **Do not ask a model what you can compute.** Source ranking, chart-type
   keywords and column hints are deterministic. The model is for genuine
   ambiguity.
2. **One decision per call**, with a closed label set.
3. **Show the output, don't name a schema.** A literal example beats a reference
   to a Pydantic class the model cannot see.
4. **Avoid multi-turn tool calling** at this size. A numbered multiple-choice
   question is the reliable shape.
5. **Parse leniently, fall back deterministically** — and make the fallback
   *visible*, or it will mask the failure it exists to survive.
6. **Greedy decoding** for anything infrastructural: the same question should
   produce the same chart.
7. **For a fine-tuned role, the serve-time prompt must match the training
   distribution** — byte for byte if possible. This is the easiest win to lose,
   and the loss is invisible without an eval.

## Still open

- The committed secrets remain the defaults so the demo runs; `make secrets`
  generates replacements and startup warns while they are in use. The values in
  git history are permanently compromised and should be considered public.
- `SafeExecutor` blocks relative-path file reads but not absolute ones (recorded
  in the platform-correctness plan, task 7).
- The canvas still keeps its data-source list in `localStorage` rather than
  reading the backend; the backend now builds candidates from its own DB, so the
  mismatch no longer affects correctness, but the two lists can disagree.
- The chartist's weakest measured buckets are `treemap_funnel_waterfall` (24%
  render) and shape fidelity on `area` and `heatmap`. Both are training-data
  problems, not harness problems.
