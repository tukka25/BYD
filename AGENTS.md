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

## Verification shortcuts
- `make smoke` is the fastest real check: health, register, login, that `/generate` refuses an anonymous call, then a real chart with real data points. It fails if the chart came from the deterministic fallback rather than the model, so a green result means the model actually worked.
- `make doctor` reports docker, api, model server, sample CSVs, adapter and base model in one line each.
- `GET /health` reports the active backend, model, upload dir and whether the committed placeholder secrets are in use.
- There is no established Python test suite config (`pytest.ini`/`pyproject.toml` absent). `backend/test_agent.py` is a manual workflow script, not an isolated unit test.
- See `docs/slm-harness-evaluation.md` for the prompt/harness review and the measured before/after numbers.

## Data and generated artifacts
- Scraper outputs (`web-crawler/*.jsonl`) and local uploads (`backend/uploads/`) can be large/noisy; avoid unnecessary edits.
- `.agents/` is gitignored at repo root; skill files may exist locally but are not part of tracked project code.
