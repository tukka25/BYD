# Agent Notes

## Repo Reality (not a single app)
- This repo contains multiple independent projects: `backend/` (FastAPI), `byd-web/` (Next.js), `web-crawler/` (Scrapy), and `langchain-archeticture/` (standalone LangGraph example).
- There is no top-level workspace runner (no root `package.json`, Makefile, or CI workflows). Run commands from each project directory.

## Known-good Commands
- Frontend (`byd-web/`): `npm run dev`, `npm run lint`, `npm run build`.
- Backend (`backend/`): `docker compose up -d` (Postgres + API container), or local API with `pip install -r requirements.txt` then `uvicorn app.main:app --reload --port 8000`.
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
- There is no established Python test suite config (`pytest.ini`/`pyproject.toml` absent). `backend/test_agent.py` is a manual workflow script, not an isolated unit test.
- For focused checks after backend edits, prefer hitting the affected FastAPI endpoint(s) directly over assuming automated tests exist.

## Data and generated artifacts
- Scraper outputs (`web-crawler/*.jsonl`) and local uploads (`backend/uploads/`) can be large/noisy; avoid unnecessary edits.
- `.agents/` is gitignored at repo root; skill files may exist locally but are not part of tracked project code.
