# Agent Notes

## Repo Reality (not a single app)
- This repo contains multiple independent projects: `backend/` (FastAPI), `byd-web/` (Next.js), `chartist-finetune/` (the fine-tune pipeline), `web-crawler/` (Scrapy), and `langchain-archeticture/` (standalone LangGraph example).
- There IS now a top-level runner: root `Makefile` and `docker-compose.yml` drive backend + frontend + Postgres together. `make help` lists targets; `make doctor` reports what is missing. Individual projects still work standalone.

## Known-good Commands
- Whole stack: `make setup`, then `make serve-model` (terminal 1) and `make up` (terminal 2), then `make smoke` to prove it end to end.
- Frontend (`byd-web/`): `npm run dev`, `npm run lint`, `npm run build`.
- Backend (`backend/`): `docker compose up -d` from the repo root, or local API with `uvicorn app.main:app --reload --port 8000`.
- Sample data: `make sample-data` writes four seeded CSVs into `backend/uploads/` (gitignored, so regenerate after a clone).
- Web crawler (`web-crawler/`): `scrapy crawl plotly_python -s CLOSESPIDER_PAGECOUNT=10 -O plotly_examples_sample.jsonl` for a short run; omit `CLOSESPIDER_PAGECOUNT` for full crawl.

## Backend gotchas that are easy to miss
- `backend/app/main.py` creates tables on startup with `Base.metadata.create_all(...)`; there are no Alembic migrations in repo.
- `backend/app/services/agents/workflow.py` currently ignores caller-provided source hints and forcibly sets:
  - selected source: `/app/uploads/abu_dhabi_population_density.csv`
  - available sources: only that file
  This will break normal multi-source behavior until removed.
- `backend/.env.example` sets `UPLOAD_DIR=backend/uploads`. Because this is resolved from current working directory, launching uvicorn from `backend/` resolves to `backend/backend/uploads` (not `backend/uploads`). Set `UPLOAD_DIR` explicitly for local runs.
- Dashboard generation depends on Ollama (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`) and can run long; frontend proxy and backend both include timeout handling.

## Frontend integration details
- Frontend backend URL resolution in `byd-web/app/api/dashboard/generate/route.ts`: `BACKEND_API_URL` -> `NEXT_PUBLIC_API_BASE_URL` -> `http://127.0.0.1:8000`.
- General API helpers use `NEXT_PUBLIC_API_BASE_URL` with default `http://localhost:8000` in `byd-web/lib/backend.ts`.
- Auth/session are localStorage-based (`promptdash_session_user`, `promptdash_access_token`) in `byd-web/lib/auth.ts`; no cookie/session middleware.
- Routes after the UI rebuild: `/` reports home, `/reports/new`, `/reports/[id]` (the canvas), `/data` (sources), `/login`. The old `/dashboard/new`, `/dashboard/new-canvas` and `/settings/data-sources` are now redirects, not pages.
- Canvas blocks are backend-owned (`backend/app/api/v1/endpoints/blocks.py`, table `report_blocks`), not localStorage. `POST /blocks/generate` runs the agent workflow; `PUT /blocks/layout` persists drag/resize.
- An all-`indicator` Plotly figure is stored as a `metric` block at tile size and titled with the label the model wrote. That is the KPI stat-card path; there is no separate "make me a KPI" endpoint.
- `byd-web/DESIGN.md` carries the design system (tokens, components, the Plotly re-theme contract). Read it before touching UI.
- `Compare models` (`/compare`, `backend/app/api/v1/endpoints/comparison.py`) runs the same question on the local chartist and on Claude Opus 5.5. Fairness is by REUSE, not by copying: one sampled DataFrame, one schema block, one planner call, the same `ChartistAgent` class (same prompt from `chartist_contract.py`, same sanitiser, same contract validation, same fallback) and the same `SafeExecutor`. `ChartistAgent(llm=None, generator=...)` swaps only the text-generation step.
- `backend/app/services/claude_chartist.py` is the only Anthropic SDK code; `llm.py` stays OpenAI-shaped for the MLX server and is untouched. Opus notes: thinking cannot be disabled, `temperature` is rejected, `output_config={"effort": ...}` is the only dial (`CLAUDE_EFFORT`, default medium), and server-side refusal fallbacks are deliberately OFF — a silent model switch would invalidate the comparison, so a refusal is surfaced as a failed cell.
- Comparison results are NOT persisted. It is an experiment, not a report. Cost is shown on screen from real `usage` tokens at published rates; a 4-question run measured $0.158.
- `backend/uploads/gapminder.csv` is a public dataset (plotly/datasets); `backend/uploads/` is gitignored, so re-fetch after a clone: `curl -sS -o backend/uploads/gapminder.csv https://raw.githubusercontent.com/plotly/datasets/master/gapminder_with_codes.csv`. Measured there: local 2/4 rendered vs Opus 4/4; both local failures were indicator/KPI traces, which the fine-tune evaluation already lists as a weak bucket.
- Four agents now: planner (chart type), detective (which source), chartist (the fine-tuned one), narrator (`agents/narrator.py`, writes the block title). The narrator never fails a request — it falls back to the question, tidied.
- `agents/architect.py` plans a WHOLE dashboard. Its structure is deliberately deterministic: the columns are profiled from a real sample (dates / measures / groupings) and the sections are composed from that in reading order. Asking an SLM for a six-block JSON plan gets you columns that do not exist. The model still writes every title.
- Gotcha that cost real time: current pandas gives string columns a `str` dtype, NOT `object`. `series.dtype == object` silently classified every label column as unusable. Use `pd.api.types.is_string_dtype`. Also, never flag a float as an identifier by uniqueness — a continuous measure is naturally almost all-unique.
- The dashboard build takes an optional `brief` ("churn by region"). It does not rewrite the section order — it reorders which measures and groupings lead, by camelCase-aware token overlap with light stemming, so `churn` finds `churnedSeats`. Deterministic on purpose: the answer has to be a real column name and this cannot return one that is not.
- Number formatting is a RENDER-layer job in `byd-web/components/plot.tsx`, applied to every figure from every model: separators on KPI numbers, value labels above bars (<=12 bars), currency on the money axis. Currency is read from field/axis names (`mrrUsd` -> `$`); `NEXT_PUBLIC_DEFAULT_CURRENCY` covers columns that name none. Never invent a currency for an unlabelled column.
- An invalid or SI `valueformat` from the model is overridden; a valid deliberate one is kept. `D3_FORMAT` exists because a colour (`#1f77b4`) once landed in that field and Plotly ignored it silently.
- `_run_executor` in `workflow.py` repairs invented Plotly properties FROM the error message (`Invalid property specified ... 'valuecolor'`) and retries once. It takes Plotly's own "Did you mean X?" suggestion when X is NOT already a key in that dict, and drops the property otherwise — Plotly suggests on spelling, not meaning, and renaming `valuecolor` onto an existing `valueformat` made a duplicate key whose junk value won, silently killing a KPI's number format. The value removal is bracket- and quote-aware and the result must `compile()` first — a naive "up to the next comma" regex cut `{'size': 48}` in half and turned a bad property into a SyntaxError. `chartist.py` separately renames `valueprefix`/`valuesuffix`, which carry meaning and should be kept rather than dropped.
- `POST /dashboard/{id}/blocks/dashboard` streams SSE (`plan`, `step`, `block`, `skipped`, `done`). Five or six generations is ~90s, so blocks are reported as they are created; one failed block is `skipped`, not a failed build. Client parser is `generateDashboard` in `byd-web/lib/blocks.ts` (POST, so EventSource is out).
- Database sources are real: `backend/app/services/db_sources.py` holds the whole path. PostgreSQL (psycopg2) and MySQL/MariaDB (pymysql) only — those are the two whose drivers install cleanly and spell `connect_timeout` the same way. `GET /data-sources/database-kinds` reports which drivers the server actually has.
- A connection is probed before it is stored (`POST /data-sources/db-connection` connects first and 400s with the driver's own error). `POST /data-sources/db-connection/test` is the same probe without saving.
- The agent sees TABLES, not connections: `candidates_for()` turns each table into a candidate `{id: "<source id>:<table>", type: "db", columns}`, the detective ranks it beside files, and the executor loads it with `load_table_by_id` into the same `df`. Nothing downstream knows the difference. Table names are never interpolated into SQL — tables are checked against the live list then reflected.
- `MAX_ROWS = 500_000`: a chart reads the whole table so totals are real, and above that it refuses with the row count rather than silently charting a LIMIT.
- `_user_sources` in `blocks.py` now scopes generation to a report's own `data_source_ids` when it has any. Before this the picker recorded a choice and generation ignored it.
- Note blocks store HTML, not plain text. `byd-web/lib/rich-text.ts` is the trust boundary: it sanitises on commit AND on render (allowlist of 14 tags, no attributes except a validated href). Never render `text_body` without it. Legacy plain-text bodies still render — `toHtml` handles both.
- Plotly is bundled (`plotly.js-dist-min`, lazily imported in `components/plot.tsx`), never the CDN script — the CDN broke the local-only claim and pinned an old Plotly.
- Gotcha: `react-grid-layout` positions items with `transform`. Any CSS animation that touches `transform` must sit on an element INSIDE the grid item; on the item itself, `animation-fill-mode: both` makes the keyframes' final `transform: none` beat the inline grid transform and all blocks pile up top-left. `globals.css` keeps a `.react-grid-item.block-settle { animation: none }` guard.
- `react-grid-layout` v2's classic API lives at `react-grid-layout/legacy`; the root export is the new rewrite and has a different surface.

## Verification shortcuts
- `make smoke` is the fastest real check: health, register, login, that `/generate` refuses an anonymous call, then a real chart with real data points. It fails if the chart came from the deterministic fallback rather than the model, so a green result means the model actually worked.
- `make doctor` reports docker, api, model server, sample CSVs, adapter and base model in one line each.
- `GET /health` reports the active backend, model, upload dir and whether the committed placeholder secrets are in use.
- There is no established Python test suite config (`pytest.ini`/`pyproject.toml` absent). `backend/test_agent.py` is a manual workflow script, not an isolated unit test.
- See `docs/slm-harness-evaluation.md` for the prompt/harness review and the measured before/after numbers.

## Data and generated artifacts
- Scraper outputs (`web-crawler/*.jsonl`) and local uploads (`backend/uploads/`) can be large/noisy; avoid unnecessary edits.
- `.agents/` is gitignored at repo root; skill files may exist locally but are not part of tracked project code.
