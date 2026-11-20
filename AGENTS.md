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
