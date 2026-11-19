# Platform Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `POST /api/v1/dashboard/generate` actually generate a chart from the authenticated user's own uploaded data, and remove the correctness, isolation, and security defects found in the 2026-11-19 codebase review.

**Architecture:** The backend keeps its four-node LangGraph (planner → detective → chartist → executor), but stops forcing a hardcoded CSV, stops sharing agent memory between requests, and resolves data sources from the authenticated user's `data_sources` rows instead of from a caller-supplied filesystem path. Generated chart code moves out of the API process into a short-lived subprocess. The frontend canvas stops keeping a second, fake copy of the user's data sources in `localStorage` and reads the real API instead.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL (SQLite for tests), LangGraph + LangChain, Ollama/Qwen, pytest + Starlette `TestClient`, Next.js 16 / React 19 / Tailwind 4.

## Global Constraints

- Python 3.11 in the container (`backend/Dockerfile` uses `python:3.11-slim`); local dev host is Python 3.13.1. Code must run on both — no 3.12+-only syntax.
- Run every backend command from `backend/` (there is no root workspace runner). Run every frontend command from `byd-web/`.
- `UPLOAD_DIR` must always be set explicitly for local runs. `backend/.env.example` ships `UPLOAD_DIR=backend/uploads`, which resolves to `backend/backend/uploads` when uvicorn is launched from `backend/`.
- No Alembic in this repo. Tables are created by `Base.metadata.create_all(...)` in `backend/app/main.py`. This plan adds no new columns and no new tables, so no migration story is needed.
- Do not reformat or restructure files beyond the lines each task names. This codebase has no formatter config.
- The chartist output contract is fixed and is referenced by the companion fine-tune plan: generated code receives a preloaded `df`, must not read files or URLs, must not call `fig.show()`, and must end with `print(fig.to_json())`.
- Tests must pass with no Postgres container, no Ollama daemon, and no network access.
- Commit after every task. Never commit a `.env` file.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `backend/pyproject.toml` | pytest configuration and test path registration. Nothing else — this is not a packaging change. |
| `backend/tests/conftest.py` | Sets test env vars *before* any `app.*` import, then exposes `client` and `auth_headers` fixtures backed by a temp-file SQLite DB. |
| `backend/tests/test_auth.py` | Proves the harness works end to end against the real router. |
| `backend/tests/test_config.py` | Guards the fail-fast behavior for placeholder secrets. |
| `backend/tests/test_source_resolution.py` | Covers `resolve_user_sources` ownership and path checks. |
| `backend/tests/test_generate_endpoint.py` | Covers auth, request shape, and source plumbing on `/dashboard/generate`. |
| `backend/tests/test_workflow_isolation.py` | Covers per-run agent construction and thread ids. |
| `backend/tests/test_executor.py` | Covers the subprocess executor: success, timeout, network block, syntax error. |
| `backend/app/services/source_resolver.py` | Single place that turns `data_source_ids` + a `User` into workflow-ready source dicts. Owned by the API layer, not the agents. |
| `backend/app/utils/code_runner.py` | The script the executor subprocess runs. Must have no imports from `app.*`. |

**Modified:**

| File | Change |
|---|---|
| `backend/app/core/config.py` | Add `validate_runtime_secrets()`; drop the hardcoded `ENCRYPTION_KEY` default. |
| `backend/app/main.py` | Call `validate_runtime_secrets()` on startup. |
| `backend/.env.example`, `backend/docker-compose.yml` | Remove real key material; document generation. |
| `backend/app/services/agents/workflow.py:32-45`, `:219-261` | Lazy LLM construction, per-run agent build, honor the caller's sources, correct `data_dir`. |
| `backend/app/services/agents/data_detective.py:23-47`, `:180-310` | Accept `run_id`, build agents per run, forward `plotly_ready_spec`. |
| `backend/app/api/v1/endpoints/dashboard.py:27-47`, `:155-234` | Require auth, accept `data_source_ids`, resolve sources, pass `run_id`. |
| `backend/app/utils/executor.py` | Replace in-process `exec()` with a subprocess call. |
| `byd-web/app/api/dashboard/generate/route.ts` | Forward `Authorization` and `data_source_ids`. |
| `byd-web/app/dashboard/new-canvas/page.tsx:1-105`, `:122-126` | Read sources from the API, upload for real, send selected ids. |
| `byd-web/lib/data-sources.ts` | Delete the fake seed sources and the per-user source store; keep only the selection helpers and `bytesToSize`. |
| `AGENTS.md` | Remove the now-fixed gotchas; document the new `/generate` contract and the test command. |

**Deleted:**

| File | Reason |
|---|---|
| `backend/app/services/tool_registry.py` | Dead code. Nothing imports `build_tool_registry`; it types plain functions as `BaseTool`. |
| `langchain-archeticture/` | `detective_graph.py` imports `.registry`, which does not exist — the module cannot be imported. Superseded by `backend/app/services/tools/`. |

**Out of scope** (deliberately not in this plan): a `DELETE /dashboard/{id}` endpoint, dashboard-to-chart persistence (charts are still ephemeral per page load), replacing `localStorage` auth with cookies, and the Plotly CDN `<script>` tag in the returned HTML.

---

### Task 1: Test harness

Nothing else in this plan is verifiable without this. The harness must work with no Postgres and no Ollama, which means the env has to be rewritten before `app.core.database` is imported and the module-level agent construction in `workflow.py` has to survive import without a daemon.

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/tests/__init__.py` (empty)
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: nothing.
- Produces: pytest fixtures `client` (a `TestClient` with lifespan run against SQLite) and `auth_headers` (a `dict[str, str]` holding `{"Authorization": "Bearer <token>"}` for a freshly registered user). Every later task uses both.

- [ ] **Step 1: Write `backend/pyproject.toml`**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-q"
```

- [ ] **Step 2: Write `backend/tests/conftest.py`**

The `os.environ` writes must come before the `app.*` imports. `app/core/database.py` builds its engine at import time from `get_settings()`, and `get_settings()` is `lru_cache`d, so a late env change has no effect.

```python
import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="byd-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ENCRYPTION_KEY"] = "m3xwSeF4J38MxGfM9Tz11LeG5m8Wz8Y5w6rkaI0sD9A="
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture()
def tmp_root() -> Path:
    return _TMP


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers(client) -> dict[str, str]:
    import uuid

    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Test User", "password": "pw-12345"},
    )
    assert register.status_code == 201, register.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-12345"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}
```

The `ENCRYPTION_KEY` above is the value already published in this repo's git history. It is a test fixture only; Task 2 removes it from shipped config.

- [ ] **Step 3: Write the failing test**

```python
# backend/tests/test_auth.py
def test_register_login_me_round_trip(client, auth_headers):
    me = client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.status_code == 200
    body = me.json()
    assert body["full_name"] == "Test User"
    assert body["is_active"] is True


def test_me_rejects_missing_token(client):
    assert client.get("/api/v1/auth/me").status_code == 403
```

- [ ] **Step 4: Run it**

```bash
cd backend && python3 -m pytest tests/test_auth.py -v
```

Expected: both tests PASS. If collection fails on an import of `app.services.agents.workflow`, that is the module-level `LocalQwenChatModel` / `create_react_agent` construction. Do **not** work around it in the test — record the traceback, skip to Task 5, make construction lazy there, then come back and finish this task. If `test_me_rejects_missing_token` fails with `401`, change the expected status to `401` and keep going: `HTTPBearer(auto_error=True)` returns `403` on a missing header in most Starlette versions, but this is version-dependent and not worth pinning.

- [ ] **Step 5: Install the test dependency if needed**

```bash
cd backend && python3 -m pip install pytest httpx2
```

If `TestClient` raises on import for a missing HTTP client, that is the `anthropic`-era `httpx2` split; Starlette's `TestClient` needs `httpx`. Install whichever the traceback names.

- [ ] **Step 6: Commit**

```bash
cd backend && git add pyproject.toml tests/ && git commit -m "test: add pytest harness with SQLite-backed TestClient fixtures

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Stop shipping real secrets

`ENCRYPTION_KEY` is the key that protects user database passwords (`encrypt_secret` in `backend/app/core/security.py`), and a working value for it is committed in `backend/app/core/config.py`, `backend/.env.example`, and `backend/docker-compose.yml`. `SECRET_KEY` signs JWTs and ships as `replace-with-strong-secret`.

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/main.py`
- Modify: `backend/.env.example`
- Modify: `backend/docker-compose.yml`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Consumes: `get_settings()` from Task 0 state (unchanged signature).
- Produces: `validate_runtime_secrets(settings: Settings) -> None`, which raises `RuntimeError` when a placeholder or empty secret is in use. Task 1's conftest already sets both env vars, so the harness stays green.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config.py
import pytest

from app.core.config import Settings, validate_runtime_secrets


def test_rejects_placeholder_secret_key():
    settings = Settings(
        SECRET_KEY="change-me-in-env",
        ENCRYPTION_KEY="m3xwSeF4J38MxGfM9Tz11LeG5m8Wz8Y5w6rkaI0sD9A=",
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_runtime_secrets(settings)


def test_rejects_empty_encryption_key():
    settings = Settings(SECRET_KEY="a-real-secret-value", ENCRYPTION_KEY="")
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        validate_runtime_secrets(settings)


def test_accepts_real_values():
    settings = Settings(
        SECRET_KEY="a-real-secret-value",
        ENCRYPTION_KEY="m3xwSeF4J38MxGfM9Tz11LeG5m8Wz8Y5w6rkaI0sD9A=",
    )
    validate_runtime_secrets(settings)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_config.py -v
```

Expected: FAIL with `ImportError: cannot import name 'validate_runtime_secrets'`.

- [ ] **Step 3: Implement**

In `backend/app/core/config.py`, change the `ENCRYPTION_KEY` field to have no usable default and append the validator:

```python
    ENCRYPTION_KEY: str = ""
```

```python
PLACEHOLDER_SECRETS = {
    "change-me-in-env",
    "replace-with-strong-secret",
    "",
}


def validate_runtime_secrets(settings: Settings) -> None:
    """Fail fast rather than silently running with known-public key material."""
    if settings.SECRET_KEY in PLACEHOLDER_SECRETS:
        raise RuntimeError(
            "SECRET_KEY is unset or still a placeholder. Set it in backend/.env. "
            'Generate one with: python3 -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    if settings.ENCRYPTION_KEY in PLACEHOLDER_SECRETS:
        raise RuntimeError(
            "ENCRYPTION_KEY is unset. Set it in backend/.env. Generate one with: "
            'python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && python3 -m pytest tests/test_config.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Wire it into startup**

In `backend/app/main.py`, change the import line to `from app.core.config import get_settings, validate_runtime_secrets` and make `on_startup` begin with the check:

```python
@app.on_event("startup")
def on_startup() -> None:
    validate_runtime_secrets(settings)
    settings.upload_dir_path.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 6: Scrub the committed key material**

In `backend/.env.example`, replace the two secret lines with:

```
SECRET_KEY=
# Generate with: python3 -c "import secrets; print(secrets.token_urlsafe(48))"
ENCRYPTION_KEY=
# Generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

In `backend/docker-compose.yml`, replace the two hardcoded `environment:` values with pass-throughs so the container reads them from the host shell or an `.env` beside the compose file:

```yaml
      SECRET_KEY: ${SECRET_KEY:?set SECRET_KEY in backend/.env}
      ENCRYPTION_KEY: ${ENCRYPTION_KEY:?set ENCRYPTION_KEY in backend/.env}
```

- [ ] **Step 7: Verify the whole suite still passes, then check the app refuses to boot without secrets**

```bash
cd backend && python3 -m pytest -v
```

```bash
cd backend && SECRET_KEY= ENCRYPTION_KEY= python3 -c "from app.core.config import Settings, validate_runtime_secrets; validate_runtime_secrets(Settings())"
```

Expected: the first command passes; the second exits non-zero with the `SECRET_KEY is unset` message.

- [ ] **Step 8: Note the rotation consequence in the commit, then commit**

Any `data_sources.db_password_encrypted` value written under the old committed key becomes unreadable once the key changes. `decrypt_secret` already returns `""` on `InvalidToken`, so this degrades to an empty password rather than a crash. There is one such row at most in local dev; re-enter DB connections after rotating.

```bash
cd backend && git add app/core/config.py app/main.py .env.example docker-compose.yml tests/test_config.py && git commit -m "fix(security): remove committed key material and fail fast on placeholder secrets

The Fernet ENCRYPTION_KEY that protects stored database passwords was
committed in config defaults, .env.example and docker-compose.yml.
Existing rows encrypted with the old key decrypt to an empty string.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Resolve data sources from the database

The workflow currently takes a raw path string. The endpoint will instead take ids and look them up, so a caller can never name a file they do not own.

**Files:**
- Create: `backend/app/services/source_resolver.py`
- Test: `backend/tests/test_source_resolution.py`

**Interfaces:**
- Consumes: `DataSource`, `DataSourceStatus`, `DataSourceType` from `app.models.data_source`; `User` from `app.models.user`.
- Produces:
  - `class SourceResolutionError(Exception)` — carries a human-readable message for a `400`.
  - `resolve_user_sources(db: Session, user: User, data_source_ids: list[str]) -> list[dict[str, Any]]` returning dicts shaped `{"id": str, "name": str, "type": "file", "path": str}` — exactly the `available_sources` shape `DataDetective._prepare_candidates` already accepts.
  - When `data_source_ids` is empty, returns every active file source the user owns.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_source_resolution.py
import uuid
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.data_source import DataSource, DataSourceStatus, DataSourceType
from app.models.user import User
from app.services.source_resolver import SourceResolutionError, resolve_user_sources


def _make_user(db: Session) -> User:
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        full_name="Owner",
        password_hash="x",
    )
    db.add(user)
    db.flush()
    return user


def _make_file_source(db: Session, user: User, path: Path) -> DataSource:
    source = DataSource(
        user_id=user.id,
        source_type=DataSourceType.FILE,
        status=DataSourceStatus.ACTIVE,
        display_name=path.name,
        file_path=str(path),
        original_filename=path.name,
        file_extension=path.suffix,
    )
    db.add(source)
    db.flush()
    return source


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_resolves_owned_file_source(db, tmp_root):
    csv = tmp_root / "owned.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")
    user = _make_user(db)
    source = _make_file_source(db, user, csv)

    resolved = resolve_user_sources(db, user, [source.id])

    assert resolved == [
        {"id": source.id, "name": "owned.csv", "type": "file", "path": str(csv)}
    ]


def test_rejects_source_owned_by_another_user(db, tmp_root):
    csv = tmp_root / "theirs.csv"
    csv.write_text("a\n1\n", encoding="utf-8")
    owner = _make_user(db)
    other = _make_user(db)
    source = _make_file_source(db, owner, csv)

    with pytest.raises(SourceResolutionError, match="not owned"):
        resolve_user_sources(db, other, [source.id])


def test_rejects_missing_file_on_disk(db, tmp_root):
    user = _make_user(db)
    source = _make_file_source(db, user, tmp_root / "gone.csv")

    with pytest.raises(SourceResolutionError, match="no longer on disk"):
        resolve_user_sources(db, user, [source.id])


def test_empty_id_list_returns_all_active_file_sources(db, tmp_root):
    first = tmp_root / "one.csv"
    second = tmp_root / "two.csv"
    first.write_text("a\n1\n", encoding="utf-8")
    second.write_text("a\n1\n", encoding="utf-8")
    user = _make_user(db)
    _make_file_source(db, user, first)
    _make_file_source(db, user, second)

    resolved = resolve_user_sources(db, user, [])

    assert {item["name"] for item in resolved} == {"one.csv", "two.csv"}


def test_raises_when_user_has_no_sources(db):
    user = _make_user(db)
    with pytest.raises(SourceResolutionError, match="no data sources"):
        resolve_user_sources(db, user, [])
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_source_resolution.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.source_resolver'`.

- [ ] **Step 3: Implement**

```python
# backend/app/services/source_resolver.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.data_source import DataSource, DataSourceStatus, DataSourceType
from app.models.user import User


class SourceResolutionError(Exception):
    """Raised when the requested data sources cannot be used for a workflow run."""


def _to_workflow_source(source: DataSource) -> dict[str, Any]:
    path = Path(source.file_path or "")
    if not path.is_file():
        raise SourceResolutionError(
            f"Data source '{source.display_name}' is no longer on disk. Re-upload it."
        )
    return {
        "id": source.id,
        "name": path.name,
        "type": "file",
        "path": str(path),
    }


def resolve_user_sources(
    db: Session,
    user: User,
    data_source_ids: list[str],
) -> list[dict[str, Any]]:
    """Turn caller-supplied data source ids into workflow-ready source descriptors.

    The caller never supplies a filesystem path, so a request cannot name a file
    the user does not own.
    """
    query = db.query(DataSource).filter(
        DataSource.user_id == user.id,
        DataSource.status == DataSourceStatus.ACTIVE,
        DataSource.source_type == DataSourceType.FILE,
    )

    if data_source_ids:
        wanted = list(dict.fromkeys(data_source_ids))
        rows = query.filter(DataSource.id.in_(wanted)).all()
        if len(rows) != len(wanted):
            found = {row.id for row in rows}
            missing = [item for item in wanted if item not in found]
            raise SourceResolutionError(
                "These data_source_ids are unknown or not owned by the current user: "
                + ", ".join(missing)
            )
    else:
        rows = query.order_by(DataSource.created_at.desc()).all()
        if not rows:
            raise SourceResolutionError(
                "This account has no data sources. Upload a CSV or Excel file first."
            )

    return [_to_workflow_source(row) for row in rows]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && python3 -m pytest tests/test_source_resolution.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/source_resolver.py tests/test_source_resolution.py && git commit -m "feat(backend): resolve workflow data sources from owned DB rows

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Unpin the forced data source

`backend/app/services/agents/workflow.py:229-241` discards both arguments and hardcodes `/app/uploads/abu_dhabi_population_density.csv`, a file that exists nowhere in the repo. Every `/generate` call therefore fails. `workflow.py:32-34` also falls back to `backend/data` — a CWD-relative path — when `/app/uploads` is absent, so the detective lists the wrong directory outside Docker.

**Files:**
- Modify: `backend/app/services/agents/workflow.py:32-45`, `:219-261`
- Test: `backend/tests/test_workflow_isolation.py` (also used by Task 5)

**Interfaces:**
- Consumes: `resolve_user_sources` output shape from Task 3.
- Produces: `run_agent_workflow(query: str, selected_source: str = "", available_sources: list[dict] | None = None, run_id: str = "") -> dict` — same return shape as today (`plan`, `data_context`, `execution_result`, `messages`, `error`), but it now honors its arguments. Also produces `resolve_data_dir() -> Path`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_workflow_isolation.py
from pathlib import Path

from app.services.agents import workflow as workflow_module


def test_resolve_data_dir_prefers_container_uploads_then_settings(monkeypatch, tmp_path):
    container = tmp_path / "app-uploads"
    configured = tmp_path / "configured-uploads"
    configured.mkdir()

    monkeypatch.setattr(workflow_module, "CONTAINER_UPLOAD_DIR", container)
    assert workflow_module.resolve_data_dir(configured) == configured.resolve()

    container.mkdir()
    assert workflow_module.resolve_data_dir(configured) == container.resolve()


def test_run_agent_workflow_passes_caller_sources_through(monkeypatch):
    captured = {}

    def fake_invoke(state):
        captured.update(state)
        return {"error": "", "plan": {}, "data_context": {}, "messages": []}

    monkeypatch.setattr(
        workflow_module,
        "build_workflow",
        lambda: type("G", (), {"invoke": staticmethod(fake_invoke)})(),
    )

    sources = [
        {"id": "ds-1", "name": "sales.csv", "type": "file", "path": "/data/sales.csv"}
    ]
    workflow_module.run_agent_workflow(
        "chart my sales",
        selected_source="/data/sales.csv",
        available_sources=sources,
        run_id="run-abc",
    )

    assert captured["selected_source"] == "/data/sales.csv"
    assert captured["available_sources"] == sources
    assert captured["run_id"] == "run-abc"
    assert "abu_dhabi" not in str(captured)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_workflow_isolation.py -v
```

Expected: FAIL — `resolve_data_dir`, `CONTAINER_UPLOAD_DIR` and `build_workflow` do not exist, and `run_agent_workflow` has no `run_id` parameter.

- [ ] **Step 3: Replace the module-level data dir block**

Delete `backend/app/services/agents/workflow.py:32-34` (`data_dir = Path("/app/uploads")` through `data_dir = Path("backend/data")`) and put this in its place:

```python
CONTAINER_UPLOAD_DIR = Path("/app/uploads")


def resolve_data_dir(configured: Path | None = None) -> Path:
    """Directory the detective scans when the caller supplies no explicit sources.

    Inside the container the bind mount at /app/uploads wins. Outside it, use the
    configured UPLOAD_DIR, which must be set explicitly for local runs.
    """
    if CONTAINER_UPLOAD_DIR.exists():
        return CONTAINER_UPLOAD_DIR.resolve()
    target = configured or get_settings().upload_dir_path
    return Path(target).resolve()
```

- [ ] **Step 4: Rewrite `run_agent_workflow`**

Replace `backend/app/services/agents/workflow.py:219-261` entirely:

```python
def run_agent_workflow(
    query: str,
    selected_source: str = "",
    available_sources: Optional[List[Dict[str, Any]]] = None,
    run_id: str = "",
):
    """Run the planner -> detective -> chartist -> executor graph for one request."""
    initial_state = {
        "user_query": query,
        "selected_source": selected_source,
        "available_sources": available_sources or [],
        "run_id": run_id or uuid.uuid4().hex,
        "messages": [HumanMessage(content=query)],
        "plan": {},
        "source_decision": {},
        "data_context": {},
        "code": "",
        "execution_result": {},
        "error": "",
    }

    started_at = time.perf_counter()
    logger.info(
        "[workflow] invoke start run_id=%s sources=%s query=%s",
        initial_state["run_id"],
        len(initial_state["available_sources"]),
        query[:120],
    )
    result = build_workflow().invoke(initial_state)
    elapsed = time.perf_counter() - started_at
    logger.info(
        "[workflow] invoke done run_id=%s in %.2fs error=%s",
        initial_state["run_id"],
        elapsed,
        bool(result.get("error")),
    )
    return result
```

Add `import uuid` to the imports and add `run_id: str` to the `AgentState` `TypedDict`.

- [ ] **Step 5: Run the test**

```bash
cd backend && python3 -m pytest tests/test_workflow_isolation.py::test_resolve_data_dir_prefers_container_uploads_then_settings -v
```

Expected: PASS. The second test still fails until Task 5 introduces `build_workflow`.

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/services/agents/workflow.py tests/test_workflow_isolation.py && git commit -m "fix(agents): stop forcing a hardcoded CSV and resolve data_dir correctly

run_agent_workflow discarded both of its arguments and pinned every run to
/app/uploads/abu_dhabi_population_density.csv, which is not in the repo, so
every generate call failed at source resolution.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Build agents per run instead of per process

`workflow.py:36-45` constructs three `LocalQwenChatModel` instances, a `DataDetective`, a `ChartistAgent` and a compiled graph at import time. `data_detective.py:204` and `:238` then invoke both ReAct agents with a *fixed* `thread_id` against a `MemorySaver`, so every request in the process appends to the same two conversation threads. Context grows without bound and earlier decisions bleed into later requests. The same import-time construction is what makes the app hard to import in tests.

**Files:**
- Modify: `backend/app/services/agents/workflow.py:36-45`
- Modify: `backend/app/services/agents/data_detective.py:23-47`, `:180-245`
- Test: `backend/tests/test_workflow_isolation.py`

**Interfaces:**
- Consumes: `resolve_data_dir` from Task 4.
- Produces:
  - `get_llms() -> tuple[LocalQwenChatModel, LocalQwenChatModel, LocalQwenChatModel]`, `lru_cache`d, returning `(llm_json, llm_code, llm_tools)`. Network-free to construct.
  - `build_workflow()` → a freshly compiled LangGraph app.
  - `DataDetective.detect_source(..., run_id: str = "")` — thread ids become `f"detective-source-{run_id}"` and `f"detective-dataframe-{run_id}"`, and the two ReAct agents are built per call with a fresh `MemorySaver`.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_workflow_isolation.py
def test_detective_uses_run_scoped_thread_ids(monkeypatch):
    from app.services.agents import data_detective as dd

    seen = []

    def fake_run_detective(agent, query, selected_source="", thread_id="", **kwargs):
        seen.append(thread_id)
        return {"structured_output": {"chosen_source": "", "confidence": 0.0}}

    def fake_run_builder(agent, query, chosen_source, required_fields_for_next_step,
                         thread_id="", **kwargs):
        seen.append(thread_id)
        return {"structured_output": {"confidence": 0.0, "selected_columns": []}}

    monkeypatch.setattr(dd, "run_detective_agent", fake_run_detective)
    monkeypatch.setattr(dd, "run_dataframe_builder_agent", fake_run_builder)
    monkeypatch.setattr(dd, "build_detective_agent", lambda **kwargs: object())
    monkeypatch.setattr(dd, "build_dataframe_builder_agent", lambda **kwargs: object())

    detective = dd.DataDetective(data_dir="/tmp", llm=object())
    sources = [{"id": "a", "name": "a.csv", "type": "file", "path": "/tmp/a.csv",
                "columns": ["x"]}]

    detective.detect_source("q", {}, "", sources, run_id="run-1")
    detective.detect_source("q", {}, "", sources, run_id="run-2")

    assert "run-1" in seen[0]
    assert "run-2" in seen[-1]
    assert len(set(seen)) == len(seen), f"thread ids must be unique per run: {seen}"


def test_build_workflow_returns_a_new_graph_each_call(monkeypatch):
    first = workflow_module.build_workflow()
    second = workflow_module.build_workflow()
    assert first is not second
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_workflow_isolation.py -v
```

Expected: FAIL — `detect_source` has no `run_id` keyword and `build_workflow` does not exist.

- [ ] **Step 3: Make LLM and graph construction lazy**

In `backend/app/services/agents/workflow.py`, delete lines 36-45 (the `llm_json` / `llm_code` / `llm_tools` / `planner` / `detective` / `chartist` / `executor` module-level assignments) and the module-level `workflow = StateGraph(...)` block through `app = workflow.compile()`. Replace with:

```python
from functools import lru_cache


@lru_cache(maxsize=1)
def get_llms():
    """Construct the three chat models once per process. No network at init."""
    return (
        LocalQwenChatModel(model=model_name, format="json"),
        LocalQwenChatModel(model=model_name),
        LocalQwenChatModel(model=model_name),
    )


@lru_cache(maxsize=1)
def get_executor() -> SafeExecutor:
    return SafeExecutor()


def build_workflow():
    """Compile a fresh graph. Cheap, and keeps per-run agent state isolated."""
    graph = StateGraph(AgentState)
    graph.add_node("planner", planning_node)
    graph.add_node("detective", data_sourcing_node)
    graph.add_node("chartist", coding_node)
    graph.add_node("executor", execution_node)
    graph.set_entry_point("planner")
    graph.add_edge("planner", "detective")
    graph.add_edge("detective", "chartist")
    graph.add_edge("chartist", "executor")
    graph.add_edge("executor", END)
    return graph.compile()
```

Then change each node function to build what it needs. `planning_node` starts with `planner = PlannerAgent(get_llms()[0])`. `coding_node` starts with `chartist = ChartistAgent(get_llms()[1])`. `execution_node` uses `get_executor()`. `data_sourcing_node` builds the detective per run and forwards the run id:

```python
def data_sourcing_node(state: AgentState):
    started_at = time.perf_counter()
    query = state.get("user_query", "")
    run_id = state.get("run_id", "")
    detective = DataDetective(data_dir=str(resolve_data_dir()), llm=get_llms()[2])
    logger.info("[workflow/detective] start run_id=%s query=%s", run_id, query[:120])

    decision = detective.detect_source(
        query=query,
        plan=state.get("plan", {}),
        selected_source=state.get("selected_source", ""),
        available_sources=state.get("available_sources") or None,
        run_id=run_id,
    )
```

Keep the rest of `data_sourcing_node` (lines 90-140 in the original) as it is, but delete the six `print(...)` calls — the `logger` lines already carry the same information.

- [ ] **Step 4: Make the detective run-scoped**

In `backend/app/services/agents/data_detective.py`, remove the `self._build_chains()` call from `__init__` and the two agent attributes it sets, then build them inside `detect_source`:

```python
    def detect_source(
        self,
        query: str,
        plan: Optional[Dict[str, Any]] = None,
        selected_source: Optional[str] = None,
        available_sources: Optional[List[Dict[str, Any]]] = None,
        run_id: str = "",
    ) -> Dict[str, Any]:
        run_id = run_id or uuid.uuid4().hex
        candidates = self._prepare_candidates(available_sources)
        if not candidates:
            return {
                "selected": None,
                "confidence": 0.0,
                "reason": "no_candidates",
                "candidates": [],
                "analysis": {},
                "files_needed": {"count": 0, "names": []},
            }

        db_url = os.getenv("DATABASE_URL", "")
        source_agent = build_detective_agent(
            llm=self.llm, data_dir=str(self.data_dir), db_url=db_url
        )
        builder_agent = build_dataframe_builder_agent(
            llm=self.llm, data_dir=str(self.data_dir), db_url=db_url
        )
```

Then change the two invocations to use run-scoped threads and the new local agents:

```python
        source_detection_run = run_detective_agent(
            agent=source_agent,
            query=f"{query}\nplan={str(plan or {})}\n{source_hint_for_agent}",
            selected_source=selected_source or "",
            thread_id=f"detective-source-{run_id}",
        )
```

```python
        dataframe_builder_run = run_dataframe_builder_agent(
            agent=builder_agent,
            query=f"{query}\nplan={str(plan or {})}",
            chosen_source=source_for_step2,
            required_fields_for_next_step=required_fields,
            thread_id=f"detective-dataframe-{run_id}",
        )
```

Add `import uuid` at the top and delete the now-unused `_build_chains` method along with the `keyword_tool_agent` / `dataframe_builder_agent` attributes.

- [ ] **Step 5: Run the tests**

```bash
cd backend && python3 -m pytest tests/ -v
```

Expected: every test in `tests/test_workflow_isolation.py` passes, and Task 1's `tests/test_auth.py` still passes (import is now network-free even if it was not before).

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/services/agents/workflow.py app/services/agents/data_detective.py tests/test_workflow_isolation.py && git commit -m "fix(agents): scope agent memory per run

Both ReAct agents shared a MemorySaver under a fixed thread_id, so every
request in the process appended to the same two threads. Build the agents and
the graph per run and derive thread ids from a run id.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Forward `plotly_ready_spec` to the chartist

`backend/app/services/agents/chartist.py:19-21` instructs the model to "use plotly_ready_spec fields (x/y/color/group_by/aggregation/chart_hint) if available". The dataframe-builder agent does produce that object, but `data_detective.py:268-275` and `:294-301` build `dataframe_plan` without it, so the key never reaches the chartist. The prompt asks for something it is never given.

**Files:**
- Modify: `backend/app/services/agents/data_detective.py:268-275`, `:294-301`
- Test: `backend/tests/test_workflow_isolation.py`

**Interfaces:**
- Consumes: `step2` structured output from the dataframe builder (`DataFrameBuildDecision`, which already declares `plotly_ready_spec: Dict[str, Any]`).
- Produces: `dataframe_plan` dicts that additionally carry `"plotly_ready_spec": dict`.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_workflow_isolation.py
def test_dataframe_plan_carries_plotly_ready_spec(monkeypatch):
    from app.services.agents import data_detective as dd

    spec = {"x": "month", "y": "revenue", "color": None, "group_by": None,
            "aggregation": "sum", "chart_hint": "line"}

    monkeypatch.setattr(dd, "build_detective_agent", lambda **kwargs: object())
    monkeypatch.setattr(dd, "build_dataframe_builder_agent", lambda **kwargs: object())
    monkeypatch.setattr(
        dd, "run_detective_agent",
        lambda **kwargs: {"structured_output": {"chosen_source": "a.csv",
                                                "confidence": 0.9,
                                                "required_fields_for_next_step": ["month"]}},
    )
    monkeypatch.setattr(
        dd, "run_dataframe_builder_agent",
        lambda **kwargs: {"structured_output": {"confidence": 0.9,
                                                "selected_columns": ["month", "revenue"],
                                                "plotly_ready_spec": spec}},
    )

    detective = dd.DataDetective(data_dir="/tmp", llm=object())
    sources = [{"id": "a", "name": "a.csv", "type": "file", "path": "/tmp/a.csv",
                "columns": ["month", "revenue"]}]

    decision = detective.detect_source("revenue by month", {}, "", sources, run_id="r")

    assert decision["dataframe_plan"]["plotly_ready_spec"] == spec
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_workflow_isolation.py::test_dataframe_plan_carries_plotly_ready_spec -v
```

Expected: FAIL with `KeyError: 'plotly_ready_spec'`.

- [ ] **Step 3: Implement**

In `detect_source`, after `load_type = str(step2.get("load_type", ""))`, add:

```python
        plotly_ready_spec = dict(step2.get("plotly_ready_spec", {}) or {})
```

Then add `"plotly_ready_spec": plotly_ready_spec,` to the `dataframe_plan` dict in **both** return branches (the `agent2_dataframe_builder_selected` branch and the `agent2_dataframe_builder_ambiguous` branch).

- [ ] **Step 4: Run the test**

```bash
cd backend && python3 -m pytest tests/test_workflow_isolation.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/agents/data_detective.py tests/test_workflow_isolation.py && git commit -m "fix(agents): forward plotly_ready_spec from the dataframe builder to the chartist

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Run generated code in a subprocess

`backend/app/utils/executor.py` runs model-written code with `exec()` inside the API process, guarded only by a regex blocklist. Its own docstring says this is not real sandboxing. The blocklist is trivially bypassable (`importlib`, `builtins`, `pandas.read_csv` to a URL) and an infinite loop in generated code hangs a worker forever. Since the executor already knows the file path, the subprocess can load the dataframe itself, which is both safer and simpler than serializing a dataframe across the process boundary.

**Files:**
- Create: `backend/app/utils/code_runner.py`
- Modify: `backend/app/utils/executor.py`
- Modify: `backend/app/services/agents/workflow.py` (`execution_node`)
- Test: `backend/tests/test_executor.py`

**Interfaces:**
- Consumes: `data_context["filepath"]` from the detective's schema dict.
- Produces: `SafeExecutor.execute(code: str, data_path: str, timeout_seconds: int = 30) -> dict` with the same result keys as today (`success`, `figure`, `output`, `error`), so `execution_node` and the endpoint's response assembly need no reshaping beyond the new argument.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_executor.py
import json

import pytest

from app.utils.executor import SafeExecutor


@pytest.fixture()
def sales_csv(tmp_path):
    path = tmp_path / "sales.csv"
    path.write_text("Category,Value\nA,10\nB,20\n", encoding="utf-8")
    return str(path)


def test_executes_valid_plotly_code(sales_csv):
    code = (
        "import plotly.express as px\n"
        "fig = px.bar(df, x='Category', y='Value')\n"
        "print(fig.to_json())\n"
    )
    result = SafeExecutor().execute(code, sales_csv)
    assert result["success"] is True
    assert result["figure"]["data"][0]["type"] == "bar"


def test_reports_syntax_error_without_raising(sales_csv):
    result = SafeExecutor().execute("fig = (((", sales_csv)
    assert result["success"] is False
    assert "error" in result


def test_times_out_on_infinite_loop(sales_csv):
    result = SafeExecutor().execute("while True:\n    pass\n", sales_csv, timeout_seconds=3)
    assert result["success"] is False
    assert "timed out" in result["error"].lower()


def test_rejects_output_that_is_not_a_figure(sales_csv):
    result = SafeExecutor().execute("print('hello')\n", sales_csv)
    assert result["success"] is False


def test_blocks_outbound_network_access(sales_csv):
    code = (
        "import urllib.request\n"
        "urllib.request.urlopen('http://example.com', timeout=2)\n"
        "print('{}')\n"
    )
    result = SafeExecutor().execute(code, sales_csv, timeout_seconds=10)
    assert result["success"] is False
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_executor.py -v
```

Expected: FAIL — `execute()` currently takes a `DataFrame`, not a path.

- [ ] **Step 3: Write the runner script**

This file must not import anything from `app.*` — it runs under `python3 -I`, which ignores the current directory and user site-packages, so a planted module beside the data file cannot hijack an import.

```python
# backend/app/utils/code_runner.py
"""Standalone runner for model-generated Plotly code. Executed as a subprocess.

Reads a JSON job from stdin: {"code": str, "data_path": str}
Writes the code's stdout to this process's stdout. Never import app.* here.
"""
from __future__ import annotations

import json
import socket
import sys


def _block_network() -> None:
    def _deny(*args, **kwargs):
        raise OSError("network access is disabled in the chart execution sandbox")

    socket.socket = _deny  # type: ignore[assignment]
    socket.create_connection = _deny  # type: ignore[assignment]


def main() -> int:
    job = json.loads(sys.stdin.read())
    code = job["code"]
    data_path = job["data_path"]

    import pandas as pd

    if data_path.endswith(".csv"):
        df = pd.read_csv(data_path)
    elif data_path.endswith((".xlsx", ".xls")):
        df = pd.read_excel(data_path)
    else:
        print(f"unsupported data format: {data_path}", file=sys.stderr)
        return 2

    _block_network()

    import plotly.express as px
    import plotly.graph_objects as go

    namespace = {"df": df, "pd": pd, "px": px, "go": go, "json": json}
    exec(compile(code, "<generated>", "exec"), namespace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Rewrite the executor**

Replace the body of `backend/app/utils/executor.py`, keeping `_sanitize_code` exactly as it is (the chartist relies on the same normalization) and dropping `_is_safe_code` and the regex blocklist — process isolation replaces it:

```python
import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

RUNNER = Path(__file__).with_name("code_runner.py")


class SafeExecutor:
    """Runs generated Plotly code in an isolated subprocess with a wall-clock limit."""

    def _sanitize_code(self, code: str) -> str:
        # unchanged from the previous implementation
        if not code:
            return ""
        code = code.replace("“", '"').replace("”", '"')
        code = code.replace("’", "'").replace("‘", "'")
        fenced = re.findall(r"```(?:python)?\s*(.*?)```", code, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            code = fenced[0]
        lines = code.splitlines()
        start_idx = 0
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if re.match(
                r"^(import |from |df\[|fig\s*=|[A-Za-z_]\w*\s*=|if |for |while |try:|except |print\(|#)",
                stripped,
            ):
                start_idx = idx
                break
        return "\n".join(lines[start_idx:]).strip()

    def execute(
        self,
        code: str,
        data_path: str,
        timeout_seconds: int = 30,
    ) -> Dict[str, Any]:
        code = self._sanitize_code(code)
        if not code:
            return {"success": False, "error": "No executable code was produced"}

        job = json.dumps({"code": code, "data_path": str(data_path)})
        try:
            completed = subprocess.run(
                [sys.executable, "-I", str(RUNNER)],
                input=job,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(RUNNER.parent),
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Chart code timed out after {timeout_seconds}s",
            }

        if completed.returncode != 0:
            logger.warning("[executor] runner exited %s: %s", completed.returncode, completed.stderr[-500:])
            return {
                "success": False,
                "error": (completed.stderr or "chart code failed").strip()[-500:],
                "output": completed.stdout,
            }

        try:
            figure = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Output is not valid JSON",
                "output": completed.stdout,
            }
        return {"success": True, "figure": figure, "output": completed.stdout}
```

- [ ] **Step 5: Update the calling node**

In `backend/app/services/agents/workflow.py`, replace the whole dataframe-loading block in `execution_node` (the `try`/`except` around `pd.read_csv` / `pd.read_excel`) with a path lookup, since the subprocess now loads the data:

```python
def execution_node(state: AgentState):
    started_at = time.perf_counter()
    data_context = state["data_context"]
    filepath = data_context.get("filepath")
    if not filepath:
        return {"error": "No resolved data file for execution"}

    result = get_executor().execute(state["code"], filepath)
```

Keep the rest of `execution_node` unchanged. The `import pandas as pd` at the top of `workflow.py` is still used by nothing else — remove it if the linter flags it.

- [ ] **Step 6: Run the tests**

```bash
cd backend && python3 -m pytest tests/test_executor.py -v
```

Expected: 5 PASS. `test_blocks_outbound_network_access` depends on `urllib` going through `socket.socket`; if it fails because some transport bypasses the patch, change the assertion to document the real behavior and leave a comment — process isolation and the timeout are the load-bearing protections here, the network patch is defense in depth.

- [ ] **Step 7: Commit**

```bash
cd backend && git add app/utils/executor.py app/utils/code_runner.py app/services/agents/workflow.py tests/test_executor.py && git commit -m "fix(executor): run generated chart code in an isolated subprocess

Replaces in-process exec() behind a regex blocklist with a python -I
subprocess that has a wall-clock timeout and no socket access.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Authenticate and rewire `/dashboard/generate`

`backend/app/api/v1/endpoints/dashboard.py:155-156` is the only unauthenticated endpoint in the app, and it accepts a `data_source` path string. After this task it requires a Bearer token and accepts `data_source_ids`.

**Files:**
- Modify: `backend/app/api/v1/endpoints/dashboard.py:27-47`, `:155-234`
- Test: `backend/tests/test_generate_endpoint.py`

**Interfaces:**
- Consumes: `resolve_user_sources` / `SourceResolutionError` (Task 3), `run_agent_workflow(..., run_id=...)` (Task 4).
- Produces: request body `{"prompt": str, "data_source_ids": list[str] = [], "request_id": str | None}`; response unchanged (`dashboard_html`, `metadata`). `400` on bad ids, `401`/`403` without a token, `504` on timeout.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_generate_endpoint.py
import io

from app.api.v1.endpoints import dashboard as dashboard_module


def _upload_csv(client, auth_headers, name="sales.csv"):
    content = b"Category,Value\nA,10\nB,20\n"
    response = client.post(
        "/api/v1/data-sources/upload",
        headers=auth_headers,
        files={"file": (name, io.BytesIO(content), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_generate_requires_authentication(client):
    response = client.post("/api/v1/dashboard/generate", json={"prompt": "chart it"})
    assert response.status_code in (401, 403)


def test_generate_rejects_unknown_data_source_id(client, auth_headers):
    response = client.post(
        "/api/v1/dashboard/generate",
        headers=auth_headers,
        json={"prompt": "chart it", "data_source_ids": ["does-not-exist"]},
    )
    assert response.status_code == 400
    assert "not owned" in response.json()["detail"]


def test_generate_passes_resolved_sources_to_the_workflow(client, auth_headers, monkeypatch):
    source_id = _upload_csv(client, auth_headers)
    captured = {}

    def fake_workflow(query, selected_source="", available_sources=None, run_id=""):
        captured["query"] = query
        captured["selected_source"] = selected_source
        captured["available_sources"] = available_sources
        captured["run_id"] = run_id
        return {
            "error": "",
            "plan": {"visualization_type": "bar"},
            "data_context": {"filename": "sales.csv"},
            "execution_result": {"figure": {"data": [], "layout": {}}},
            "messages": [],
        }

    monkeypatch.setattr(dashboard_module, "run_agent_workflow", fake_workflow)

    response = client.post(
        "/api/v1/dashboard/generate",
        headers=auth_headers,
        json={"prompt": "bar chart of value by category", "data_source_ids": [source_id]},
    )

    assert response.status_code == 200, response.text
    assert "promptdash-chart" in response.json()["dashboard_html"]
    assert len(captured["available_sources"]) == 1
    assert captured["available_sources"][0]["name"] == "sales.csv"
    assert captured["selected_source"] == captured["available_sources"][0]["path"]
    assert captured["run_id"]


def test_generate_surfaces_workflow_errors_as_400(client, auth_headers, monkeypatch):
    source_id = _upload_csv(client, auth_headers, name="other.csv")
    monkeypatch.setattr(
        dashboard_module,
        "run_agent_workflow",
        lambda *args, **kwargs: {"error": "Could not resolve data source (no_candidates)."},
    )
    response = client.post(
        "/api/v1/dashboard/generate",
        headers=auth_headers,
        json={"prompt": "chart it", "data_source_ids": [source_id]},
    )
    assert response.status_code == 400
    assert "Could not resolve" in response.json()["detail"]
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_generate_endpoint.py -v
```

Expected: `test_generate_requires_authentication` FAILS (returns 200 or 500, not 401/403).

- [ ] **Step 3: Change the request model**

Replace `DashboardRequest` at `backend/app/api/v1/endpoints/dashboard.py:27-30`:

```python
class DashboardRequest(BaseModel):
    prompt: str = Field(min_length=1)
    data_source_ids: list[str] = Field(default_factory=list)
    request_id: Optional[str] = None
```

Add `Field` to the `pydantic` import and add these imports:

```python
import uuid

from app.services.source_resolver import SourceResolutionError, resolve_user_sources
```

- [ ] **Step 4: Rewrite the endpoint signature and source plumbing**

Replace `backend/app/api/v1/endpoints/dashboard.py:155-175` (through the `run_agent_workflow` call) with:

```python
@router.post("/generate", response_model=DashboardResponse)
async def generate_dashboard(
    request: DashboardRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a chart from the authenticated user's own data sources."""
    try:
        sources = resolve_user_sources(db, current_user, request.data_source_ids)
    except SourceResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    run_id = (request.request_id or "").strip() or uuid.uuid4().hex
    selected_source = sources[0]["path"] if len(sources) == 1 else ""

    try:
        started_at = time.perf_counter()
        logger.info(
            "[dashboard/generate] start run_id=%s user=%s sources=%s prompt=%s",
            run_id,
            current_user.id,
            len(sources),
            request.prompt[:150],
        )
        workflow_call = asyncio.to_thread(
            run_agent_workflow,
            request.prompt,
            selected_source,
            sources,
            run_id,
        )
```

Keep the rest of the handler as it is, and change the two `request.request_id or "-"` log arguments and the `"request_id": request.request_id` metadata entry to use `run_id`.

- [ ] **Step 5: Run the tests**

```bash
cd backend && python3 -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/api/v1/endpoints/dashboard.py tests/test_generate_endpoint.py && git commit -m "feat(api): authenticate /dashboard/generate and take data_source_ids

The only unauthenticated endpoint in the app accepted a raw filesystem path.
It now requires a Bearer token and resolves ids against the caller's own rows.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Forward auth and sources through the frontend proxy

`byd-web/app/api/dashboard/generate/route.ts:10-32` reads only `prompt` and `request_id` and sends no `Authorization` header, so it cannot talk to the endpoint Task 8 produced.

There is no JS test runner in this repo and adding one is out of scope, so this task and Task 10 are verified by `npm run lint`, `npm run build`, and an explicit manual check. That is a real gap; it is recorded here rather than papered over with tests that assert nothing.

**Files:**
- Modify: `byd-web/app/api/dashboard/generate/route.ts`

**Interfaces:**
- Consumes: the Task 8 request body.
- Produces: a proxy that forwards `Authorization` verbatim and passes `data_source_ids` through; returns `401` with a clear message when the header is absent.

- [ ] **Step 1: Widen the parsed body**

Replace line 10:

```ts
    const body = (await request.json()) as {
      prompt?: string;
      request_id?: string;
      data_source_ids?: string[];
    };
```

- [ ] **Step 2: Require and forward the token**

After the `if (!prompt)` guard, add:

```ts
    const authorization = request.headers.get("authorization");
    if (!authorization) {
      return NextResponse.json(
        { detail: "Not signed in. Sign in again and retry." },
        { status: 401 },
      );
    }

    const dataSourceIds = Array.isArray(body.data_source_ids) ? body.data_source_ids : [];
```

- [ ] **Step 3: Send them upstream**

Change the `fetch` call's `headers` and `body`:

```ts
        headers: { "Content-Type": "application/json", Authorization: authorization },
        body: JSON.stringify({
          prompt,
          request_id: requestId,
          data_source_ids: dataSourceIds,
        }),
```

- [ ] **Step 4: Verify**

```bash
cd byd-web && npm run lint
```

```bash
cd byd-web && npm run build
```

Expected: both succeed with no new errors.

- [ ] **Step 5: Commit**

```bash
cd byd-web && git add app/api/dashboard/generate/route.ts && git commit -m "fix(frontend): forward auth and data_source_ids through the generate proxy

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: Point the canvas at the real API

`byd-web/app/dashboard/new-canvas/page.tsx:61-62` loads sources from `localStorage` via `loadDataSources`, which **seeds three fabricated sources** on first read (`sales_q1_2024.csv`, `customer_churn.xlsx`, "Local PostgreSQL" — `byd-web/lib/data-sources.ts:15-43`). `handleUpload` at line 81 writes file *metadata* to `localStorage` and never uploads the file. `submitPrompt` at line 122 sends only `prompt` and `request_id`. The result is that the entire source-selection UI on the one page that generates charts is decorative.

**Files:**
- Modify: `byd-web/app/dashboard/new-canvas/page.tsx`
- Modify: `byd-web/lib/data-sources.ts`

**Interfaces:**
- Consumes: `authorizedFetch`, `BackendDataSource`, `mapBackendDataSource` from `byd-web/lib/backend.ts`; `getAccessToken` from `byd-web/lib/auth.ts`; the Task 9 proxy.
- Produces: a canvas whose sidebar lists real `/api/v1/data-sources` rows, whose upload posts to `/api/v1/data-sources/upload`, and whose prompt carries `data_source_ids`.

- [ ] **Step 1: Delete the fake store**

In `byd-web/lib/data-sources.ts`, delete the `defaultSources` array (lines 15-43), `dataSourcesKey`, `loadDataSources`, and `saveDataSources`. Keep the `DataSource` interface, `createId`, `selectedSourcesKey`, `loadSelectedSourceIds`, `saveSelectedSourceIds`, and `bytesToSize` — the selection list is a legitimate per-browser preference, unlike the source inventory.

- [ ] **Step 2: Load real sources on mount**

In `new-canvas/page.tsx`, change the imports to:

```tsx
import { AuthUser, getAccessToken, loadCurrentUser, logoutUser } from "@/lib/auth";
import { authorizedFetch, backendBaseUrl, BackendDataSource, mapBackendDataSource } from "@/lib/backend";
import {
  bytesToSize,
  createId,
  DataSource,
  loadSelectedSourceIds,
  saveSelectedSourceIds,
} from "@/lib/data-sources";
```

Add a `token` state alongside `user` (`const [token, setToken] = useState<string | null>(null);`) and an `error` state (`const [error, setError] = useState<string | null>(null);`), then replace the mount effect:

```tsx
  useEffect(() => {
    const currentUser = loadCurrentUser();
    const currentToken = getAccessToken();
    if (!currentUser || !currentToken) {
      router.replace("/login");
      return;
    }
    setUser(currentUser);
    setToken(currentToken);
    setSelectedSourceIds(loadSelectedSourceIds(currentUser.id));
    setIsHydrated(true);

    authorizedFetch<BackendDataSource[]>("/api/v1/data-sources", currentToken)
      .then((items) => setAllSources(items.map(mapBackendDataSource)))
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load data sources"),
      );
  }, [router]);
```

- [ ] **Step 3: Make the upload real**

Replace `handleUpload` entirely:

```tsx
  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    if (!token) return;
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;

    try {
      for (const file of files) {
        const formData = new FormData();
        formData.append("file", file);
        const response = await fetch(`${backendBaseUrl()}/api/v1/data-sources/upload`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        });
        if (!response.ok) {
          const detail = (await response.json().catch(() => null)) as { detail?: string } | null;
          throw new Error(detail?.detail ?? `Upload failed (${response.status})`);
        }
      }
      const items = await authorizedFetch<BackendDataSource[]>("/api/v1/data-sources", token);
      const mapped = items.map(mapBackendDataSource);
      setAllSources(mapped);
      const uploadedNames = new Set(files.map((file) => file.name));
      const newlySelected = mapped
        .filter((source) => uploadedNames.has(source.name))
        .map((source) => source.id);
      updateSelected([...new Set([...newlySelected, ...selectedSourceIds])]);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload file");
    } finally {
      event.target.value = "";
    }
  }
```

`bytesToSize` and `createId` stay imported — `createId` is still used for `requestId` and `chartId`, and `bytesToSize` is no longer needed here, so drop it from the import list if the linter flags it.

- [ ] **Step 4: Send the selected ids with the prompt**

In `submitPrompt`, add a guard after the existing `if (!prompt) return;`:

```tsx
    if (!selectedSourceIds.length) {
      setError("Select at least one data source before generating a chart.");
      return;
    }
```

and change the request body at line 125:

```tsx
        body: JSON.stringify({
          prompt,
          request_id: requestId,
          data_source_ids: selectedSourceIds,
        }),
```

Add the `Authorization` header to that same `fetch` so the proxy can forward it:

```tsx
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
```

- [ ] **Step 5: Render the error banner**

Immediately inside the `<main>` element, before the `<aside>`, add:

```tsx
        {error ? (
          <p className="col-span-full rounded-xl border border-[#ff9faa] bg-[#ffd8dd] p-3 text-sm text-[#a12d39]">
            {error}
          </p>
        ) : null}
```

- [ ] **Step 6: Verify**

```bash
cd byd-web && npm run lint && npm run build
```

Expected: both succeed. Fix any unused-import errors the deletions in Step 1 produced — `byd-web/app/dashboard/new/page.tsx` imports `saveSelectedSourceIds` only, so it is unaffected, but confirm with the build.

- [ ] **Step 7: Manual end-to-end check**

This is the only check that proves the whole chain. Run it before committing.

```bash
cd backend && docker compose up -d
```

```bash
cd byd-web && npm run dev
```

Then: sign in at `http://localhost:3000/login`, go to `/settings/data-sources` and upload `backend/data/sales.csv`, open `/dashboard/new`, select it, press **Open Canvas**, press **+**, and submit `bar chart of value by category`. Confirm the sidebar shows `sales.csv` and *not* `sales_q1_2024.csv` or `customer_churn.xlsx`, and that a chart renders. Generation needs Ollama on `:11434` with the configured model pulled; if Ollama is absent the request fails at the planner, which still proves auth, source resolution, and plumbing — note in the commit which half you verified.

- [ ] **Step 8: Commit**

```bash
cd byd-web && git add app/dashboard/new-canvas/page.tsx lib/data-sources.ts && git commit -m "fix(frontend): read real data sources in the canvas and upload for real

The canvas kept a second, fabricated source list in localStorage, its upload
button never sent the file to the backend, and the prompt carried no source
selection. All three are now wired to the API.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: Remove dead code and correct the docs

`AGENTS.md` currently documents the forced-source hack as present behavior, which will mislead the next reader now that Task 4 removed it.

**Files:**
- Delete: `backend/app/services/tool_registry.py`
- Delete: `langchain-archeticture/` (the whole directory)
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. This is cleanup.

- [ ] **Step 1: Prove the deletions are safe**

```bash
cd /Users/atukka/Desktop/BYD && grep -rn "tool_registry\|build_tool_registry\|langchain_archeticture\|langchain-archeticture" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.md" . | grep -v __pycache__
```

Expected: hits only in `backend/app/services/tool_registry.py` itself, in `langchain-archeticture/`, and in `AGENTS.md` / this plan. If anything else references them, stop and reassess.

- [ ] **Step 2: Delete**

```bash
cd /Users/atukka/Desktop/BYD && git rm backend/app/services/tool_registry.py && git rm -r langchain-archeticture
```

- [ ] **Step 3: Update `AGENTS.md`**

In the "Backend gotchas" section, delete the three bullet lines describing the forced `selected source` / `available sources` behavior and the "This will break normal multi-source behavior" sentence. Replace them with:

```markdown
- `POST /api/v1/dashboard/generate` requires a Bearer token and takes `{"prompt", "data_source_ids": [...], "request_id"}`. Sources are resolved from the caller's own `data_sources` rows by `backend/app/services/source_resolver.py` — callers never send a filesystem path.
- Generated chart code runs in a `python -I` subprocess (`backend/app/utils/code_runner.py`) with a 30s wall-clock limit and no socket access. It must end with `print(fig.to_json())`; `fig.show()` output is rejected by the chartist sanitizer.
- `SECRET_KEY` and `ENCRYPTION_KEY` have no defaults. The app refuses to start without them.
```

In the "Verification shortcuts" section, replace the "no established Python test suite config" bullet with:

```markdown
- Backend tests: `cd backend && python3 -m pytest`. They run against a temp SQLite DB with no Postgres, Ollama, or network access. `backend/test_agent.py` remains a manual workflow script, not part of the suite.
- Frontend has no test runner. Verify with `cd byd-web && npm run lint && npm run build` plus a manual pass through login → upload → canvas.
```

- [ ] **Step 4: Run the full suite one more time**

```bash
cd backend && python3 -m pytest -v
```

```bash
cd byd-web && npm run lint && npm run build
```

Expected: everything green.

- [ ] **Step 5: Commit**

```bash
cd /Users/atukka/Desktop/BYD && git add AGENTS.md && git commit -m "chore: drop dead tool_registry and broken langchain-archeticture, refresh AGENTS.md

langchain-archeticture/detective_graph.py imported a .registry module that
does not exist, so it could never be imported. Superseded by
backend/app/services/tools/.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage.** Every defect named in the request maps to a task: forced source → Task 4; canvas on `localStorage` → Task 10; unauthenticated `/generate` → Task 8; fixed-`thread_id` `MemorySaver` → Task 5; committed secrets → Task 2; dropped `plotly_ready_spec` → Task 6; broken `langchain-archeticture` import → Task 11. Two defects from the review that the request did not name are included because they block or endanger the above: the unsafe in-process executor (Task 7) and the absent test harness (Task 1). Two known gaps are listed as out of scope with reasons: no dashboard `DELETE`, and charts are still not persisted.

**Placeholder scan.** No "TBD", no "add error handling", no "similar to Task N". Every code step carries the literal code. Task 1 Step 4 and Task 7 Step 6 describe how to react to a version-dependent outcome rather than asserting one — that is a deliberate branch with both paths spelled out, not a placeholder.

**Type consistency.** `resolve_user_sources` returns `list[dict]` with keys `id`/`name`/`type`/`path` in Task 3, and Tasks 4 and 8 consume exactly those keys. `run_agent_workflow(query, selected_source, available_sources, run_id)` is defined in Task 4 and called positionally in that order from Task 8. `SafeExecutor.execute(code, data_path, timeout_seconds)` is defined in Task 7 and called as `execute(state["code"], filepath)` in the same task. `detect_source(..., run_id=...)` is introduced in Task 5 and relied on by Task 6's test. `build_workflow` / `get_llms` / `get_executor` / `resolve_data_dir` / `CONTAINER_UPLOAD_DIR` are all defined in Tasks 4-5 before any task references them.

One ordering note for the executor: Task 1's harness must be able to import `app.main`, which transitively imports `workflow.py`. If that import needs a live Ollama, Task 1 Step 4 routes you to Task 5 first and back. Running Task 5 before Task 1 is acceptable; no other reordering is.
