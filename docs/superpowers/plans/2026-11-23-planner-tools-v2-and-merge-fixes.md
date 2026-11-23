# Planner Tools v2 and Merge Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the final review's merge blockers, catch lines that run back and forth (in the plan and in the drawn figure), log every chart plan, and give the planner two new data tools it may call itself, then measure whether that mode should become the default.

**Architecture:** Part A fixes three review findings:
- a foreign key into another schema is no longer joined;
- a kind picked with "/" is ranked first among the planner's tries, told to the planner up front, and reported to the user when it is still missing;
- a "/" kind request on a wide table gets a live check, and a fix only if the check fails.

Part B adds one value-based function, `data_tools.repeated_x`, reached through `data_tools.chart_shape`, which both the plan check and the new `preview_chart` tool call. It also adds a drawing check in `workflow.run_on_frame`, the loop every path shares, that sends a line whose x repeats back to the model as a repair turn.

Part C adds `row_grain` and `preview_chart`, a third `PLANNER_TOOLS` value (`planner`) in which the planner holds the tools during its own call, the measurement harness changes, and a speed script.

The trained system prompts never change: kinds and tool instructions are appended user-message sections, pinned by a sha256 test.

**Tech Stack:** Python 3.13 host venv (`backend/.venv`; the api container runs 3.11), FastAPI, SQLAlchemy 2.1, pandas 3.1, plotly 7.1, LangChain (`bind_tools`, `ToolMessage`), mlx_lm server 0.32.2 (lora-v2, 4-bit), Next.js 16 / React 19, Node 24 (`node --test`), pytest.

## Global Constraints

Every task's requirements include this section.

- Never hardcode charts: every chart is the model's own code; a check finds a problem and sends it back to the model in plain words, it never draws, edits a plan or picks a column itself.
- No name rules: column roles and checks come from values, never from column names.
- `ANALYST_SYSTEM_PROMPT`, `PLANNER_SYSTEM_PROMPT`, `EXPLORER_SYSTEM_PROMPT` and `SPEC_RULES` stay byte-identical; new context goes in appended user-message sections.
- Tool results stay bounded:
  - lists cap at 20 items with totals;
  - each result is at most 1,200 characters;
  - cuts are marked;
  - `preview_chart` returns one line per plan.
- The planner makes at most 3 tool calls per dashboard.
- Temperature stays 0.0, and the analyst, planner and explorer run with thinking off.
- Identifiers are never interpolated into SQL.
- Test baselines at `dacbe60` (counts after each task are in the table below):
  - backend: `cd backend && .venv/bin/python -m pytest -q tests` runs 131 tests. The only allowed failures are the 3 that predate this plan in `tests/test_chartist_contract.py` (`test_rejects_write_html`, `test_rejects_to_csv`, `test_method_named_open_is_not_a_file_read`). The suite prints no final count line, so count the dots and `F`s.
  - finetune: `cd chartist-finetune && ../backend/.venv/bin/python -m pytest -q tests` gives 81 passed.
  - frontend: `cd byd-web && npm test && npx tsc --noEmit -p . && npx eslint <files>` gives 4 tests passing, and no output from tsc or eslint.
  - `chartist-finetune/contract.py` executes `chartist_contract.py`, `planning_contract.py` and `profiler.py` by path. A task that touches one of them also runs the finetune suite. Those three files may import only the standard library and pandas, never `app.*`.
- Commit after every task. Each commit message ends with a Co-Authored-By trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Measure only on the frozen planning set (`chartist-finetune/data/v2/planning_testset.jsonl`); never train on it.
- Seam check, for every task (from the final review): what does this add to a prompt, what happens on the last retry, and does it hold for joined and wide tables?
- Apply the tasks in order. `planning.py`, `dashboard_flow.py`, `data_tools.py`, `blocks.py` and `AGENTS.md` are each edited by several tasks, so every edit is anchored by quoted code as it stands after the earlier tasks, never by line number.
- Steps marked **(controller)** need the running stack (`make up`), the model server (`make serve-model`) or a browser. The controller runs them; an implementer without the stack stops there and reports.

## File Structure

- `backend/app/services/db_sources.py`: `links_on` skips keys into another schema (Task 1).
- `backend/app/services/agents/chart_kinds.py`: `include_kinds()`, the one wording for picked kinds (Task 2).
- `backend/app/services/agents/planning_contract.py`:
  - `with_context(..., notes=())` (Task 2);
  - `PLANNER_TOOLS_NOTE` (Task 9).
- `backend/app/services/agents/planning.py`:
  - `run_checked(rank=..., ask=...)`, `by_size`, and the planner ranked by kinds present (Task 2);
  - the planner's tool loop, `_tool_asker` (Task 9).
- `backend/app/services/agents/dashboard_flow.py`:
  - `missing_kinds` in the plan event (Task 2);
  - one log line per placed plan (Task 5);
  - `planner_tools=` and status lines for the planner's tool calls (Task 9).
- `backend/app/api/v1/endpoints/blocks.py`:
  - passes `missing_kinds` on (Task 2);
  - the `PLANNER_TOOLS` mode, and a 500 for an unknown value (Task 9).
- `backend/app/services/agents/kind_request.py`: `direction_columns()`, and the conditional overlap order (Task 4).
- `backend/app/services/agents/architect.py`: `by_overlap()`, conditional (Task 4).
- `backend/scripts/make_relational_demo.py`: adds the 14-column `visits` table (Task 4).
- `backend/scripts/check_kind_columns.py`: the live check of a "/" request on a wide table (Task 4).
- `backend/app/services/agents/data_tools.py`:
  - `repeated_x`, `chart_shape`, `_plan_head`, `UNITS`, and `preview`'s `series`/`low`/`high` (Task 5);
  - `row_grain`, `inspect_column` repeats, `tool_specs(names=)` and `ToolBox(tools=)` (Task 7);
  - `preview_chart`, `ToolBox(kinds=)`, `call(compact=)` and `PLANNER_TOOL_NAMES` (Task 8).
- `backend/app/services/agents/chartist_contract.py`: `REPEATED_X_FIX`, `figure_problems` (Task 6).
- `backend/app/services/agents/workflow.py`: the drawing check and `repair_reasons` in `run_on_frame` (Task 6).
- `backend/app/services/agents/spec_runner.py`: passes `repair_reasons` on (Task 6).
- `backend/app/services/agents/discovery.py`: `run_tools`, the shared tool loop (Task 9).
- `backend/app/core/config.py`: the `PLANNER_TOOLS` comment (Task 9), and the default only if Task 10 decides so.
- `docker-compose.yml`: `PLANNER_TOOLS: ${PLANNER_TOOLS:-on}` (Task 9).
- `byd-web/lib/kind-notice.ts`: import-free notice text (Task 3).
- `byd-web/lib/blocks.ts`, `byd-web/components/report-canvas.tsx`: the notice line (Task 3).
- `byd-web/DESIGN.md`: the notice line (Task 3).
- `chartist-finetune/measure_planning_tools.py`: `--tools planner`, `--draw N`, `draw_first` and `compare_planner` (Task 10).
- `backend/scripts/time_planner_tools.py`: tool timings on three tables (Task 10).
- `backend/scripts/probe_planner_tools.py`: the two server behaviours the planner's tool loop relies on (Task 9).
- Tests:
  - create `backend/tests/test_dashboard_endpoint.py`, `backend/tests/test_drawing_check.py`, `backend/tests/test_planner_tools.py` and `byd-web/tests/kind-notice.test.mts`;
  - extend `test_db_links.py`, `test_planning_steps.py`, `test_planning_contract.py`, `test_dashboard_flow.py`, `test_kind_request.py`, `test_data_tools.py` and `chartist-finetune/tests/test_measure_planning_tools.py`.
- `AGENTS.md`: each task adds its own bullets, at a named anchor.

## Test counts after each task

The sums below were measured by applying every task in a scratch copy of the repo.

| After | Backend tests (all pass except the 3 known) | Finetune | Frontend `npm test` |
|---|---|---|---|
| `dacbe60` | 131 | 81 | 4 |
| Task 1 | 132 | 81 | 4 |
| Task 2 | 139 | 81 | 4 |
| Task 3 | 139 | 81 | 8 |
| Task 4 | 141 if the fix is applied, else 139 | 81 | 8 |
| Task 5 | +6 (147 or 145) | 81 | 8 |
| Task 6 | +11 (158 or 156) | 81 | 8 |
| Task 7 | +6 (164 or 162) | 81 | 8 |
| Task 8 | +6 (170 or 168) | 81 | 8 |
| Task 9 | +13 (183 or 181) | 81 | 8 |
| Task 10 | unchanged | 89 | 8 |

---

### Task 1: `links_on` skips a key into another schema

The final review's must-fix:
- SQLAlchemy sets `referred_schema` when a key points outside the connection's schema (Postgres) or database (MySQL).
- `links_on` drops that field, and `load_joined_on` reflects the parent by its bare name.
- So a key from `public.orders` to `audit.customers` joins `public.customers` whenever that table exists. The result is plausible, wrong sums, and no error.

The module is single-schema by design, so such a key is skipped.

**Files:**
- Modify: `backend/app/services/db_sources.py` (`links_on`)
- Test: `backend/tests/test_db_links.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: `links_on(connection, tables) -> list[Link]` (existing). It calls the module-level `inspect` imported from `sqlalchemy`, which the test replaces.
- Produces: the same signature. A key whose `referred_schema` is set and differs from `inspector.default_schema_name` is never a `Link`.

- [ ] **Step 1: Write the failing test** (append to `backend/tests/test_db_links.py`)

```python


class KeysOnly:
    """An inspector that knows the default schema and some declared keys, nothing else."""

    default_schema_name = "public"

    def __init__(self, keys):
        self.keys = keys

    def get_foreign_keys(self, table):
        return self.keys.get(table, [])


def test_a_key_into_another_schema_is_left_out(monkeypatch):
    # public.orders -> audit.customers: joining by the bare name would read public.customers instead.
    def key(parent, schema, column):
        return {"referred_table": parent, "referred_schema": schema,
                "constrained_columns": [column], "referred_columns": ["id"]}
    keys = {"orders": [key("customers", "audit", "customer_id"), key("products", "public", "product_id"),
                       key("regions", None, "region_id")]}
    monkeypatch.setattr(db_sources, "inspect", lambda connection: KeysOnly(keys))
    links = links_on(object(), ["orders", "customers", "products", "regions"])
    assert [link.parent for link in links] == ["products", "regions"]
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_db_links.py -k another_schema`
Expected: 1 failed, with `AssertionError: assert ['customers',...s', 'regions'] == ['products', 'regions']`.

- [ ] **Step 3: Implement**

In `backend/app/services/db_sources.py`, replace the head of `links_on`, from `def links_on` to the `if (parent in known` condition:

```python
def links_on(connection: Any, tables: List[str]) -> List[Link]:
    """Declared foreign keys among `tables`, child to parent. Only declared ones:
    a join guessed from column names would be a name rule, and often wrong."""
    inspector = inspect(connection)
    known = set(tables)
    found: List[Link] = []
    for table in tables:
        for fk in inspector.get_foreign_keys(table):
            parent = fk.get("referred_table")
            child_columns = fk.get("constrained_columns") or []
            parent_columns = fk.get("referred_columns") or []
            if (parent in known and parent != table and child_columns
                    and len(child_columns) == len(parent_columns)):
```

with:

```python
def links_on(connection: Any, tables: List[str]) -> List[Link]:
    """Declared foreign keys among `tables`, child to parent. Only declared ones:
    a join guessed from column names would be a name rule, and often wrong.

    A key into another schema (Postgres) or another database (MySQL) is left
    out. The parent is reflected by its bare name, so a same-named table in this
    schema would be joined instead: plausible, wrong numbers and no error."""
    inspector = inspect(connection)
    home = inspector.default_schema_name
    known = set(tables)
    found: List[Link] = []
    for table in tables:
        for fk in inspector.get_foreign_keys(table):
            parent = fk.get("referred_table")
            elsewhere = fk.get("referred_schema")
            child_columns = fk.get("constrained_columns") or []
            parent_columns = fk.get("referred_columns") or []
            if elsewhere and elsewhere != home:
                continue
            if (parent in known and parent != table and child_columns
                    and len(child_columns) == len(parent_columns)):
```

The two lines after the condition (`found.append(...)`, and the `pairs`/`return` lines) stay as they are.

SQLite reports `referred_schema` as `None` for a key within the same database, and its default schema is `main`. The existing real-SQLite tests in this file therefore still find both keys.

- [ ] **Step 4: Run the file, then the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_db_links.py`
Expected: `12 passed`.

Run: `cd backend && .venv/bin/python -m pytest -q tests`
Expected: 132 tests; the only failures are the 3 known ones in `test_chartist_contract.py`.

- [ ] **Step 5: Record it in AGENTS.md**

Insert this bullet directly after the line that starts with `- Declared foreign keys become joined tables`:

```markdown
- A declared key into another schema (Postgres) or another database (MySQL) is not joined: `db_sources.links_on` skips a `referred_schema` other than the connection's default. The parent is reflected by its bare name, so a same-named table here would be joined instead, with wrong numbers and no error.
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/db_sources.py backend/tests/test_db_links.py AGENTS.md
git commit -m "fix(db): never join a foreign key that points into another schema

links_on dropped referred_schema and load_joined_on reflects the parent by
its bare name, so public.orders -> audit.customers joined public.customers
whenever it existed: plausible, wrong sums, no error. Such a key is now
skipped; the module is single-schema by design.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: A picked kind is ranked first, told to the planner up front, and reported when missing

The final review's Important 1. Three faults combine to drop a kind picked with "/" for a dashboard without a word:
- **Best attempt.** `run_checked` keeps the try with the most usable charts, so 7 charts without the pie beat 6 with it.
- **Planner told late.** The dashboard planner hears of the pick only in a retry message.
- **Miss not reported.** A kind still missing at the end reaches only the api log.

This task fixes the backend half of each. Task 3 shows the miss on the canvas.

**Files:**
- Modify: `backend/app/services/agents/planning_contract.py` (`with_context`)
- Modify: `backend/app/services/agents/chart_kinds.py` (add `include_kinds`)
- Modify: `backend/app/services/agents/planning.py` (`by_size`, `Rank`, `run_checked`, `plan_charts_steps`)
- Modify: `backend/app/services/agents/dashboard_flow.py` (analyst request wording, `missing_kinds`)
- Modify: `backend/app/api/v1/endpoints/blocks.py` (`_ai_dashboard`'s plan branch)
- Test: `backend/tests/test_planning_steps.py`, `backend/tests/test_planning_contract.py`, `backend/tests/test_dashboard_flow.py`, `backend/tests/test_kind_request.py`; create `backend/tests/test_dashboard_endpoint.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes:
  - `run_checked(llm, system, user, check, tables, label, max_attempts)`;
  - `plan_charts_steps(..., required_kinds=())`;
  - `check_specs(payload, tables, validate, required_kinds)`;
  - `KIND_INFO` (`chart_kinds.py`);
  - `build_dashboard(..., required_kinds=())`.

  All exist already.
- Produces (later tasks rely on these exact names):
  - `planning_contract.with_context(text, facts="", memory="", links="", notes: tuple[str, ...] = ()) -> str`. Notes come last, and empty ones are dropped.
  - `chart_kinds.include_kinds(kinds) -> str`, for example `"Include these chart kinds: Pie chart, KPI card."`. It returns `""` for no kinds.
  - `planning.Rank = Callable[[list[dict], list[str]], tuple]` and `planning.by_size(items, errors) -> tuple`.
  - `run_checked(..., rank: Rank = by_size)`. The attempt with the largest `rank` key is kept.
  - The `plan` event's data gains `"missing_kinds": list[str]` (kind ids). The SSE `plan` event carries the same key.
  - `backend/tests/test_dashboard_endpoint.py` holds the helpers `_fake_build(seen)`, `_wire(monkeypatch, seen)`, `_start(payload)`, `_events(response)`, `NoDb` and `SOURCE`. Task 9 adds tests that use them.

The kinds section is appended to every planner call that has `required_kinds`. The single-chart "/" path (`kind_request.run_kind_request`) is therefore told up front too. That is intended, and a test asserts it.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_planning_steps.py`:

```python


SAAS = pd.DataFrame({"cntry_cd": ["DE", "US", "BR", "FR"] * 50, "plan_tier": ["a", "b"] * 100,
                     "mrr": [i % 37 * 1.5 for i in range(200)]})
ONE_DIRECTION = [{"question": "q", "why": "w", "table": "saas", "columns": ["cntry_cd", "mrr"]}]


def _chart(kind, x="cntry_cd", y="mrr", title="t"):
    return {"title": title, "question": "q", "chart": kind, "table": "saas", "x": "" if kind == "kpi" else x,
            "y": y, "group": "", "agg": "sum", "grain": "", "sort": "", "top_n": 0}


def test_a_try_with_the_picked_kind_beats_a_bigger_try_without_it():
    # The final review's reproduction: two bars without the pie used to be kept over a
    # valid pie next to one broken chart, so a /pie brief could end with no pie.
    two_bars = json.dumps({"charts": [_chart("bar", title="a"), _chart("bar", x="plan_tier", title="b")]})
    pie_and_broken = json.dumps({"charts": [_chart("pie", title="p"), _chart("bar", y="no_such_column", title="x")]})
    step = plan_charts(Scripted(two_bars, pie_and_broken, pie_and_broken), ONE_DIRECTION,
                       [profile_table("saas", SAAS)], required_kinds=("pie",))
    assert step.attempts == 3 and [s["chart"] for s in step.items] == ["pie"]
    assert not any("asked for a pie" in e for e in step.errors)


def test_the_planner_is_told_the_picked_kinds_up_front():
    llm = Scripted(json.dumps({"charts": [_chart("pie", title="p"), _chart("kpi", title="k")]}))
    step = plan_charts(llm, ONE_DIRECTION, [profile_table("saas", SAAS)], required_kinds=("pie", "kpi"))
    assert step.attempts == 1 and step.errors == []
    assert llm.calls[0][1].content.endswith("\n\nInclude these chart kinds: Pie chart, KPI card.")
```

Append to `backend/tests/test_planning_contract.py`. The hashes were taken at `dacbe60`. This test passes before and after the change: it guards the constraint and is not a red test.

```python


import hashlib

from app.services.agents.planning_contract import (
    ANALYST_SYSTEM_PROMPT,
    EXPLORER_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    SPEC_RULES,
    with_context,
)

# sha256 of the prompts lora-v2 was trained on (and the explorer's), taken at dacbe60.
TRAINED = {
    "ANALYST_SYSTEM_PROMPT": "467c296ad922e5c1223427489111d41e272fafd29fb0430cc5d2ddb4ab305f96",
    "PLANNER_SYSTEM_PROMPT": "b0e3819ba2824d672c27feb80885b71055de2feea01236e2a92ce6c73cc980b3",
    "EXPLORER_SYSTEM_PROMPT": "f1c8f808f0c16544e8372d2dd1a7527dd51f56cf5ca7d421f3beb185bf535552",
    "SPEC_RULES": "bcb5e7882a0b6e0de19eafd2f20756fefa5c3ba81970fbba6309e8c29b941c9f",
}


def test_the_trained_prompts_are_byte_identical():
    # New context goes in appended user-message sections, never into these.
    texts = {"ANALYST_SYSTEM_PROMPT": ANALYST_SYSTEM_PROMPT, "PLANNER_SYSTEM_PROMPT": PLANNER_SYSTEM_PROMPT,
             "EXPLORER_SYSTEM_PROMPT": EXPLORER_SYSTEM_PROMPT, "SPEC_RULES": SPEC_RULES}
    assert {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in texts.items()} == TRAINED


def test_notes_come_last_and_empty_ones_are_left_out():
    text = with_context("T", facts="- f", links="L", notes=("", "N"))
    assert text == "T\n\nL\n\nFacts checked on the full data:\n- f\n\nN"
```

Append to `backend/tests/test_dashboard_flow.py`. `Recorder`, `Scripted`, `Fixed`, `_source`, `DIRECTIONS` and `CHARTS` are already defined in that file.

```python


def test_a_kind_still_missing_after_every_try_is_named_in_the_plan(tmp_path):
    planner = Recorder(CHARTS, CHARTS, CHARTS)  # three tries, never a pie
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("churn", [_source(tmp_path)], str(tmp_path), Scripted(DIRECTIONS), planner,
                                  chartist, required_kinds=("pie",)))
    plan = next(e for e in events if e.kind == "plan").data
    assert plan["missing_kinds"] == ["pie"] and plan["attempts"]["planner"] == 3
    assert planner.seen[0][-1].content.endswith("Include these chart kinds: Pie chart.")


def test_a_plan_with_every_picked_kind_misses_none(tmp_path):
    planner = Recorder(CHARTS.replace('"chart": "bar"', '"chart": "pie"'))
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("churn", [_source(tmp_path)], str(tmp_path), Scripted(DIRECTIONS), planner,
                                  chartist, required_kinds=("pie",)))
    assert next(e for e in events if e.kind == "plan").data["missing_kinds"] == []
```

In `backend/tests/test_kind_request.py`, inside `test_the_picked_kind_is_planned_and_drawn_by_the_model`, replace the line

```python
    assert "asked for a treemap" in planner.seen[1][-1].content
```

with

```python
    assert "asked for a treemap" in planner.seen[1][-1].content
    # Told up front too, in the dashboard's words, so a retry is the exception.
    assert planner.seen[0][-1].content.endswith("Include these chart kinds: Treemap.")
```

Create `backend/tests/test_dashboard_endpoint.py`:

```python
"""The dashboard endpoint: the kinds picked with "/" reach the build, and a kind
the plan still lacks reaches the client in the plan event."""
import asyncio
import json
from types import SimpleNamespace

from app.api.v1.endpoints import blocks
from app.api.v1.endpoints.blocks import DashboardBriefRequest
from app.services.agents.dashboard_flow import Event

SOURCE = {"id": "s1", "type": "file", "name": "saas.csv", "path": "saas.csv"}
PLACED = SimpleNamespace(spec={"title": "Churn by country", "question": "q", "chart": "bar"}, x=0, y=3, w=6, h=9)


class NoDb:
    """Enough of a session for the intro block: nothing is stored."""

    def add(self, row):
        pass

    def commit(self):
        pass

    def refresh(self, row):
        row.id = "b1"

    def rollback(self):
        pass


def _fake_build(seen):
    """Stands in for dashboard_flow.build_dashboard: records what it was given, at call time."""
    def build_dashboard(*args, **kwargs):
        seen.update(kwargs)
        return iter([Event("plan", {"intro": {"text": "<p>About</p>", "x": 0, "y": 0, "w": 12, "h": 3},
                                    "placed": [PLACED], "tables": [SimpleNamespace(label="saas.csv")],
                                    "attempts": {"analyst": 1, "planner": 3}, "dropped": [], "facts": [],
                                    "missing_kinds": ["pie"]})])
    return build_dashboard


def _wire(monkeypatch, seen):
    """Everything around the build replaced: no database, no model, no files."""
    monkeypatch.setattr(blocks, "build_dashboard", _fake_build(seen))
    monkeypatch.setattr(blocks, "_owned_report", lambda db, dashboard_id, user: SimpleNamespace(id=dashboard_id))
    monkeypatch.setattr(blocks, "_user_sources", lambda db, report: [SOURCE])
    monkeypatch.setattr(blocks, "_report_memory", lambda db, report_id: "")
    monkeypatch.setattr(blocks, "_record_request", lambda *args: None)
    monkeypatch.setattr(blocks, "_next_row", lambda db, report_id: 0)
    monkeypatch.setattr(blocks, "get_llm", lambda role: role)
    monkeypatch.setattr(blocks, "_agents", lambda: (None, None, "chartist", None))
    monkeypatch.setattr(blocks.settings, "DASHBOARD_PLANNER", "ai")


def _start(payload):
    async def run():
        return await blocks.generate_whole_dashboard("r1", payload, current_user=SimpleNamespace(id="u1"), db=NoDb())
    return asyncio.run(run())


def _events(response):
    async def drain():
        return [chunk async for chunk in response.body_iterator]
    out = []
    for chunk in asyncio.run(drain()):
        fields = dict(line.split(": ", 1) for line in chunk.strip().splitlines())
        out.append((fields["event"], json.loads(fields["data"])))
    return out


def test_picked_kinds_reach_the_build_and_a_missing_one_reaches_the_client(monkeypatch):
    seen = {}
    _wire(monkeypatch, seen)
    events = _events(_start(DashboardBriefRequest(brief="churn", chart_kinds=["pie"])))
    assert seen["required_kinds"] == ("pie",)
    assert [name for name, _ in events] == ["plan", "block", "done"]
    assert events[0][1]["missing_kinds"] == ["pie"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_planning_steps.py tests/test_planning_contract.py tests/test_dashboard_flow.py tests/test_kind_request.py tests/test_dashboard_endpoint.py`
Expected: 7 failed. The hash test passes.
- The two planning-steps tests fail: the kept plan is `['bar', 'bar']`, and the first message lacks the kinds line.
- `test_notes_come_last...` fails with `TypeError: with_context() got an unexpected keyword argument 'notes'`.
- The two dashboard-flow tests and the endpoint test fail with `KeyError: 'missing_kinds'`.
- The kind-request test fails, because the first message does not end with the kinds line.

- [ ] **Step 3: Implement**

In `backend/app/services/agents/planning_contract.py`, replace `with_context`:

```python
def with_context(text: str, facts: str = "", memory: str = "", links: str = "") -> str:
    """A planning user message, with optional sections after the trained part.
    Links describe tables, so they come straight after them."""
    parts = [text]
    if links:
        parts.append(links)
    if facts:
        parts.append(f"{FACTS_HEADER}\n{facts}")
    if memory:
        parts.append(memory)
    return "\n\n".join(parts)
```

with:

```python
def with_context(text: str, facts: str = "", memory: str = "", links: str = "",
                 notes: tuple[str, ...] = ()) -> str:
    """A planning user message: the trained part, then the optional sections in
    this order: join lines, the facts note, the report memory, then any notes
    (the kinds the user picked, the planner's tool instructions). Empty ones are left out."""
    parts = [text]
    if links:
        parts.append(links)
    if facts:
        parts.append(f"{FACTS_HEADER}\n{facts}")
    if memory:
        parts.append(memory)
    parts.extend(note for note in notes if note)
    return "\n\n".join(parts)
```

In `backend/app/services/agents/chart_kinds.py`, append after `chart_kinds()`:

```python


def include_kinds(kinds: tuple[str, ...] | list[str]) -> str:
    """How the analyst and the planner are told the kinds the user picked, in the
    same words; "" when none was picked."""
    if not kinds:
        return ""
    return f"Include these chart kinds: {', '.join(KIND_INFO[kind]['label'] for kind in kinds)}."
```

In `backend/app/services/agents/planning.py`, make these changes.

1. Add an import. Above `from app.services.agents.planning_contract import (`, add:

```python
from app.services.agents.chart_kinds import include_kinds
```

2. Add `Rank` and `by_size`. Directly after the `Check = ...` line, add:

```python
# How two checked attempts compare: the one with the larger key is kept.
Rank = Callable[[list[dict], list[str]], tuple]


def by_size(items: list[dict], errors: list[str]) -> tuple:
    """The default best attempt: the most usable items, then the fewest problems."""
    return (len(items), -len(errors))
```

3. Change `run_checked`'s signature tail and docstring. Replace

```python
    label: str = "planning",
    max_attempts: int = MAX_ATTEMPTS,
) -> Generator[Retry, None, PlanStep]:
    """Call, check, and send problems back; yields a Retry before each retry, returns the PlanStep."""
```

with

```python
    label: str = "planning",
    max_attempts: int = MAX_ATTEMPTS,
    rank: Rank = by_size,
) -> Generator[Retry, None, PlanStep]:
    """Call, check, and send problems back; yields a Retry before each retry, returns the PlanStep.
    The attempt kept is the one `rank` puts highest."""
```

4. Use `rank` to pick the best attempt. Replace

```python
        items, errors = check(extract_json(raw), tables)
        better = len(items) > len(best_items) or (
            len(items) == len(best_items) and len(errors) < len(best_errors)
        )
        if attempt == 1 or better:
            best_items, best_errors = items, errors
```

with

```python
        items, errors = check(extract_json(raw), tables)
        if attempt == 1 or rank(items, errors) > rank(best_items, best_errors):
            best_items, best_errors = items, errors
```

`by_size` gives exactly the old order, so the analyst and every caller that passes no `rank` behave as before.

5. Tell the planner the kinds, and rank by them. In `plan_charts_steps`, replace the body:

```python
    user = with_context(
        PLANNER_USER_TEMPLATE.format(profiles=render_profiles(profiles), directions=render_directions(directions)),
        facts,
        links=links,
    )
    kinds = tuple(required_kinds)

    def check(payload: Any, tables: dict[str, dict[str, str]]) -> tuple[list[dict], list[str]]:
        return check_specs(payload, tables, validate, kinds)

    return run_checked(llm, PLANNER_SYSTEM_PROMPT, user, check, columns_by_table(profiles), "planner")
```

with:

```python
    kinds = tuple(required_kinds)
    user = with_context(
        PLANNER_USER_TEMPLATE.format(profiles=render_profiles(profiles), directions=render_directions(directions)),
        facts,
        links=links,
        notes=(include_kinds(kinds),),
    )

    def check(payload: Any, tables: dict[str, dict[str, str]]) -> tuple[list[dict], list[str]]:
        return check_specs(payload, tables, validate, kinds)

    def rank(items: list[dict], errors: list[str]) -> tuple:
        # An attempt with the kinds the user picked beats a bigger one without them.
        present = sum(1 for kind in kinds if any(item["chart"] == kind for item in items))
        return (present, *by_size(items, errors))

    return run_checked(llm, PLANNER_SYSTEM_PROMPT, user, check, columns_by_table(profiles), "planner", rank=rank)
```

In `backend/app/services/agents/dashboard_flow.py`, make these changes.

1. Replace the import `from app.services.agents.chart_kinds import KIND_INFO` with:

```python
from app.services.agents.chart_kinds import include_kinds
```

2. Word the analyst's request with the same helper. Replace

```python
    request = brief
    if required_kinds:
        labels = ", ".join(KIND_INFO[kind]["label"] for kind in required_kinds)
        request = f"{brief}\nInclude these chart kinds: {labels}.".strip()
```

with the line below. It produces the same text as before, byte for byte:

```python
    request = f"{brief}\n{include_kinds(required_kinds)}".strip() if required_kinds else brief
```

3. Name the missing kinds in the plan event. Replace

```python
    placed = lay_out(charts.items, top=top + INTRO_HEIGHT)
    intro = {"text": intro_html(profiles, brief, charts.items), "x": 0, "y": top, "w": 12, "h": INTRO_HEIGHT}
    yield Event("plan", {
        "intro": intro, "placed": placed, "tables": tables,
        # How hard planning was: tries per call, and what the checks dropped.
        "attempts": {"analyst": directions.attempts, "planner": charts.attempts},
        "dropped": directions.errors[:5] + charts.errors[:5],
        "facts": facts.splitlines() if facts else [],
    })
```

with

```python
    placed = lay_out(charts.items, top=top + INTRO_HEIGHT)
    intro = {"text": intro_html(profiles, brief, charts.items), "x": 0, "y": top, "w": 12, "h": INTRO_HEIGHT}
    # A kind the user picked that is still not in the plan after every try: said, never dropped silently.
    missing = [kind for kind in required_kinds if not any(spec["chart"] == kind for spec in charts.items)]
    if missing:
        logger.info("[dashboard] the plan has no %s, which the user asked for", ", ".join(missing))
    yield Event("plan", {
        "intro": intro, "placed": placed, "tables": tables,
        # How hard planning was: tries per call, and what the checks dropped.
        "attempts": {"analyst": directions.attempts, "planner": charts.attempts},
        "dropped": directions.errors[:5] + charts.errors[:5],
        "facts": facts.splitlines() if facts else [],
        "missing_kinds": missing,
    })
```

In `backend/app/api/v1/endpoints/blocks.py`, in `_ai_dashboard`'s `plan` branch, replace

```python
                logger.info(
                    "[dashboard] planned %d charts from %s (tries: %s; dropped: %s; facts: %s)",
                    len(placed), names, event.data["attempts"], event.data["dropped"], event.data.get("facts"),
                )
                yield _sse("plan", {"total": total, "source": names, "brief": brief, "sections": sections})
```

with

```python
                missing = event.data.get("missing_kinds", [])
                logger.info(
                    "[dashboard] planned %d charts from %s (tries: %s; dropped: %s; facts: %s; missing kinds: %s)",
                    len(placed), names, event.data["attempts"], event.data["dropped"], event.data.get("facts"),
                    missing,
                )
                yield _sse("plan", {"total": total, "source": names, "brief": brief, "sections": sections,
                                    "missing_kinds": missing})
```

The `skipped` event is deliberately not reused. Its handler counts a finished block, and its banner says a block "could not be drawn". Neither is true of a kind that was never planned.

- [ ] **Step 4: Run the tests, the suite and the finetune suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_planning_steps.py tests/test_planning_contract.py tests/test_dashboard_flow.py tests/test_kind_request.py tests/test_dashboard_endpoint.py`
Expected: all pass.

Run: `cd backend && .venv/bin/python -m pytest -q tests`
Expected: 139 tests; the only failures are the 3 known ones.

Run: `cd chartist-finetune && ../backend/.venv/bin/python -m pytest -q tests`
Expected: 81 passed (`planning_contract.py` is loaded there by path).

- [ ] **Step 5: Record it in AGENTS.md**

Insert these bullets directly after the line that starts with `- Chart kinds: the "/" menu and the chart kinds panel`:

```markdown
- A kind picked for a dashboard is now told to the planner up front, in the analyst's words: `Include these chart kinds: Pie chart.` is appended to its message by `chart_kinds.include_kinds`. Before, it heard of the pick only in a retry message.
- The planner's best try is now the one with the most picked kinds, then the most charts (`planning.run_checked(rank=...)`). Before, a try with 7 charts and no pie beat one with 6 charts including a valid pie. That was the final review's reproduction.
- A kind still missing after the last try is named in the SSE `plan` event as `missing_kinds` and logged with the plan. It is not a `skipped` event, because that event counts as a finished block.
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/agents/planning_contract.py backend/app/services/agents/chart_kinds.py \
  backend/app/services/agents/planning.py backend/app/services/agents/dashboard_flow.py \
  backend/app/api/v1/endpoints/blocks.py backend/tests/test_planning_steps.py \
  backend/tests/test_planning_contract.py backend/tests/test_dashboard_flow.py \
  backend/tests/test_kind_request.py backend/tests/test_dashboard_endpoint.py AGENTS.md
git commit -m "fix(kinds): rank tries by the picked kinds, tell the planner up front, name a miss

A try with 7 charts and no pie beat a try with 6 charts and a valid pie, and
the dashboard planner heard of the pick only in a retry. The planner's best
attempt is now ranked by picked kinds present first; it is told the kinds in
an appended section worded like the analyst's; a kind still missing is sent
as missing_kinds in the plan event. Trained prompts pinned by sha256.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The canvas says when a picked kind could not be planned

Task 2 sends `missing_kinds` in the plan event. This task shows it as one plain line during and after the build, for example "Could not plan a pie chart for this data."

**Files:**
- Create: `byd-web/lib/kind-notice.ts`
- Create: `byd-web/tests/kind-notice.test.mts`
- Modify: `byd-web/lib/blocks.ts` (`DashboardProgress.onPlan`'s type)
- Modify: `byd-web/components/report-canvas.tsx` (state, reset, plan handler, the line)
- Modify: `byd-web/DESIGN.md`, `AGENTS.md`

**Interfaces:**
- Consumes:
  - the SSE `plan` event's `missing_kinds: string[]` (Task 2);
  - `CHART_KINDS` from `byd-web/lib/chart-kinds.ts` (entries with `kind` and `label`).
- Produces: `missingKindsNotice(missing: string[], kinds: KindLabel[]): string` in `lib/kind-notice.ts`. It returns `""` when nothing is missing. It has no imports, so `npm test` (Node's own runner) loads it directly, as it does `lib/slash-menu.ts`.

- [ ] **Step 1: Write the failing test** (`byd-web/tests/kind-notice.test.mts`)

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { missingKindsNotice } from "../lib/kind-notice.ts";

const KINDS = [
  { kind: "pie", label: "Pie chart" },
  { kind: "area", label: "Area chart" },
  { kind: "kpi", label: "KPI card" },
  { kind: "funnel", label: "Funnel" },
];

test("one missing kind is one plain sentence", () => {
  assert.equal(missingKindsNotice(["pie"], KINDS), "Could not plan a pie chart for this data.");
});

test("articles and acronyms read right", () => {
  assert.equal(missingKindsNotice(["area"], KINDS), "Could not plan an area chart for this data.");
  assert.equal(missingKindsNotice(["kpi"], KINDS), "Could not plan a KPI card for this data.");
});

test("several missing kinds share the one line", () => {
  assert.equal(
    missingKindsNotice(["pie", "funnel", "kpi"], KINDS),
    "Could not plan a pie chart, a funnel or a KPI card for this data.",
  );
});

test("nothing missing, nothing to say", () => {
  assert.equal(missingKindsNotice([], KINDS), "");
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd byd-web && npm test`
Expected: the new file fails with `ERR_MODULE_NOT_FOUND` for `lib/kind-notice.ts`; the 4 slash-menu tests still pass.

- [ ] **Step 3: Implement** (`byd-web/lib/kind-notice.ts`)

```ts
/* The line the canvas shows when a chart kind the user picked for a dashboard
   is not in the plan. Kept free of imports so Node's own test runner loads it
   directly (`npm test`); the caller passes the kinds list in. */

export interface KindLabel {
  kind: string;
  label: string;
}

function named(kind: string, kinds: KindLabel[]): string {
  const label = kinds.find((k) => k.kind === kind)?.label ?? kind;
  // "Pie chart" reads "a pie chart"; an acronym keeps its capitals ("a KPI card").
  const text = /^[A-Z][a-z]/.test(label) ? label[0].toLowerCase() + label.slice(1) : label;
  return `${/^[aeiou]/i.test(text) ? "an" : "a"} ${text}`;
}

/** "Could not plan a pie chart for this data." for the kinds the plan lacks; "" when it lacks none. */
export function missingKindsNotice(missing: string[], kinds: KindLabel[]): string {
  if (missing.length === 0) return "";
  const names = missing.map((kind) => named(kind, kinds));
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}`;
  return `Could not plan ${list} for this data.`;
}
```

- [ ] **Step 4: Run the tests**

Run: `cd byd-web && npm test`
Expected: `tests 8`, `pass 8`, `fail 0`.

- [ ] **Step 5: Show the line on the canvas**

In `byd-web/lib/blocks.ts`, in `DashboardProgress`, replace

```ts
  onPlan?: (plan: {
    total: number;
    source: string;
    brief: string;
    sections: PlannedSection[];
  }) => void;
```

with

```ts
  onPlan?: (plan: {
    total: number;
    source: string;
    brief: string;
    sections: PlannedSection[];
    /** Kinds picked with "/" that the plan still lacks after every try. */
    missing_kinds?: string[];
  }) => void;
```

In `byd-web/components/report-canvas.tsx`, make these changes.

1. Replace the import `import type { ChartKind } from "@/lib/chart-kinds";` with:

```tsx
import { CHART_KINDS, type ChartKind } from "@/lib/chart-kinds";
import { missingKindsNotice } from "@/lib/kind-notice";
```

2. Add the state. Directly after `const [skipped, setSkipped] = useState<string[]>([]);`, add:

```tsx
  const [missingKinds, setMissingKinds] = useState<string[]>([]);
```

3. Clear it when a build starts. In `buildDashboard`, replace

```tsx
    setBriefOpen(false);
    setSkipped([]);
```

with

```tsx
    setBriefOpen(false);
    setSkipped([]);
    setMissingKinds([]);
```

4. Set it from the plan event. Replace

```tsx
        onPlan: (plan) => {
          setPlanned(plan.sections);
```

with

```tsx
        onPlan: (plan) => {
          setMissingKinds(plan.missing_kinds ?? []);
          setPlanned(plan.sections);
```

5. Render the line. Replace

```tsx
        {skipped.length > 0 ? (
          <p className="mb-3 px-3 text-[12.5px] text-muted">
```

with

```tsx
        {missingKinds.length > 0 ? (
          <p role="status" className="mb-3 px-3 text-[12.5px] text-muted">
            {missingKindsNotice(missingKinds, CHART_KINDS)}
          </p>
        ) : null}

        {skipped.length > 0 ? (
          <p className="mb-3 px-3 text-[12.5px] text-muted">
```

The line appears when the plan arrives. It stays after the build, including after the chips are cleared on success, until the next build starts. Nothing about it counts toward `building.done`.

- [ ] **Step 6: Type-check and lint**

Run: `cd byd-web && npx tsc --noEmit -p . && npx eslint lib/kind-notice.ts lib/blocks.ts components/report-canvas.tsx tests/kind-notice.test.mts`
Expected: no output from either.

- [ ] **Step 7: Record it in DESIGN.md and AGENTS.md**

In `byd-web/DESIGN.md`, insert this paragraph directly after the paragraph that starts with `**What the loader says is true.**`:

```markdown
**A picked kind is never dropped without a word.** When a kind picked with "/"
for a dashboard is still not in the plan after the planner's last try, the
plan event names it (`missing_kinds`). The canvas then shows one muted line
above the blocks (`text-[12.5px] text-muted`, `role="status"`), "Could not plan
a pie chart for this data." (`lib/kind-notice.ts`), from the plan until the next
build. It is not the skipped-block line: nothing was drawn and failed; the
plan never had it.
```

In `AGENTS.md`, insert this bullet directly after the line that starts with `- A kind still missing after the last try is named in the SSE`, which Task 2 added:

```markdown
- The canvas shows `missing_kinds` as one muted line above the blocks, "Could not plan a pie chart for this data." (`byd-web/lib/kind-notice.ts`, import-free so `npm test` loads it). It shows from the plan until the next build.
```

- [ ] **Step 8: Commit**

```bash
git add byd-web/lib/kind-notice.ts byd-web/tests/kind-notice.test.mts byd-web/lib/blocks.ts \
  byd-web/components/report-canvas.tsx byd-web/DESIGN.md AGENTS.md
git commit -m "feat(web): say when a picked chart kind could not be planned

The plan event's missing_kinds becomes one muted line above the blocks,
'Could not plan a pie chart for this data.', from the plan until the next
build. Not the skipped line: nothing was drawn and failed.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Kind requests on wide tables: a live check, then a fix only if it is needed

The final review's Important 2. A "/" kind request gives the planner one direction whose `Columns:` are the table's first 12 profiled columns (`kind_request.py`, `MAX_DIRECTION_COLUMNS = 12`).
- **Spotify.** On the Spotify table (23 columns) that list leaves out `energy`, so `/box` "energy by genre" sends a direction without the column it names.
- **Wide joined tables.** On a joined table whose child has 12 or more columns, every parent column is cut.

The planner still sees the full profile, so whether this changes plans is unknown. The live check decides:
- If the planner plans the needed column anyway, the code stays and the result is recorded.
- If it does not, the direction lists the columns the question names first, using the brief's existing word overlap.

The fix in Steps 9–13 is **conditional** on Step 8.

**Files:**
- Modify: `backend/app/services/agents/kind_request.py` (extract `direction_columns`; conditional: overlap order)
- Modify: `backend/scripts/make_relational_demo.py` (add the 14-column `visits` table)
- Create: `backend/scripts/check_kind_columns.py`
- Conditional: Modify `backend/app/services/agents/architect.py` (add `by_overlap`), `backend/tests/test_kind_request.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes:
  - `run_kind_request(question, chart_kind, sources, selected_source, planner_llm, chartist, data_dir, detect=None)` (existing). Since Task 2, its planner is told the kind up front.
  - `profile_sources(sources, data_dir)` and `db_sources.candidates_for(row)` (existing).
  - The brief matching in `architect.py`: `_tokens`, `_steer` and `_BRIEF_STOPWORDS`. This is the camelCase-aware overlap with light stemming that AGENTS.md describes, used today by `architect.plan`.
- Produces:
  - `kind_request.direction_columns(question: str, profile: TableProfile) -> list[str]`, at most `MAX_DIRECTION_COLUMNS` names.
  - Conditional: `architect.by_overlap(columns: list[str], text: str) -> list[str]`.
  - `backend/scripts/check_kind_columns.py`, a live check that prints what the direction lists and what the model planned.

On names: ordering by overlap matches the user's own words to column names, and only to choose which columns a direction lists first. It decides no column's role, the model still picks every column, and the checks still read values. It is the brief matching the project already uses, and the user asked for it here.

**Who does what.** An implementer does Steps 1-6 and stops after Step 6's commit. The controller runs Steps 7 and 8. Steps 9-12 go to an implementer only if Step 8 says the fix is needed, and the controller then runs Step 13. Steps 14 and 15 are written from the controller's Step 7 output (and Step 13's, if the fix ran). The later tasks' suite totals depend on Step 8; the counts table gives both.

- [ ] **Step 1: Extract `direction_columns` (no behaviour change)**

In `backend/app/services/agents/kind_request.py`, replace

```python
from app.services.agents.planning import plan_charts
from app.services.agents.spec_runner import run_spec

MAX_DIRECTION_COLUMNS = 12
```

with

```python
from app.services.agents.planning import plan_charts
from app.services.agents.profiler import TableProfile
from app.services.agents.spec_runner import run_spec

MAX_DIRECTION_COLUMNS = 12


def direction_columns(question: str, profile: TableProfile) -> list[str]:
    """The columns the one direction lists: the table's first 12, as profiled."""
    return [column.name for column in profile.columns][:MAX_DIRECTION_COLUMNS]
```

and replace

```python
    direction = {"question": question.strip(), "why": f"the user asked for a {label}", "table": entry.label,
                 "columns": [column.name for column in entry.profile.columns][:MAX_DIRECTION_COLUMNS]}
```

with

```python
    direction = {"question": question.strip(), "why": f"the user asked for a {label}", "table": entry.label,
                 "columns": direction_columns(question, entry.profile)}
```

- [ ] **Step 2: Run the kind-request tests and the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_kind_request.py && .venv/bin/python -m pytest -q tests`
Expected: `4 passed`, then 139 tests with only the 3 known failures.

- [ ] **Step 3: Give the shop demo a wide child table**

No demo table has a joined table whose child has more than 12 columns: `orders+products` has 10. Replace the whole of `backend/scripts/make_relational_demo.py` with the version below. The three existing tables keep their seeded rows: `visits` draws from its own generator, and `visits` is dropped first because it holds a key to `customers`.

```python
"""A small shop database with declared foreign keys, for trying joined tables.

    docker exec -i promptdash-api python /app/scripts/make_relational_demo.py

Creates database `shop` on the app's Postgres if it is missing, then rebuilds
its four tables. Seeded, so every run makes the same rows. Touches nothing
outside `shop`. `visits` is wide on purpose (14 columns, a key to customers):
its joined table, visits+customers, has more columns than a one-chart
direction lists, so it shows whether the parent's columns still reach the planner.
"""
import sys

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, "/app")
from app.core.config import get_settings  # noqa: E402

admin = make_url(get_settings().DATABASE_URL)
with create_engine(admin, isolation_level="AUTOCOMMIT").connect() as conn:
    if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'shop'")).scalar():
        conn.execute(text("CREATE DATABASE shop"))

engine = create_engine(admin.set(database="shop"))
rng = np.random.default_rng(7)
customers = pd.DataFrame({
    "id": range(1, 201),
    "name": [f"Customer {i}" for i in range(1, 201)],
    "region": rng.choice(["North", "South", "East", "West"], 200),
    "segment": rng.choice(["Consumer", "SMB", "Enterprise"], 200, p=[0.6, 0.3, 0.1]),
})
products = pd.DataFrame({
    "id": range(1, 41),
    "name": [f"Product {i}" for i in range(1, 41)],
    "category": rng.choice(["Books", "Games", "Home", "Garden", "Tech"], 40),
    "unit_price": rng.uniform(5, 300, 40).round(2),
})
orders = pd.DataFrame({
    "id": range(1, 5001),
    "customer_id": rng.integers(1, 201, 5000),
    "product_id": rng.integers(1, 41, 5000),
    "order_date": pd.to_datetime("2024-01-01") + pd.to_timedelta(rng.integers(0, 730, 5000), unit="D"),
    "quantity": rng.integers(1, 6, 5000),
})
orders["revenue"] = (orders["quantity"] * products.set_index("id").loc[orders["product_id"], "unit_price"].to_numpy()).round(2)
wide = np.random.default_rng(11)  # its own seed, so the three tables above keep their rows
visits = pd.DataFrame({
    "id": range(1, 2001),
    "customer_id": wide.integers(1, 201, 2000),
    "visit_date": pd.to_datetime("2024-01-01") + pd.to_timedelta(wide.integers(0, 730, 2000), unit="D"),
    "channel": wide.choice(["web", "app", "email", "ads"], 2000),
    "device": wide.choice(["desktop", "mobile", "tablet"], 2000),
    "browser": wide.choice(["Chrome", "Safari", "Firefox", "Edge"], 2000),
    "country": wide.choice(["DE", "FR", "GB", "US", "ES"], 2000),
    "landing_page": wide.choice(["home", "search", "product", "cart", "blog"], 2000),
    "referrer": wide.choice(["google", "newsletter", "partner", "direct"], 2000),
    "pages": wide.integers(1, 21, 2000),
    "minutes": wide.gamma(2.0, 3.0, 2000).round(1),
    "bounced": wide.random(2000) < 0.3,
    "cart_value": wide.uniform(0, 400, 2000).round(2),
    "coupon_used": wide.random(2000) < 0.15,
})

with engine.begin() as conn:
    conn.execute(text("DROP TABLE IF EXISTS visits; DROP TABLE IF EXISTS orders; DROP TABLE IF EXISTS products; "
                      "DROP TABLE IF EXISTS customers"))
    conn.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                      "region TEXT NOT NULL, segment TEXT NOT NULL)"))
    conn.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                      "category TEXT NOT NULL, unit_price NUMERIC(10,2) NOT NULL)"))
    conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, "
                      "customer_id INTEGER NOT NULL REFERENCES customers(id), "
                      "product_id INTEGER NOT NULL REFERENCES products(id), "
                      "order_date DATE NOT NULL, quantity INTEGER NOT NULL, revenue NUMERIC(12,2) NOT NULL)"))
    conn.execute(text("CREATE TABLE visits (id INTEGER PRIMARY KEY, "
                      "customer_id INTEGER NOT NULL REFERENCES customers(id), visit_date DATE NOT NULL, "
                      "channel TEXT NOT NULL, device TEXT NOT NULL, browser TEXT NOT NULL, country TEXT NOT NULL, "
                      "landing_page TEXT NOT NULL, referrer TEXT NOT NULL, pages INTEGER NOT NULL, "
                      "minutes NUMERIC(6,1) NOT NULL, bounced BOOLEAN NOT NULL, cart_value NUMERIC(10,2) NOT NULL, "
                      "coupon_used BOOLEAN NOT NULL)"))
customers.to_sql("customers", engine, if_exists="append", index=False)
products.to_sql("products", engine, if_exists="append", index=False)
orders.to_sql("orders", engine, if_exists="append", index=False)
visits.to_sql("visits", engine, if_exists="append", index=False)
print(f"shop: {len(customers)} customers, {len(products)} products, {len(orders)} orders, "
      f"{len(visits)} visits ({len(visits.columns)} columns)")
```

- [ ] **Step 4: Write the live check** (`backend/scripts/check_kind_columns.py`)

```python
"""Live check: does a "/" kind request on a wide table plan the column its question needs?

    docker exec -i promptdash-api python /app/scripts/check_kind_columns.py \
        "<connection name>" "<table>" <kind> "<question>" "<needed column>"

Prints what the one direction lists, the plan the model wrote, and whether the
needed column is in each. The chart goes through the normal path (planner,
checks, chartist, repairs); nothing is saved.
"""
import sys

sys.path.insert(0, "/app")
from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.data_source import DataSource  # noqa: E402
from app.services import db_sources  # noqa: E402
from app.services.agents.dashboard_flow import profile_sources  # noqa: E402
from app.services.agents.kind_request import direction_columns, run_kind_request  # noqa: E402
from app.services.agents.workflow import _agents  # noqa: E402
from app.services.llm import get_llm  # noqa: E402

connection, table, kind, question, needed = sys.argv[1:6]
db = SessionLocal()
row = db.query(DataSource).filter(DataSource.display_name == connection).first()
if row is None:
    sys.exit(f"no connection named {connection!r}")
candidates = db_sources.candidates_for(row)
source = next((c for c in candidates if c["table"] == table), None)
if source is None:
    sys.exit(f"{table!r} is not offered; tables: {', '.join(c['table'] for c in candidates)}")
settings = get_settings()
profile = profile_sources([source], settings.UPLOAD_DIR)[0].profile
listed = direction_columns(question, profile)
print(f"{table}: {len(profile.columns)} columns; the direction lists {len(listed)}: {', '.join(listed)}")
print(f"needed {needed!r} listed: {needed in listed}")
result = run_kind_request(question, kind, candidates, source["id"], get_llm("spec_planner"), _agents()[2],
                          settings.UPLOAD_DIR)
spec = result.get("spec") or {}
print("plan:", {key: spec.get(key) for key in ("chart", "x", "y", "group", "agg", "top_n")})
print(f"needed {needed!r} planned: {needed in (spec.get('x'), spec.get('y'), spec.get('group'))}")
figure = (result.get("execution_result") or {}).get("figure")
print("rendered:", bool(figure) and not result.get("error"), result.get("error") or "")
```

`selected_source` is the candidate's exact id, so the detective takes it as an explicit selection (`_find_candidate_by_source_hint`) and no ranking is involved.

- [ ] **Step 5: Check both scripts compile**

Run: `cd backend && .venv/bin/python -m py_compile scripts/check_kind_columns.py scripts/make_relational_demo.py`
Expected: no output.

- [ ] **Step 6: Commit the refactor and the scripts**

The live check then runs against committed code.

```bash
git add backend/app/services/agents/kind_request.py backend/scripts/make_relational_demo.py backend/scripts/check_kind_columns.py
git commit -m "chore(kinds): direction_columns, a wide joined demo table, and a live check

No behaviour change: the one-chart direction still lists the first 12
profiled columns, now from direction_columns(). The shop demo gains visits
(14 columns, a key to customers), so visits+customers is wider than that
list; check_kind_columns.py shows whether a '/' request still plans the
column its question names.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Run the live check (controller)**

Preconditions:
- the stack is up (`make up`), on this commit;
- `make serve-model` is serving lora-v2;
- the test account has the connection "Spotify tracks (Postgres)" (database `spotify`, table `tracks`).

1. Rebuild the shop demo:

   Run: `docker exec -i promptdash-api python /app/scripts/make_relational_demo.py`
   Expected: `shop: 200 customers, 40 products, 5000 orders, 2000 visits (14 columns)`

2. If the test account has no connection to `shop`, add one on `/data`:
   - PostgreSQL, host `postgres`, port `5432`, database `shop`;
   - user and password from the root `.env` (`POSTGRES_USER`/`POSTGRES_PASSWORD`; the compose defaults are `promptdash`/`promptdash`);
   - name it `Shop demo`.

3. Spotify:

   Run: `docker exec -i promptdash-api python /app/scripts/check_kind_columns.py "Spotify tracks (Postgres)" tracks box "energy by genre" energy`

4. The wide joined table:

   Run: `docker exec -i promptdash-api python /app/scripts/check_kind_columns.py "Shop demo" "visits+customers" box "minutes by customer segment" customers.segment`

Expected for each, in this shape (values vary):

```
tracks: 23 columns; the direction lists 12: track_id, track_name, ...
needed 'energy' listed: False
plan: {'chart': 'box', 'x': 'playlist_genre', 'y': 'energy', 'group': '', 'agg': 'none', 'top_n': 0}
needed 'energy' planned: True
rendered: True
```

Keep both outputs: Step 14 records them. The model runs at temperature 0, so a rerun of the same prompt gives the same plan.

- [ ] **Step 8: Decide**

- **Both checks print `planned: True`:** keep the first-12 code. Skip Steps 9–13 and go to Step 14.
- **Either prints `planned: False`, or the plan is an error:** do Steps 9–13.

- [ ] **Step 9 (conditional): Write the failing tests** (append to `backend/tests/test_kind_request.py`)

```python


from app.services.agents.kind_request import MAX_DIRECTION_COLUMNS, direction_columns
from app.services.agents.profiler import profile_table


def test_a_wide_table_lists_the_columns_the_question_names_first():
    wide = pd.DataFrame({**{f"c{i:02d}": range(10) for i in range(20)},
                         "energy": [i / 10 for i in range(10)], "playlist_genre": ["pop", "rap"] * 5})
    columns = direction_columns("energy by genre", profile_table("tracks", wide))
    assert columns[:3] == ["energy", "playlist_genre", "c00"] and len(columns) == MAX_DIRECTION_COLUMNS


def test_a_wide_joined_table_keeps_the_parent_column_the_question_names():
    child = {name: ["a", "b"] * 5 for name in ("channel", "device", "browser", "country", "landing_page",
                                               "referrer", "visit_date", "id", "customer_id", "bounced")}
    joined = pd.DataFrame({**child, "pages": range(10), "minutes": [i * 1.5 for i in range(10)],
                           "cart_value": [i * 2.5 for i in range(10)], "coupon_used": [True, False] * 5,
                           "customers.region": ["North", "South"] * 5, "customers.segment": ["SMB", "Consumer"] * 5})
    columns = direction_columns("minutes by customer segment", profile_table("visits+customers", joined))
    assert columns[:2] == ["minutes", "customers.segment"]
```

- [ ] **Step 10 (conditional): Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_kind_request.py -k wide`
Expected: 2 failed. The lists start `['c00', 'c01', 'c02']` and `['channel', 'device']`, the first 12 in frame order.

- [ ] **Step 11 (conditional): Implement**

In `backend/app/services/agents/architect.py`, add this function directly above `def plan(`:

```python
def by_overlap(columns: List[str], text: str) -> List[str]:
    """`columns` with those sharing words with `text` first, most shared words
    first, ties in their own order: the brief's matching, for any text."""
    return _steer(list(columns), {t for t in _tokens(text) if t not in _BRIEF_STOPWORDS})
```

In `backend/app/services/agents/kind_request.py`, replace `direction_columns` with:

```python
def direction_columns(question: str, profile: TableProfile) -> list[str]:
    """The columns the one direction lists, at most 12: those sharing words with
    the question first (the brief's own camelCase-aware overlap), then the
    table's order. The first 12 alone left out the column a question names on a
    wide table, and every parent column on a wide joined table."""
    from app.services.agents.architect import by_overlap

    return by_overlap([column.name for column in profile.columns], question)[:MAX_DIRECTION_COLUMNS]
```

Only the order changes. The direction still lists real profiled columns, at most 12, so its `Columns:` line keeps the short shape the planner was trained on.

- [ ] **Step 12 (conditional): Run the tests and the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_kind_request.py && .venv/bin/python -m pytest -q tests`
Expected: `6 passed`, then 141 tests with only the 3 known failures.

- [ ] **Step 13 (conditional, controller): Re-run both live checks from Step 7**

Expected: `needed ... listed: True` for both. Record whether each now prints `planned: True`.

- [ ] **Step 14: Record the result in AGENTS.md**

Insert one bullet directly after the line that starts with `` - The canvas shows `missing_kinds` ``, which Task 3 added. Fill every `<...>` from the Step 7 output (and Step 13's, if the fix ran); nothing in angle brackets may remain.

- If the fix did not run, use this form:

```markdown
- Kind requests on wide tables, live check <date> (lora-v2, `backend/scripts/check_kind_columns.py`). `/box` "energy by genre" on Spotify `tracks` (<n> columns, `energy` not among the 12 the direction lists) planned x=<x> y=<y>, rendered <yes|no>. `/box` "minutes by customer segment" on the shop demo's `visits+customers` (18 columns, no parent column listed) planned x=<x> y=<y>, rendered <yes|no>. The planner found both columns in the full profile, so the direction still lists the first 12 profiled columns.
```

- If the fix ran, use this form:

```markdown
- Kind requests on wide tables, live check <date> (lora-v2, `backend/scripts/check_kind_columns.py`). Listing the first 12 profiled columns, `/box` "energy by genre" on Spotify `tracks` planned x=<x> y=<y>, and "minutes by customer segment" on `visits+customers` (18 columns) planned x=<x> y=<y>. A one-chart direction now lists the columns the question names first (`kind_request.direction_columns`, the brief's word overlap via `architect.by_overlap`), then the table's order, up to 12. After the change both planned the column: <x/y of each>.
```

- [ ] **Step 15: Commit**

```bash
git add AGENTS.md backend/app/services/agents/kind_request.py backend/app/services/agents/architect.py backend/tests/test_kind_request.py
git commit -m "fix(kinds): <'record the wide-table live check' if no fix, else 'a one-chart direction lists the asked columns first'>

<Step 7's two results, one line each; and, if the fix ran, Step 13's.>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
# Before running: replace both <...> with the real subject and results.
# Without the fix, git add only AGENTS.md: the other paths are unchanged.
```

---

### Task 5: The plan check catches a line whose x repeats, and every placed plan is logged

The user's "Bounce Rate by Hour" chart:
- 168 rows, one per weekday × hourOfDay, were drawn as `px.line(df, x='hourOfDay', y='bounceRatePct')` with no aggregation.
- So the line ran back and forth 7 times, and the frontend's spline smoothing turned it into loops.

Two gaps let it through:
- `check_specs` demands an aggregation on a line only when x is a date or year.
- `validate_spec` only caps points per line.

This task adds one value-based function for the repeated-x problem, `repeated_x`. It also adds one function both callers share, `chart_shape`: `validate_spec` calls it now, and `preview_chart` (Task 8) will call it too. Plans were never logged, so it is unknown whether the planner said `agg=none` or the chartist dropped a `mean`. The last step logs every placed plan.

**Files:**
- Modify: `backend/app/services/agents/data_tools.py` (`_fmt`, `UNITS`, `preview`, `repeated_x`, `_plan_head`, `chart_shape`, `ToolBox.validate_spec`)
- Modify: `backend/app/services/agents/dashboard_flow.py` (one log line per placed plan)
- Test: `backend/tests/test_data_tools.py`, `backend/tests/test_dashboard_flow.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes:
  - `preview(frame, table, x, y, agg, group, top_n, grain) -> dict`, `LINE_POINTS`, `CAPS` and `_num` (existing);
  - `ToolBox.validate_spec`, which `build_dashboard` passes as `validate` when `PLANNER_TOOLS` is on (existing).
- Produces (Task 8 relies on these):
  - `data_tools.repeated_x(frame, x: str, group: str = "") -> str`. It returns the problem in words, or `""`. It names no column of its own.
  - `data_tools.chart_shape(frame, spec: dict) -> tuple[str, list[str]]`. It returns one line on what the plan would draw on the full data, and the plan check's problems. `ToolBox.validate_spec(spec)` returns exactly `chart_shape(frame, spec)[1]`.
  - `data_tools._plan_head(spec) -> str`, for example `"line mean of bounceRatePct by hourOfDay"`.
  - `data_tools._fmt(value) -> str`, a number at three significant figures with thousands separators.
  - `data_tools.UNITS`, the word for a chart's pieces (bars, slices, stages, pieces, cells).
  - `preview(...)` also returns `series` (lines or groups), and `low`/`high` (the value range) when the values are numbers.
  - A log line `[dashboard] chart plan N of M: {json of the spec}` for each placed plan.

What this changes for existing behaviour:
- `validate_spec` now runs `preview` for scatter, histogram and box plans too, which it skipped before. Their only possible problem is "every row is empty".
- A line may now get two problems at once: repeated x, then too many points.
- The data check runs wherever `validate_spec` runs, which is `PLANNER_TOOLS` on (and planner, from Task 9). Task 6's drawing check covers every path regardless.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_data_tools.py`. `toolbox(**frames)` is already defined in that file.

```python


from app.services.agents.data_tools import chart_shape, repeated_x

WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOURS = pd.DataFrame({"weekday": [day for day in WEEK for _ in range(24)], "hourOfDay": list(range(24)) * 7,
                      "bounceRatePct": [30 + (i * 7) % 40 for i in range(168)]})
RAW_LINE = {"chart": "line", "table": "web", "x": "hourOfDay", "y": "bounceRatePct", "agg": "none", "group": "",
            "top_n": 0, "grain": ""}


def test_a_raw_line_whose_x_repeats_goes_back_in_plain_words():
    # 168 rows, one per weekday and hour, drawn over the hour alone: the line ran back and forth 7 times.
    assert toolbox(web=HOURS).validate_spec(RAW_LINE) == [
        "x 'hourOfDay' has 24 values over 168 rows (each appears 7 times), so one line would run back and "
        "forth: set agg (mean for rates, sum for totals) or a group"]


def test_the_line_is_fine_aggregated_or_split_by_its_other_key():
    box = toolbox(web=HOURS)
    assert box.validate_spec({**RAW_LINE, "agg": "mean"}) == []
    assert box.validate_spec({**RAW_LINE, "group": "weekday"}) == []


def test_a_grouped_line_that_still_repeats_names_its_group():
    problem = repeated_x(HOURS.assign(device=["desktop", "mobile"] * 84), "hourOfDay", "device")
    assert "(each appears 7 times within one 'device' line)" in problem and "or another group" in problem


def test_markers_may_repeat_x():
    assert toolbox(web=HOURS).validate_spec({**RAW_LINE, "chart": "scatter"}) == []


def test_the_shape_line_and_the_plan_check_give_one_answer():
    shape, problems = chart_shape(HOURS, RAW_LINE)
    assert problems == toolbox(web=HOURS).validate_spec(RAW_LINE)
    assert shape == "line bounceRatePct by hourOfDay: 168 points per line, x repeats within a line, values 30 to 69"
    bars = {**RAW_LINE, "chart": "bar", "x": "weekday", "agg": "mean"}
    assert chart_shape(HOURS, bars) == ("bar mean of bounceRatePct by weekday: 7 bars (limit 50), values 48.5 to 50.8", [])
```

Append to `backend/tests/test_dashboard_flow.py`. `ChartistAgent`, `Fixed`, `Scripted`, `_source`, `DIRECTIONS` and `CHARTS` are already defined there.

```python


import logging


def test_each_placed_plan_is_logged_with_every_field(tmp_path, caplog):
    # A chart that draws badly can then be traced to its plan (say agg none) or to the code drawn from it.
    caplog.set_level(logging.INFO, logger="app.services.agents.dashboard_flow")
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    list(build_dashboard("churn by country", [_source(tmp_path)], str(tmp_path), Scripted(DIRECTIONS),
                         Scripted(CHARTS), chartist))
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[dashboard] chart plan")]
    assert len(lines) == 1 and lines[0].startswith("[dashboard] chart plan 1 of 1: ")
    logged = json.loads(lines[0].split(": ", 1)[1])
    assert set(logged) == {"title", "question", "chart", "table", "x", "y", "group", "agg", "grain", "sort", "top_n"}
    assert (logged["chart"], logged["x"], logged["agg"]) == ("bar", "cntry_cd", "sum")
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_data_tools.py tests/test_dashboard_flow.py`
Expected:
- `test_data_tools.py` errors at collection with `ImportError: cannot import name 'chart_shape'`;
- `test_each_placed_plan_is_logged_with_every_field` fails on `assert len(lines) == 1`, because nothing is logged yet.

- [ ] **Step 3: Implement in `data_tools.py`**

1. Add `_fmt`. Directly after `_num`, add:

```python


def _fmt(value: Any) -> str:
    """A number inside a one-line fact: three significant figures, thousands separated."""
    number = _num(value)
    return f"{number:,.0f}" if abs(number) >= 1000 else f"{number:g}"
```

2. Add `UNITS`. Directly after the `CAPS = {...}` line, add:

```python
UNITS = {"bar": "bars", "waterfall": "bars", "pie": "slices", "funnel": "stages", "treemap": "pieces",
         "sunburst": "pieces", "heatmap": "cells"}
```

3. In `preview`, add `series` and the value range to the raw-points branch. Replace

```python
    if agg == "none" or not x:
        out["points"] = out["shown"] = int(len(data))
        out["per_series"] = int(data.groupby(group).size().max()) if group and len(data) else int(len(data))
```

with

```python
    if agg == "none" or not x:
        out["points"] = out["shown"] = int(len(data))
        out["per_series"] = int(data.groupby(group).size().max()) if group and len(data) else int(len(data))
        out["series"] = int(data[group].nunique()) if group else 1
        measure = y or x
        if measure and len(data) and pd.api.types.is_numeric_dtype(data[measure]):
            out["low"], out["high"] = _num(data[measure].min()), _num(data[measure].max())
```

and to the aggregated branch, replace

```python
    out["shown"] = int(len(values))
    out["per_series"] = int(values.groupby(level=1).size().max()) if group and len(values) else int(len(values))
```

with

```python
    out["shown"] = int(len(values))
    out["per_series"] = int(values.groupby(level=1).size().max()) if group and len(values) else int(len(values))
    out["series"] = int(values.index.get_level_values(1).nunique()) if group and len(values) else 1
    if len(values) and pd.api.types.is_numeric_dtype(values):
        out["low"], out["high"] = _num(values.min()), _num(values.max())
```

4. Add `repeated_x`, `_plan_head` and `chart_shape`. Insert these three functions directly above `def tool_specs(`:

```python
def repeated_x(frame: pd.DataFrame, x: str, group: str = "") -> str:
    """The problem with drawing raw rows as a line when x repeats within one
    line, in plain words; "" when each x value is once per line.

    The one place this is decided: the plan check and the planner's
    preview_chart both reach it through chart_shape, so they cannot disagree.
    """
    keys = [column for column in (x, group) if column]
    if not x:
        return ""
    data = frame[keys].dropna()
    if not len(data):
        return ""
    per_line = data.groupby(keys).size()
    most = int(per_line.max())
    if most <= 1:
        return ""
    times = f"each appears {most} times" if int(per_line.min()) == most else f"up to {most} times"
    within = f" within one '{group}' line" if group else ""
    fix = "or another group" if group else "or a group"
    return (f"x '{x}' has {int(data[x].nunique()):,} values over {len(data):,} rows ({times}{within}), "
            f"so one line would run back and forth: set agg (mean for rates, sum for totals) {fix}")


def _plan_head(spec: dict) -> str:
    """A plan in a few words: "line mean of bounceRatePct by hourOfDay"."""
    chart = str(spec.get("chart") or "")
    x, y, group = (str(spec.get(key) or "") for key in ("x", "y", "group"))
    agg = str(spec.get("agg") or "sum")
    if agg == "count" or (not y and agg != "none"):
        measure = "row count"
    elif agg == "none":
        measure = y or x
    else:
        measure = f"{agg} of {y}"
    return f"{chart} {measure}" + (f" by {x}" if x and measure != x else "") + (f" per {group}" if group else "")


def chart_shape(frame: pd.DataFrame, spec: dict) -> tuple[str, list[str]]:
    """What a chart plan would draw on the full data, in one line, and the
    problems the plan check raises for it ([] when none).

    ToolBox.validate_spec (the check on every final plan) and the planner's
    preview_chart tool both call this, so a preview and the check cannot
    disagree. Facts only: it never changes a plan, picks a column or draws.
    """
    chart = str(spec.get("chart") or "")
    x, y, group = (str(spec.get(key) or "") for key in ("x", "y", "group"))
    agg = str(spec.get("agg") or "sum")
    head = _plan_head(spec)
    if chart == "kpi":
        if agg == "count" or not y:
            return f"{head}: one number, {len(frame):,} rows", []
        if agg in ("sum", "mean", "median", "min", "max"):
            return f"{head}: one number, {_fmt(getattr(frame[y].dropna(), agg)())}", []
        return f"{head}: one number", []
    shown = preview(frame, str(spec.get("table") or ""), x, y, agg, group, int(spec.get("top_n") or 0),
                    str(spec.get("grain") or ""))
    if shown.get("rows_used") == 0:
        return f"{head}: no rows with values", [f"'{y or x}' has no values to plot: every row is empty"]
    problems: list[str] = []
    n = int(shown.get("shown", 0))
    if chart in ("line", "area"):
        per_line = int(shown.get("per_series", n))
        repeat = repeated_x(frame, x, group) if agg == "none" else ""
        text = f"{per_line:,} points per line" + (f", {int(shown.get('series', 1)):,} lines" if group else "")
        text += ", x repeats within a line" if repeat else ", x once per line"
        if repeat:
            problems.append(repeat)
        if per_line > LINE_POINTS:
            problems.append(f"would draw {per_line:,} points on one line: aggregate it (agg, or a grain for dates)")
    elif chart in CAPS:
        cap, unit = CAPS[chart], UNITS[chart]
        text = f"{n:,} {unit} (limit {cap})"
        if n > cap:
            problems.append(f"would draw {n:,} {unit}, more than {cap}: set top_n or use a coarser column")
    else:
        text = f"{n:,} raw points"
    if "low" in shown:
        text += f", values {_fmt(shown['low'])} to {_fmt(shown['high'])}"
    return f"{head}: {text}", problems
```

5. Route `validate_spec` through `chart_shape`. Replace the whole of `ToolBox.validate_spec` with:

```python
    def validate_spec(self, spec: dict) -> list[str]:
        """Objective problems a planned chart would have on the real data. Not a
        judgement of taste: only what cannot be drawn readably (chart_shape)."""
        try:
            return chart_shape(self.frame(spec["table"]), spec)[1]
        except Exception as exc:  # noqa: BLE001 - a check that cannot run is not a problem with the plan
            logger.warning("[tools] could not check chart plan %s: %s", spec.get("title"), exc)
            return []
```

The bar-cap message is unchanged for bars ("would draw 60 bars, more than 50: ..."). A pie now says "slices", a funnel "stages", a treemap "pieces", a heatmap "cells".

- [ ] **Step 4: Log every placed plan in `dashboard_flow.py`**

Add `import json` above `import logging`, then replace

```python
    placed = lay_out(charts.items, top=top + INTRO_HEIGHT)
    intro = {"text": intro_html(profiles, brief, charts.items), "x": 0, "y": top, "w": 12, "h": INTRO_HEIGHT}
```

with

```python
    placed = lay_out(charts.items, top=top + INTRO_HEIGHT)
    for n, item in enumerate(placed, 1):
        # Every field, so a bad chart can be traced to its plan or to the code drawn from it.
        logger.info("[dashboard] chart plan %d of %d: %s", n, len(placed), json.dumps(item.spec, ensure_ascii=False))
    intro = {"text": intro_html(profiles, brief, charts.items), "x": 0, "y": top, "w": 12, "h": INTRO_HEIGHT}
```

- [ ] **Step 5: Run the tests and the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_data_tools.py tests/test_dashboard_flow.py`
Expected: all pass. That includes the existing `test_validate_refuses_a_line_through_every_raw_row`, whose x is unique, so its first problem is still the points cap.

Run: `cd backend && .venv/bin/python -m pytest -q tests`
Expected: 6 more tests than after Task 4 (147 with Task 4's fix, 145 without); the only failures are the 3 known ones.

- [ ] **Step 6: Record it in AGENTS.md**

Insert these bullets directly after the line that starts with `- Planner tools (`:

```markdown
- A line or area plan with `agg` none whose x repeats within one line (per `group`) goes back to the planner in words: "x 'hourOfDay' has 24 values over 168 rows (each appears 7 times), so one line would run back and forth: set agg (mean for rates, sum for totals) or a group". The check is `data_tools.repeated_x`, reached through `chart_shape`, which `ToolBox.validate_spec` calls, so it runs with the other data checks. It was found from "Bounce Rate by Hour": 168 weekday × hour rows drawn as one line over the hour.
- Every placed chart plan is logged with all its fields: `[dashboard] chart plan 2 of 7: {"chart": "line", ..., "agg": "none", ...}`. A bad chart can then be traced to its plan or to the code drawn from it.
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/agents/data_tools.py backend/app/services/agents/dashboard_flow.py \
  backend/tests/test_data_tools.py backend/tests/test_dashboard_flow.py AGENTS.md
git commit -m "feat(planning): send back a line whose x repeats; log every placed plan

168 weekday x hour rows were drawn as one line over the hour and the line
ran back and forth. A line or area plan with agg none whose x repeats within
one line now goes back to the planner in words (data_tools.repeated_x, via
chart_shape, the one function validate_spec and the coming preview_chart
share). Each placed plan is logged with all its fields.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The drawing check: a line drawn back and forth goes back to the model, on every path

Task 5 checks plans, but only where `validate_spec` runs. The single-chart ask bar, "/" kind requests and the comparison never pass a plan through it, and a chartist can drop a planned `mean`.

So the figure itself is checked after the model's code runs, in `workflow.run_on_frame`. That is the one loop the dashboard (`run_spec` → `run_chart_code`), the ask bar (`execution_node`), "/" kind requests (`run_spec`) and both comparison engines (`comparison.run_cell`) share.

A line-mode trace whose x values repeat is a contract problem. It goes back to the model as a repair turn and counts against `MAX_REPAIRS`. Nothing redraws or edits the figure.

**Files:**
- Modify: `backend/app/services/agents/chartist_contract.py` (add `REPEATED_X_FIX`, `_drawn_as_line`, `figure_problems`)
- Modify: `backend/app/services/agents/workflow.py` (imports, `run_on_frame`)
- Modify: `backend/app/services/agents/spec_runner.py` (pass `repair_reasons` on)
- Test: create `backend/tests/test_drawing_check.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes:
  - `decode_typed_arrays(value)` from `backend/app/utils/figure_json.py`. plotly 7 stores numeric arrays as `{"dtype", "bdata"}`; `px.line`'s x is one.
  - `run_on_frame(executor, code, df, repair=None, max_repairs=MAX_REPAIRS)` and `comparison.run_cell` (existing).
- Produces:
  - `chartist_contract.REPEATED_X_FIX = "each x value should appear once per line: aggregate y for each x and sort by x"`. Task 10's harness counts repairs by these words.
  - `chartist_contract.figure_problems(figure: dict) -> list[str]`. It expects plain lists, so decode first. `chartist_contract.py` stays standard-library only, because the finetune loads it by path.
  - `run_on_frame(...)` returns `"repair_reasons": list[str]`, the problem behind each repair asked for, on success and on failure. When the drawing check still fails after the last repair, `execution_result` is `{..., "success": False, "figure": None, "error": <problem>}`, so no caller can take it for a chart. `comparison.run_cell` decides `ok` from `execution_result["success"]`.
  - `run_spec(...)` returns `"repair_reasons"` too (`[]` on its early returns).

Which traces count (the controller's ruling on this plan's open question, 2026-11-23):
- **Counted:** `scatter`/`scattergl` traces that Plotly draws with lines: a `mode` that contains `"lines"`, `stackgroup` set (an area), or no `mode` at all. Plotly's own reference for a scatter with no mode: under 20 points and not stacked it draws "lines+markers", otherwise "lines". So a trace with no mode is a line; its problem line adds "(it has no mode, so Plotly draws it as a line; for a scatter, set mode='markers')", unless it is a stacked area.
- **Not counted:** markers-only traces (and `mode="none"`), which may repeat x, and a closed shape (`fill="toself"`, such as a confidence band), which goes back over its x by design.
- **The problem:** one x value carrying more than one y value in the same trace. The same x with the same y (a fitted line over data whose x repeats) draws over itself and is not a problem.
- **A staircase is fine** (controller ruling after the Task 6 review, 2026-11-23): x that never goes back with y that only rises or only falls, such as `px.ecdf` (x sorted with ties, cumulative y, drawn as steps) or a running total over sorted x. It never runs back and forth. A sorted x whose y jumps up and down at a repeated x is still a problem.
- **Never a failure:** an x that is not a list or cannot be compared; a `y` that is not a list as long as `x` (a missing `y` is drawn along the row index, so it never runs back); points whose x or y is missing.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_drawing_check.py`)

```python
"""A line the model draws back and forth goes back to the model, on every path
that runs its code (dashboard, ask bar, "/" kinds, comparison)."""
import pandas as pd

from app.services import comparison
from app.services.agents.chartist import ChartistAgent
from app.services.agents.chartist_contract import REPEATED_X_FIX, figure_problems
from app.services.agents.spec_runner import run_spec
from app.services.agents.workflow import run_on_frame
from app.utils.executor import SafeExecutor

WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOURS = pd.DataFrame({"weekday": [day for day in WEEK for _ in range(24)], "hourOfDay": list(range(24)) * 7,
                      "bounceRatePct": [30 + (i * 7) % 40 for i in range(168)]})
LOOPS = ("import plotly.express as px\n"
         "fig = px.line(df, x='hourOfDay', y='bounceRatePct')\n"
         "print(fig.to_json())\n")
ONE_POINT_PER_HOUR = ("import plotly.express as px\n"
                      "d = df.groupby('hourOfDay', as_index=False)['bounceRatePct'].mean().sort_values('hourOfDay')\n"
                      "fig = px.line(d, x='hourOfDay', y='bounceRatePct')\n"
                      "print(fig.to_json())\n")


def figure(**fields):
    return {"data": [{"type": "scatter", "x": [0, 1, 0, 1], "y": [1, 2, 3, 4], **fields}]}


def test_a_line_whose_x_repeats_is_a_problem_the_model_can_act_on():
    problems = figure_problems(figure(mode="lines"))
    assert problems == ["the line 'trace 1' has 4 points but only 2 x values, so it runs back and forth: "
                        + REPEATED_X_FIX]


def test_a_stacked_area_is_a_line():
    assert figure_problems(figure(stackgroup="1")) and figure_problems(figure(mode="lines+markers"))


def test_markers_may_repeat_x():
    assert figure_problems(figure(mode="markers")) == [] and figure_problems(figure(mode="none")) == []


def test_a_trace_with_no_mode_is_drawn_as_a_line():
    assert figure_problems(figure()) == [
        "the line 'trace 1' has 4 points but only 2 x values, so it runs back and forth: " + REPEATED_X_FIX
        + " (it has no mode, so Plotly draws it as a line; for a scatter, set mode='markers')"]


def test_a_closed_shape_may_go_back_over_its_x():
    band = figure(mode="lines", fill="toself", x=[0, 1, 2, 2, 1, 0], y=[3, 4, 5, 1, 2, 1])
    assert figure_problems(band) == []


def test_an_x_repeated_with_the_same_y_is_fine():
    assert figure_problems(figure(mode="lines", y=[1, 2, 1, 2])) == []


def test_a_line_with_each_x_once_or_unreadable_values_is_fine():
    assert figure_problems(figure(mode="lines", x=[0, 1, 2, 3])) == []
    assert figure_problems(figure(mode="lines", x={"dtype": "i1", "bdata": "!!"})) == []
    assert figure_problems(figure(mode="lines", y={"dtype": "i1", "bdata": "!!"})) == []
    assert figure_problems(figure(mode="lines", y=None)) == []
    assert figure_problems({"data": [{"type": "bar", "x": [0, 0]}]}) == []


def test_the_model_is_asked_to_fix_a_line_that_runs_back_and_forth():
    # px.line stores x as a typed array, so this also shows the figure is decoded before it is read.
    asked = []
    outcome = run_on_frame(SafeExecutor(), LOOPS, HOURS,
                           repair=lambda code, problem: asked.append(problem) or ONE_POINT_PER_HOUR)
    assert outcome["repairs"] == 1 and outcome["repair_reasons"] == asked and REPEATED_X_FIX in asked[0]
    assert outcome["execution_result"]["success"] and outcome["code_run"] == ONE_POINT_PER_HOUR


def test_a_line_never_fixed_is_reported_failed_without_a_figure():
    outcome = run_on_frame(SafeExecutor(), LOOPS, HOURS, repair=lambda code, problem: LOOPS)
    assert outcome["repairs"] == 2 and "back and forth" in outcome["error"]
    assert outcome["execution_result"]["success"] is False and outcome["execution_result"]["figure"] is None


class Scripted:
    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []

    def invoke(self, variables):
        self.requests.append(dict(variables))
        return self.replies.pop(0)


def _chartist(*replies):
    model = Scripted(*replies)
    return ChartistAgent(llm=None, generator=model, chart_type_hint_style="off"), model


def test_a_planned_chart_says_why_it_was_repaired(tmp_path):
    path = tmp_path / "web.csv"
    HOURS.to_csv(path, index=False)
    spec = {"title": "Bounce rate by hour", "question": "Bounce rate by hour", "chart": "line", "table": "web.csv",
            "x": "hourOfDay", "y": "bounceRatePct", "group": "", "agg": "mean", "grain": "", "sort": "", "top_n": 0}
    chartist, model = _chartist(LOOPS, ONE_POINT_PER_HOUR)
    result = run_spec(spec, {"type": "file", "name": "web.csv", "path": str(path)}, chartist, str(tmp_path))
    assert result["error"] == "" and result["repairs"] == 1
    assert REPEATED_X_FIX in result["repair_reasons"][0] and REPEATED_X_FIX in model.requests[1]["problem"]


def test_a_comparison_cell_with_a_line_never_fixed_is_not_a_chart():
    chartist, _ = _chartist(LOOPS, LOOPS, LOOPS)
    context = {"columns": list(HOURS.columns), "dtypes": {c: str(t) for c, t in HOURS.dtypes.items()},
               "sample": HOURS.head(3).to_dict("records")}
    cell = comparison.run_cell("slm", chartist, "Bounce rate by hour", {}, context, HOURS, SafeExecutor())
    assert not cell.ok and cell.figure is None and cell.repairs == 2 and "back and forth" in cell.error
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_drawing_check.py`
Expected: a collection error, `ImportError: cannot import name 'REPEATED_X_FIX' from 'app.services.agents.chartist_contract'`.

- [ ] **Step 3: Implement**

In `backend/app/services/agents/chartist_contract.py`, insert directly above `def _syntax_problem(`:

```python
# Said to the model when a line it drew runs back and forth. The planning
# measurement counts repairs by these words, so change both together.
REPEATED_X_FIX = "each x value should appear once per line: aggregate y for each x and sort by x"


def _drawn_as_line(trace: dict) -> bool:
    """A scatter trace that Plotly draws with lines: its mode includes "lines",
    it is a stacked area, or it has no mode (Plotly's reference: "lines+markers"
    under 20 points when not stacked, otherwise "lines"). Markers-only traces
    may repeat x, and a closed shape (fill="toself", such as a band) goes back
    over its x by design."""
    if trace.get("type", "scatter") not in ("scatter", "scattergl") or trace.get("fill") == "toself":
        return False
    mode = trace.get("mode")
    return bool(trace.get("stackgroup")) or mode is None or "lines" in str(mode)


def figure_problems(figure: dict) -> list[str]:
    """What a drawn figure gets wrong, in words the model can act on; [] when nothing does.

    Expects plain lists: decode Plotly's typed arrays first, as
    workflow.run_on_frame does. One rule today: a line on which one x value
    carries more than one y value runs back and forth across the chart (rows of
    two keys, drawn as one line over one of them). The same x with the same y
    draws over itself and is fine. An x or y that cannot be read is not a problem.
    """
    problems = []
    for n, trace in enumerate((figure or {}).get("data") or [], 1):
        if not isinstance(trace, dict) or not _drawn_as_line(trace):
            continue
        xs, ys = trace.get("x"), trace.get("y")
        if not isinstance(xs, list) or not isinstance(ys, list) or len(xs) != len(ys):
            continue
        points = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
        seen: dict = {}
        try:
            for x, y in points:
                seen.setdefault(tuple(x) if isinstance(x, list) else x, set()).add(
                    tuple(y) if isinstance(y, list) else y)
        except TypeError:
            continue
        if any(len(values) > 1 for values in seen.values()):
            name = str(trace.get("name") or "").strip() or f"trace {n}"
            problem = (f"the line '{name}' has {len(points):,} points but only {len(seen):,} x values, "
                       f"so it runs back and forth: {REPEATED_X_FIX}")
            if trace.get("mode") is None and not trace.get("stackgroup"):
                problem += " (it has no mode, so Plotly draws it as a line; for a scatter, set mode='markers')"
            problems.append(problem)
    return problems
```

In `backend/app/services/agents/workflow.py`, make these changes.

1. Replace `from app.services.agents.chartist_contract import problems_with` with:

```python
from app.services.agents.chartist_contract import figure_problems, problems_with
```

2. Directly after `from app.utils.executor import SafeExecutor`, add:

```python
from app.utils.figure_json import decode_typed_arrays
```

3. In `run_on_frame`, replace the docstring and loop head, from the docstring's first line down to `repairs += 1`:

```python
    """Check and run the model's code; on any failure send the problem back to
    the model for a fix, at most `max_repairs` times, then report the failure.

    The chart is always the model's own code. There is no deterministic
    stand-in and no code-side patching: a hardcoded backup once drew 32,833 bars
    of the wrong column under the planned title, froze the report it sat in and
    hid that the model had failed. A chart the model cannot fix is reported.
    """
    started = time.perf_counter()
    repairs = 0
    result: Dict[str, Any] = {}
    while True:
        problems = problems_with(code)
        if problems:
            problem = "; ".join(problems)
        else:
            result = executor.execute(code, df)
            if result.get("success"):
                logger.info(
                    "[workflow/executor] success in %.2fs after %d fix(es)",
                    time.perf_counter() - started,
                    repairs,
                )
                return {
                    "execution_result": result,
                    "code_run": code,
                    "repairs": repairs,
                    "messages": [AIMessage(content="Chart rendered.")],
                }
            problem = _run_problem(result)
        if repair is None or repairs >= max_repairs:
            break
        repairs += 1
```

with:

```python
    """Check and run the model's code; on any failure send the problem back to
    the model for a fix, at most `max_repairs` times, then report the failure.

    A failure is code that breaks the contract, code that does not run, or a
    figure that breaks it (`figure_problems`: a line whose x repeats runs back
    and forth). `repair_reasons` lists the problem behind each fix asked for.

    The chart is always the model's own code. There is no deterministic
    stand-in and no code-side patching: a hardcoded backup once drew 32,833 bars
    of the wrong column under the planned title, froze the report it sat in and
    hid that the model had failed. A chart the model cannot fix is reported.
    """
    started = time.perf_counter()
    repairs = 0
    reasons: List[str] = []
    result: Dict[str, Any] = {}
    while True:
        problems = problems_with(code)
        if problems:
            problem = "; ".join(problems)
        else:
            result = executor.execute(code, df)
            drawn = figure_problems(decode_typed_arrays(result.get("figure") or {})) if result.get("success") else []
            if result.get("success") and not drawn:
                logger.info(
                    "[workflow/executor] success in %.2fs after %d fix(es)",
                    time.perf_counter() - started,
                    repairs,
                )
                return {
                    "execution_result": result,
                    "code_run": code,
                    "repairs": repairs,
                    "repair_reasons": reasons,
                    "messages": [AIMessage(content="Chart rendered.")],
                }
            if drawn:
                problem = "; ".join(drawn)
                # It ran, but what it drew breaks the contract: no caller may take it for a chart.
                result = {**result, "success": False, "figure": None, "error": problem}
            else:
                problem = _run_problem(result)
        if repair is None or repairs >= max_repairs:
            break
        repairs += 1
        reasons.append(problem)
```

4. In the failure return at the end of `run_on_frame`, replace

```python
        "code_run": code,
        "repairs": repairs,
        "messages": [AIMessage(content=f"Chart failed: {problem}")],
```

with

```python
        "code_run": code,
        "repairs": repairs,
        "repair_reasons": reasons,
        "messages": [AIMessage(content=f"Chart failed: {problem}")],
```

`List` is already imported from `typing` in `workflow.py`.

In `backend/app/services/agents/spec_runner.py`, add `"repair_reasons": []` after `"repairs": 0,` in both early returns, so each of them reads:

```python
            "data_context": context,
            "repairs": 0,
            "repair_reasons": [],
        }
```

and replace the final return's last entry

```python
        "repairs": outcome.get("repairs", 0),
    }
```

with

```python
        "repairs": outcome.get("repairs", 0),
        "repair_reasons": outcome.get("repair_reasons", []),
    }
```

- [ ] **Step 4: Run the tests, the suite and the finetune suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_drawing_check.py tests/test_model_repair.py tests/test_spec_runner.py`
Expected: all pass.

Run: `cd backend && .venv/bin/python -m pytest -q tests`
Expected: 11 more tests than after Task 5 (158 with Task 4's fix, 156 without); the only failures are the 3 known ones.

Run: `cd chartist-finetune && ../backend/.venv/bin/python -m pytest -q tests`
Expected: 81 passed (`chartist_contract.py` is loaded there by path and still imports only the standard library).

- [ ] **Step 5: Record it in AGENTS.md**

Insert this bullet directly after the line that starts with `- NO HARDCODED CHARTS, the user's standing rule`:

```markdown
- The drawing check (`chartist_contract.figure_problems`, called in `workflow.run_on_frame` after the figure is decoded) runs on every path: dashboard, ask bar, "/" kinds and the comparison.
  - A trace Plotly draws with lines (a mode with lines, `stackgroup`, or no mode at all, which Plotly draws as a line) on which one x carries more than one y goes back to the model as a repair: "each x value should appear once per line: aggregate y for each x and sort by x". It counts against `MAX_REPAIRS`.
  - Not checked: markers-only traces, closed shapes (`fill="toself"`, such as bands), and an x repeated with the same y (a fitted line draws over itself).
  - A line still drawn that way after two fixes is reported failed, with no figure.
  - `run_on_frame` and `run_spec` return `repair_reasons`, the problem behind each fix.
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/agents/chartist_contract.py backend/app/services/agents/workflow.py \
  backend/app/services/agents/spec_runner.py backend/tests/test_drawing_check.py AGENTS.md
git commit -m "feat(chartist): a line drawn back and forth goes back to the model

After the code runs, run_on_frame decodes the figure and checks each line-mode
trace: x repeating within a trace is a contract problem, sent back as a repair
turn ('each x value should appear once per line: aggregate y for each x and
sort by x') within MAX_REPAIRS. Every path shares the loop; nothing redraws
the chart. repair_reasons records why each fix was asked for.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `row_grain`, and `inspect_column` says how often values repeat

The planner's first new tool tells it what one row is, so it knows that x repeats before it plans a line. For example: "one row per weekday × hourOfDay (168 rows); other columns describe the row".

It works from values only:
- **Search.** It searches the profile's 2,000-row sample, label columns with the fewest values first, for keys of up to 3 columns, trying at most 8 columns.
- **Confirmation.** Each candidate is confirmed on the full table in one pass, at most 3 candidates. A key the sample cannot see through is caught there, and the next candidate is tried.
- **Measures.** A column with fractions is a measure and never part of a key. A whole number unique by chance is not an id unless it counts the rows.

Tool sets also become per role in this task. The explorer keeps exactly its four tools. Its results still change in this plan (Task 5 adds a series count and the value range to `preview`; this task adds how often values repeat to `inspect_column`), so the `on` arm measured in Task 10 is not exactly today's behaviour; both arms run the same code, so the comparison stays fair. A tool that was not offered is refused.

**Files:**
- Modify: `backend/app/services/agents/data_tools.py` (`inspect_column`, constants, `row_grain`, `tool_specs`, `ToolBox.__init__`, `ToolBox.specs`, `ToolBox._run`)
- Test: `backend/tests/test_data_tools.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes:
  - `architect.spread_sample(frame, rows)`, which `row_grain` imports inside the function, so a test can patch `architect.spread_sample`;
  - `KIND_SAMPLE = 2000` (existing).
- Produces (Tasks 8 and 9 rely on these):
  - `data_tools.row_grain(frame, table: str) -> dict`, with keys `table`, `rows`, `key` (column names in table order, or `[]`) and `fact` (one line).
  - Constants: `EXPLORER_TOOL_NAMES = ("find_columns", "inspect_column", "relationship", "preview")` (it replaces `TOOL_NAMES`), `GRAIN_COLUMNS = 8`, `GRAIN_SIZE = 3` and `GRAIN_CONFIRMS = 3`.
  - `tool_specs(tables: list[str], names: tuple[str, ...] = EXPLORER_TOOL_NAMES)` returns the named tools in that order. It now includes a `row_grain` spec.
  - `ToolBox(sources, data_dir, max_calls=MAX_CALLS, loader=None, tools=EXPLORER_TOOL_NAMES)`. `ToolBox.tools` is what `specs` offers, and `_run` refuses any other name with `"no tool '<name>'; tools are: ..."`.
  - `inspect_column` adds `rows_per_value` (rounded to 0.1) whenever distinct is less than the non-empty rows. Its fact gains "each value appears about N times" when N ≥ 1.5.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_data_tools.py`. `json`, `pd`, `ToolBox`, `inspect_column` and `toolbox` are already imported or defined there.

```python


from app.services.agents import architect
from app.services.agents.data_tools import EXPLORER_TOOL_NAMES, row_grain

DAYS7 = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
GRID = pd.DataFrame({"weekday": [day for day in DAYS7 for _ in range(24)], "hourOfDay": list(range(24)) * 7,
                     "sessions": [100 + (i * 37) % 900 for i in range(168)],
                     "bounceRatePct": [30.5 + (i * 7) % 40 for i in range(168)]})


def test_row_grain_names_the_columns_that_identify_a_row():
    assert row_grain(GRID, "web")["fact"] == (
        "web: one row per weekday × hourOfDay (168 rows); other columns describe the row")


def test_row_grain_takes_an_id_that_counts_the_rows():
    orders = pd.DataFrame({"order_id": range(1, 301), "region": ["N", "S", "E"] * 100,
                           "amount": [i * 1.5 for i in range(300)]})
    assert row_grain(orders, "orders")["key"] == ["order_id"]


def test_a_number_unique_by_chance_is_not_a_key():
    events = pd.DataFrame({"region": ["N", "S", "E", "W"] * 25, "sessions": [100 + 3 * i for i in range(100)]})
    assert row_grain(events, "events")["fact"] == (
        "events: no key found among the columns tried, alone or up to 3 together (100 rows)")


def test_a_key_the_sample_misses_is_caught_on_the_full_table(monkeypatch):
    # The first 2,000 rows (the sample here) never repeat shop and day; the last 200 do,
    # so that pair fails on the full table and the next candidate is tried.
    monkeypatch.setattr(architect, "spread_sample", lambda frame, rows: frame.head(rows))
    first = [{"shop": i // 200, "day": i % 200, "till": i % 3} for i in range(2000)]
    extra = [{"shop": 0, "day": i % 200, "till": 3} for i in range(200)]
    frame = pd.DataFrame(first + extra).assign(amount=[i * 0.5 for i in range(2200)])
    assert row_grain(frame, "t")["key"] == ["shop", "day", "till"]


def test_inspect_says_how_often_each_value_repeats():
    facts = inspect_column(GRID, "web", "hourOfDay")
    assert facts["rows_per_value"] == 7.0 and "each value appears about 7 times" in facts["fact"]


def test_row_grain_is_a_tool_only_where_it_is_offered():
    offered = ToolBox({"web": {"type": "file", "name": "web"}}, "", loader=lambda source, data_dir: GRID,
                      tools=EXPLORER_TOOL_NAMES + ("row_grain",))
    assert json.loads(offered.call("row_grain", {"table": "web"}))["key"] == ["weekday", "hourOfDay"]
    assert "no tool 'row_grain'" in json.loads(toolbox(web=GRID).call("row_grain", {"table": "web"}))["error"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_data_tools.py`
Expected: a collection error, `ImportError: cannot import name 'EXPLORER_TOOL_NAMES'`.

- [ ] **Step 3: Implement**

In `backend/app/services/agents/data_tools.py`, make these changes.

1. Report repeats in `inspect_column`. Replace

```python
    facts = [f"{table}.{column}: {kind}, {out['distinct']:,} distinct in {out['rows']:,} rows"]
    if out["nulls"]:
```

with

```python
    facts = [f"{table}.{column}: {kind}, {out['distinct']:,} distinct in {out['rows']:,} rows"]
    if out["distinct"] and len(values) > out["distinct"]:
        per_value = len(values) / out["distinct"]
        out["rows_per_value"] = round(per_value, 1)
        if per_value >= 1.5:
            facts.append(f"each value appears about {per_value:.0f} times")
    if out["nulls"]:
```

2. Add the constants. Replace

```python
TOOL_NAMES = ("find_columns", "inspect_column", "relationship", "preview")
```

with

```python
EXPLORER_TOOL_NAMES = ("find_columns", "inspect_column", "relationship", "preview")
GRAIN_COLUMNS = 8      # the label columns with the fewest values tried as parts of a key
GRAIN_SIZE = 3         # the most columns a key may have
GRAIN_CONFIRMS = 3     # candidate keys checked on the full table, one pass each
```

3. Add `row_grain`. Insert it directly above `def repeated_x(`:

```python
def row_grain(frame: pd.DataFrame, table: str) -> dict[str, Any]:
    """The smallest set of columns whose values identify one row, from values only.

    Searched on the profile's 2,000-row sample: first one column unique there,
    then label columns (values that repeat), fewest values first, in twos and
    threes. Each candidate is confirmed on the full table in one pass, at most
    GRAIN_CONFIRMS of them. A column with fractions is a measure and never part
    of a key, and a whole number unique by chance is not an id unless it counts
    the rows: a measure is almost all-unique by nature.
    """
    from itertools import combinations, islice
    from math import prod

    from app.services.agents.architect import spread_sample

    rows = int(len(frame))
    sample = spread_sample(frame, KIND_SAMPLE)
    n = len(sample)
    position = {column: i for i, column in enumerate(frame.columns)}
    singles: list[str] = []
    labels: dict[str, int] = {}
    for column in frame.columns:
        values = sample[column]
        if values.isna().any() or (pd.api.types.is_float_dtype(values) and not bool((values % 1 == 0).all())):
            continue
        distinct = int(values.nunique())
        if distinct == n > 1:
            singles.append(column)
        elif distinct >= 2 and distinct * 2 <= n:
            labels[column] = distinct

    def candidates():
        for column in singles:
            whole = frame[column].dropna()
            if pd.api.types.is_numeric_dtype(whole) and (
                    len(whole) != rows or int(whole.max() - whole.min()) + 1 != rows):
                continue
            yield [column]
        ordered = sorted(labels, key=lambda c: (labels[c], position[c]))[:GRAIN_COLUMNS]
        for size in range(2, GRAIN_SIZE + 1):
            for combo in sorted(combinations(ordered, size),
                                key=lambda cs: (prod(labels[c] for c in cs), [position[c] for c in cs])):
                if prod(labels[c] for c in combo) >= n and not sample.duplicated(subset=list(combo)).any():
                    yield list(combo)

    key: list[str] = []
    for candidate in islice(candidates(), GRAIN_CONFIRMS):
        if not frame.duplicated(subset=candidate).any():
            key = sorted(candidate, key=position.__getitem__)
            break
    if key:
        fact = f"{table}: one row per {' × '.join(key)} ({rows:,} rows); other columns describe the row"
    else:
        fact = f"{table}: no key found among the columns tried, alone or up to {GRAIN_SIZE} together ({rows:,} rows)"
    return {"table": table, "rows": rows, "key": key, "fact": fact}
```

4. Give `tool_specs` a `names` parameter and a `row_grain` spec. Replace its head

```python
def tool_specs(tables: list[str]) -> list[dict[str, Any]]:
    """The four tools in the OpenAI format mlx_lm server forwards to the chat template."""
    table = {"type": "string", "enum": tables}
    def spec(name: str, description: str, properties: dict, required: list[str]) -> dict:
        return {"type": "function", "function": {"name": name, "description": description, "parameters": {
            "type": "object", "properties": properties, "required": required}}}
    return [
```

with

```python
def tool_specs(tables: list[str], names: tuple[str, ...] = EXPLORER_TOOL_NAMES) -> list[dict[str, Any]]:
    """The named tools, in that order, in the OpenAI format mlx_lm server forwards to the chat template."""
    table = {"type": "string", "enum": tables}
    def spec(name: str, description: str, properties: dict, required: list[str]) -> dict:
        return {"type": "function", "function": {"name": name, "description": description, "parameters": {
            "type": "object", "properties": properties, "required": required}}}
    every = [
```

and its tail

```python
              "top_n": {"type": "integer"},
              "grain": {"type": "string", "enum": ["", *GRAIN_FREQ]}}, ["table", "x"]),
    ]
```

with

```python
              "top_n": {"type": "integer"},
              "grain": {"type": "string", "enum": ["", *GRAIN_FREQ]}}, ["table", "x"]),
        spec("row_grain", "Which columns identify one row of a table, found from the values (for example one "
             "row per weekday and hour), so you know whether x repeats before you plan a line.",
             {"table": table}, ["table"]),
    ]
    by_name = {tool["function"]["name"]: tool for tool in every}
    return [by_name[name] for name in names]
```

The four existing specs keep their text, so the explorer's prompt does not change.

5. Give `ToolBox` its tool set. In `ToolBox.__init__`, replace

```python
    def __init__(self, sources: dict[str, dict], data_dir: str, max_calls: int = MAX_CALLS,
                 loader: Callable[[dict, str], pd.DataFrame] | None = None):
        self.sources = sources
        self.data_dir = data_dir
        self.max_calls = max_calls
        self._loader = loader
```

with

```python
    def __init__(self, sources: dict[str, dict], data_dir: str, max_calls: int = MAX_CALLS,
                 loader: Callable[[dict, str], pd.DataFrame] | None = None,
                 tools: tuple[str, ...] = EXPLORER_TOOL_NAMES):
        self.sources = sources
        self.data_dir = data_dir
        self.max_calls = max_calls
        self.tools = tools
        self._loader = loader
```

In `ToolBox.specs`, replace `return tool_specs(list(self.sources))` with:

```python
        return tool_specs(list(self.sources), self.tools)
```

6. Refuse a tool that was not offered. In `ToolBox._run`, replace

```python
    def _run(self, name: str, args: dict) -> dict[str, Any]:
        if name == "find_columns":
```

with

```python
    def _run(self, name: str, args: dict) -> dict[str, Any]:
        if name not in self.tools:
            raise ValueError(f"no tool '{name}'; tools are: {', '.join(self.tools)}")
        if name == "find_columns":
```

and its last line,

```python
        raise ValueError(f"no tool '{name}'; tools are: {', '.join(TOOL_NAMES)}")
```

with

```python
        if name == "row_grain":
            return row_grain(self.frame(table), table)
        raise ValueError(f"no tool '{name}'; tools are: {', '.join(self.tools)}")
```

Check that nothing else uses the old name:

Run: `cd backend && grep -rn "TOOL_NAMES" app/ | grep -v "EXPLORER_TOOL_NAMES"`
Expected: no output.

- [ ] **Step 4: Run the tests and the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_data_tools.py tests/test_discovery.py`
Expected: all pass. `test_discovery.py` still sees exactly the explorer's four tool names.

Run: `cd backend && .venv/bin/python -m pytest -q tests`
Expected: 6 more tests than after Task 6 (164 with Task 4's fix, 162 without); the only failures are the 3 known ones.

- [ ] **Step 5: Record it in AGENTS.md**

First run `row_grain` on every CSV in `backend/uploads/` (a short loop: `pd.read_csv`, then `data_tools.row_grain(frame, name)`), and paste each printed fact into the report. The "Run on the sample files" line below is copied from that output, and nothing in angle brackets may remain.

Insert these bullets directly after the line that starts with `- Every placed chart plan is logged with all its fields`, which Task 5 added:

```markdown
- `data_tools.row_grain(table)` names, from values only, the columns that identify a row: "one row per weekday × hourOfDay (168 rows); other columns describe the row", or "no key found among the columns tried, alone or up to 3 together". The search is bounded, so "no key found" does not mean every row is unique.
  - Search: the profile's 2,000-row sample; label columns with the fewest values first; keys of up to 3 columns, from at most 8 columns.
  - Confirmation: each candidate on the full table in one pass, at most 3 candidates.
  - A column with fractions is never part of a key, and a whole number is an id only if it counts the rows.
  - Run on the sample files: <one entry per CSV in `backend/uploads/`, `file: key` or `file: no key found`, copied from the run above>.
- `inspect_column` now says how often values repeat: "each value appears about 7 times".
- The explorer keeps its four tools (`EXPLORER_TOOL_NAMES`), and a ToolBox refuses a tool it did not offer.
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/agents/data_tools.py backend/tests/test_data_tools.py AGENTS.md
git commit -m "feat(tools): row_grain names what one row is; inspect_column says how values repeat

row_grain finds the smallest set of up to 3 columns whose values identify a
row, searching the 2,000-row sample (label columns, fewest values first) and
confirming on the full table, at most 3 candidates. Values only: a measure
is never a key. Tool sets are per role now; the explorer keeps its four.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `preview_chart`, one line per draft plan, from the same function as the check

The planner's second new tool takes up to 7 draft plans and returns one line per plan, about the full data:
- points per line, and whether x repeats within a line;
- bars, slices, stages, pieces or cells, against the caps;
- the value range;
- the problem text the automatic checks would raise.

**How it is built:**
- **Rules.** When the profile's kinds are known, the plan rules come first (`planning_contract.check_spec`).
- **Shape.** Then `chart_shape` (Task 5), the function `validate_spec` calls. So a preview and the check on the final plan cannot disagree.
- **Bad drafts.** A bad draft gets its own error line. The batch costs one tool call.
- **Size.** The whole result stays under 1,200 characters, and every plan keeps its line; long lines are cut evenly, each marked with "…".

This task also adds the compact reply the planner will read in its own prompt: the fact line(s), not the JSON.

**Files:**
- Modify: `backend/app/services/agents/data_tools.py` (import `check_spec`, `_capped`, `_fit_lines`, constants, the `preview_chart` spec, `ToolBox.__init__` (`kinds`), `ToolBox.call` (`compact`), `ToolBox._run`, `ToolBox._preview_chart`, `ToolBox._preview_one`)
- Test: `backend/tests/test_data_tools.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes:
  - `chart_shape(frame, spec)` and `_plan_head(spec)` (Task 5);
  - `ToolBox(tools=...)`, `tool_specs(tables, names)` and `EXPLORER_TOOL_NAMES` (Task 7);
  - `planning_contract.check_spec(item, tables) -> (spec | None, problems)` (existing);
  - `profiler.profile_table(name, frame).kinds()` (existing).
- Produces (Task 9 relies on these):
  - `PLANNER_TOOL_NAMES = ("preview_chart", "row_grain", "inspect_column", "find_columns", "relationship")` and `MAX_PREVIEW_PLANS = 7`.
  - `ToolBox(..., tools=..., kinds: dict[str, dict[str, str]] | None = None)`. `kinds` is `columns_by_table(profiles)`; with it, `preview_chart` runs the plan rules too.
  - `ToolBox.call(name, args, compact: bool = False) -> str`. With `compact`, it returns the result's fact line(s), capped at 1,200 characters; an error is still the JSON. Every call is recorded in `ToolBox.calls` as before.
  - The `preview_chart` result is `{"fact": "<one line per plan, joined by newlines>", "plans": n}`. Each line reads `"<n>. <shape>; ok"` or `"<n>. <shape>; problem: <the check's words>"`.

The tool's schema names the plan fields in words and does not nest a schema. Measured with the base model's chat template, a nested schema cost about 175 more prompt tokens: the template prints every schema into the planner's prompt. A tool parser may hand the list over as JSON text, so a string is parsed first.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_data_tools.py`. `GRID`, `EXPLORER_TOOL_NAMES`, `RESULT_CHARS`, `ToolBox`, `toolbox` and `json` are already defined or imported there.

```python


from app.services.agents.data_tools import MAX_PREVIEW_PLANS, PLANNER_TOOL_NAMES
from app.services.agents.profiler import profile_table

RAW = {"chart": "line", "table": "web", "x": "hourOfDay", "y": "bounceRatePct", "agg": "none"}


def planner_box(**frames):
    """A ToolBox as the planner holds it: its five tools, and the profile's kinds for the plan rules."""
    return ToolBox({name: {"type": "file", "name": name} for name in frames}, "",
                   loader=lambda source, data_dir: frames[source["name"]], tools=PLANNER_TOOL_NAMES,
                   kinds={name: profile_table(name, frame).kinds() for name, frame in frames.items()})


def test_preview_chart_gives_one_line_per_plan_with_the_checks_own_words():
    box = planner_box(web=GRID)
    plans = [RAW, {**RAW, "agg": "mean"}, {**RAW, "chart": "bar", "x": "weekday", "y": "sessions", "agg": "sum"}]
    lines = box.call("preview_chart", {"plans": plans}, compact=True).splitlines()
    assert len(lines) == 3 and len(box.calls) == 1
    assert lines[0].startswith("1. line bounceRatePct by hourOfDay: 168 points per line, x repeats within a line")
    assert lines[0].endswith("; problem: " + box.validate_spec({**RAW, "title": "t"})[0])
    assert lines[1].startswith("2. line mean of bounceRatePct by hourOfDay: 24 points per line, x once per line")
    assert lines[1].endswith("; ok")
    assert lines[2].startswith("3. bar sum of sessions by weekday: 7 bars (limit 50), values ") and lines[2].endswith("; ok")


def test_a_draft_without_agg_is_previewed_as_the_check_reads_it():
    box = planner_box(web=GRID)
    draft = {key: value for key, value in RAW.items() if key != "agg"}
    line = box.call("preview_chart", {"plans": [draft]}, compact=True)
    assert "x repeats within a line" in line
    assert line.endswith("; problem: " + box.validate_spec({**draft, "title": "t"})[0])


def test_a_bad_draft_gets_its_own_line_in_the_one_call():
    box = planner_box(web=GRID)
    plans = [{"chart": "pie", "table": "web", "x": "hourOfDay", "y": "sessions", "agg": "sum"},
             {"chart": "bar", "table": "web", "x": "nope", "y": "sessions", "agg": "sum"},
             "not a plan",
             {"chart": "kpi", "table": "web", "y": "sessions", "agg": "sum"}]
    lines = box.call("preview_chart", {"plans": plans}, compact=True).splitlines()
    assert len(lines) == 4 and len(box.calls) == 1
    assert "a pie needs a category column on x" in lines[0]
    assert "'nope' is not a column of 'web'" in lines[1]
    assert lines[2] == "3. not a chart plan: give chart, table, x, y, group, agg, grain, top_n"
    assert lines[3].startswith("4. kpi sum of sessions: one number, ") and lines[3].endswith("; ok")


def test_seven_long_plans_keep_a_line_each_within_the_cap():
    reply = planner_box(web=GRID).call("preview_chart", {"plans": [RAW] * 9})
    lines = json.loads(reply)["fact"].splitlines()
    assert len(reply) <= RESULT_CHARS and len(lines) == MAX_PREVIEW_PLANS + 1
    assert all(line.endswith("…") for line in lines[:MAX_PREVIEW_PLANS])
    assert lines[-1] == "(only the first 7 of 9 plans were previewed)"


def test_a_cut_line_keeps_what_the_planner_acts_on():
    lines = ["1. line y by x: " + "s" * 300 + "; problem: set agg", "2. bar y by x: 7 bars; ok"] * 4
    text = _fit_lines(lines, limit=400)
    assert len(text) <= 400 and len(text.splitlines()) == 8
    assert all(line.endswith("; problem: set agg") or line == "2. bar y by x: 7 bars; ok"
               for line in text.splitlines())


def test_compact_replies_are_the_fact_line_and_errors_stay_json():
    box = planner_box(web=GRID)
    assert box.call("inspect_column", {"table": "web", "column": "hourOfDay"}, compact=True).startswith(
        "web.hourOfDay: number, 24 distinct in 168 rows; each value appears about 7 times")
    reply = box.call("inspect_column", {"table": "web", "column": "hour"}, compact=True)
    assert "not a column of 'web'" in json.loads(reply)["error"]


def test_the_planner_and_the_explorer_get_their_own_tools():
    assert [t["function"]["name"] for t in planner_box(web=GRID).specs] == list(PLANNER_TOOL_NAMES)
    assert [t["function"]["name"] for t in toolbox(web=GRID).specs] == list(EXPLORER_TOOL_NAMES)
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_data_tools.py`
Expected: a collection error, `ImportError: cannot import name 'MAX_PREVIEW_PLANS'`.

- [ ] **Step 3: Implement**

In `backend/app/services/agents/data_tools.py`, make these changes.

1. Import `check_spec`. Above `from app.services.agents.profiler import profile_column`, add:

```python
from app.services.agents.planning_contract import check_spec
```

`planning_contract` imports only the standard library, so this adds no cycle.

2. Add the two text helpers. Insert them directly above `def find_columns(`:

```python
def _capped(text: str, limit: int = RESULT_CHARS) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fit_lines(lines: list[str], limit: int = RESULT_CHARS - 40) -> str:
    """The lines joined; when together they would pass `limit`, every line
    stays and only the long ones are cut. Lines that fit an equal share stay
    whole, and the room they leave goes to the longer lines. A cut line keeps
    its head (up to the first ": ") and its verdict ("; ok" or "; problem: ...",
    what the planner acts on): the shape text between them is cut first, then
    the verdict's end. Each cut is marked with an ellipsis."""
    text = "\n".join(lines)
    if len(text) <= limit:
        return text
    room = limit - (len(lines) - 1)
    whole: set[int] = set()
    left = sorted(range(len(lines)), key=lambda i: len(lines[i]))
    while left and len(lines[left[0]]) <= max(40, room // len(left)):
        whole.add(left[0])
        room -= len(lines[left.pop(0)])
    share = max(40, room // len(left)) if left else 0
    return "\n".join(line if i in whole else _cut_line(line, share) for i, line in enumerate(lines))


def _cut_line(line: str, width: int) -> str:
    """`line` cut to `width`, keeping its head and its verdict when they fit."""
    if len(line) <= width:
        return line
    at = line.find("; problem: ")
    if at < 0 and line.endswith("; ok"):
        at = len(line) - len("; ok")
    colon = line.find(": ")
    head_end = colon + 1 if colon > 0 else 0
    if at <= head_end:
        return line[: width - 1] + "…"
    head, verdict = line[:head_end], line[at:]
    if len(head) + 1 + len(verdict) <= width:
        return line[: width - 1 - len(verdict)] + "…" + verdict
    return (head + "…" + verdict)[: width - 1] + "…"
```

3. Add the constants. Directly after `GRAIN_CONFIRMS = 3     # candidate keys checked on the full table, one pass each`, add:

```python
MAX_PREVIEW_PLANS = 7  # draft plans one preview_chart call may hold
PLANNER_TOOL_NAMES = ("preview_chart", "row_grain", "inspect_column", "find_columns", "relationship")
```

4. Add the `preview_chart` spec. In `tool_specs`, replace

```python
        spec("row_grain", "Which columns identify one row of a table, found from the values (for example one "
             "row per weekday and hour), so you know whether x repeats before you plan a line.",
             {"table": table}, ["table"]),
    ]
```

with

```python
        spec("row_grain", "Which columns identify one row of a table, found from the values (for example one "
             "row per weekday and hour), so you know whether x repeats before you plan a line.",
             {"table": table}, ["table"]),
        # Plan fields are named in words, not as a nested schema: the chat template
        # prints every schema into the planner's prompt, and a nested one cost ~175 tokens more.
        spec("preview_chart", "What up to 7 draft chart plans would draw on the full data, one line per plan: "
             "points per line and whether x repeats, bars, slices or cells against the limits, the value "
             "range, and any problem the plan check will raise. Each plan has chart, table, x, y, group, "
             "agg, grain and top_n, as in your reply.",
             {"plans": {"type": "array", "items": {"type": "object"}}}, ["plans"]),
    ]
```

5. Give `ToolBox` the kinds. In `ToolBox.__init__`, replace

```python
                 tools: tuple[str, ...] = EXPLORER_TOOL_NAMES):
        self.sources = sources
        self.data_dir = data_dir
        self.max_calls = max_calls
        self.tools = tools
```

with

```python
                 tools: tuple[str, ...] = EXPLORER_TOOL_NAMES,
                 kinds: dict[str, dict[str, str]] | None = None):
        self.sources = sources
        self.data_dir = data_dir
        self.max_calls = max_calls
        self.tools = tools
        self.kinds = kinds  # the profile's column kinds by table, so preview_chart runs the plan rules too
```

6. Add the compact reply to `call`. Replace

```python
    def call(self, name: str, args: dict | None) -> str:
        if self.exhausted:
```

with

```python
    def call(self, name: str, args: dict | None, compact: bool = False) -> str:
        """Run one tool and record it. The reply is the result as compact JSON or,
        with `compact`, its fact line(s) alone: what the planner reads inside its
        own prompt. An error is always the JSON."""
        if self.exhausted:
```

and replace

```python
        text = bounded(result)
        self.calls.append(ToolCall(name, args, text, str(result.get("fact", ""))))
        return text
```

with

```python
        text = bounded(result)
        call = ToolCall(name, args, text, str(result.get("fact", "")))
        self.calls.append(call)
        return _capped(call.fact) if compact and call.fact else text
```

7. Route the tool in `_run`. Replace

```python
        if name == "row_grain":
            return row_grain(self.frame(table), table)
        raise ValueError(f"no tool '{name}'; tools are: {', '.join(self.tools)}")
```

with

```python
        if name == "row_grain":
            return row_grain(self.frame(table), table)
        if name == "preview_chart":
            return self._preview_chart(args.get("plans"))
        raise ValueError(f"no tool '{name}'; tools are: {', '.join(self.tools)}")
```

8. Add the preview methods. Insert these two methods directly above `def facts(self)`:

```python
    def _preview_chart(self, plans: Any) -> dict[str, Any]:
        """Each draft plan's shape on the full data, one line per plan, in one call."""
        if isinstance(plans, str):  # a tool parser may hand the list over as its JSON text
            try:
                plans = json.loads(plans)
            except json.JSONDecodeError:
                pass
        if not isinstance(plans, list) or not plans:
            raise ValueError("give plans: a list of draft chart plans, each with chart, table, x, y, group, agg, "
                             "grain, top_n")
        lines = [f"{n}. {self._preview_one(plan)}" for n, plan in enumerate(plans[:MAX_PREVIEW_PLANS], 1)]
        if len(plans) > MAX_PREVIEW_PLANS:
            lines.append(f"(only the first {MAX_PREVIEW_PLANS} of {len(plans)} plans were previewed)")
        return {"fact": _fit_lines(lines), "plans": min(len(plans), MAX_PREVIEW_PLANS)}

    def _preview_one(self, plan: Any) -> str:
        """One draft plan in one line: the plan rules first (when the kinds are known),
        then chart_shape, the same function the check on the final plan runs."""
        if not isinstance(plan, dict):
            return "not a chart plan: give chart, table, x, y, group, agg, grain, top_n"
        # A missing agg reads as "none", as check_spec reads it, so the preview and the check agree.
        draft = {"title": "draft", "question": "", "x": "", "y": "", "group": "", "agg": "none", "grain": "",
                 "sort": "", "top_n": 0, **plan}
        try:
            table = str(draft.get("table") or "")
            frame = self._with(table, *(str(draft.get(key) or "") for key in ("x", "y", "group")))
            spec = draft
            if self.kinds is not None:
                spec, rules = check_spec(draft, self.kinds)
                if spec is None:
                    return f"{_plan_head(draft)}: problem: {'; '.join(rules)}"
            shape, problems = chart_shape(frame, spec)
        except (KeyError, ValueError, TypeError) as exc:
            return f"{_plan_head(draft)}: problem: {exc.args[0] if exc.args else exc}"
        except Exception as exc:  # noqa: BLE001 - one draft that cannot be previewed must not cost the others
            logger.warning("[tools] could not preview %s: %s", draft, exc)
            return f"{_plan_head(draft)}: problem: it could not be previewed ({exc})"
        return f"{shape}; problem: {'; '.join(problems)}" if problems else f"{shape}; ok"
```

Columns are checked first by `_with`. Its message is short ("'nope' is not a column of 'web'; columns like it: ..."), where `check_spec`'s lists every column of the table.

Here is a realistic result, from the web-traffic sample (`make sample-data`):

```
1. line bounceRatePct by hourOfDay: 168 points per line, x repeats within a line, values 28.4 to 70.8; problem: x 'hourOfDay' has 24 values over 168 rows (each appears 7 times), so one line would run back and forth: set agg (mean for rates, sum for totals) or a group
2. line mean of bounceRatePct by hourOfDay: 24 points per line, x once per line, values 39.8 to 58.6; ok
3. kpi sum of sessions: one number, 81,200; ok
4. pie sum of sessions by deviceClass: 3 slices (limit 12), values 20,100 to 40,300; ok
```

- [ ] **Step 4: Run the tests and the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_data_tools.py tests/test_discovery.py tests/test_dashboard_flow.py`
Expected: all pass.

Run: `cd backend && .venv/bin/python -m pytest -q tests`
Expected: 6 more tests than after Task 7 (170 with Task 4's fix, 168 without); the only failures are the 3 known ones.

- [ ] **Step 5: Record it in AGENTS.md**

Insert this bullet directly after the line that starts with `- The explorer keeps its four tools`, which Task 7 added:

```markdown
- `preview_chart(plans)` previews up to 7 draft plans in one call, one line per plan.
  - Each line gives points per line and whether x repeats; bars, slices or cells against the limits; the value range; and the problem the checks would raise.
  - The plan rules come first (`check_spec`, with the profile's kinds), then `data_tools.chart_shape`, the function `validate_spec` calls. So a preview and the final check cannot disagree.
  - A bad draft gets its own line. The result stays under 1,200 characters, with every plan keeping a line.
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/agents/data_tools.py backend/tests/test_data_tools.py AGENTS.md
git commit -m "feat(tools): preview_chart, one line per draft plan from the check's own function

Up to 7 drafts per call: shape on the full data (points per line and whether
x repeats, bars/slices/cells against the caps, value range) and the problem
the checks would raise, from check_spec and chart_shape, so the preview and
the final check cannot disagree. Compact replies carry the fact lines only.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: `PLANNER_TOOLS=planner`: the planner holds the tools itself

With `on` (today's default), an explorer call checks up to 3 facts before planning, and the planner only reads a facts note. With the new value `planner`:
- there is no explorer step;
- the planner call gets the five tools bound (`preview_chart`, `row_grain`, `inspect_column`, `find_columns`, `relationship`);
- on its first try it may call them, at most 3 times;
- it then answers in the same JSON, which the same checks read, with the same retries.

The trained `PLANNER_SYSTEM_PROMPT` is untouched. The tool instructions are an appended user-message section, and the chat template adds the tool list to the system turn, as it does for the explorer. A tool or backend failure plans without tools, never fails a build. `on` stays the default until Task 10's measurement decides.

**Design decisions:**
- **Fact lines only.** Each tool result in the planner's prompt is the compact fact line(s), not the JSON. Measured with the base model's chat template on the Spotify table (23 columns, 7 directions), the planner prompt is:
  - 1,407 tokens without tools;
  - 2,262 tokens with the five tools and the note bound, before any call;
  - 2,937 tokens after three calls.

  lora-v2 was trained at 2,048. A size test pins what the tools add.
- **First try only.** Tools are offered on the first try only. A retry is a plain call with the check's words, as the planner was trained. The whole transcript is kept, so the retry still sees what the tools said.
- **Answering after the budget.** When the model stops calling, that reply is its answer. When the 3-call budget runs out while it is still calling, the unbound model is asked once for the answer. So an empty, tool-only reply never reaches the check and costs a retry.
- **Unbound calls after tool turns.** That unbound call (and a retry after a tool was used) sends the tool-call and tool-result turns without `tools`. If the server refuses that, the same call is made once more without the tool turns. `backend/scripts/probe_planner_tools.py` (Step 12) checks on the real server which of the two happens.
- **Status lines.** The planner's tool calls appear as status lines ("Checking the data: previewing 3 draft plans"), through the same `_with_retry_status` that announces retries.

**Files:**
- Modify: `backend/app/services/agents/planning_contract.py` (add `PLANNER_TOOLS_NOTE`)
- Modify: `backend/app/services/agents/discovery.py` (extract `run_tools`; `discover` uses it)
- Modify: `backend/app/services/agents/planning.py` (`Ask`, `run_checked(ask=)`, `_tool_asker`, `plan_charts_steps(toolbox=)`, `plan_charts(toolbox=)`)
- Modify: `backend/app/services/agents/dashboard_flow.py` (`build_dashboard(planner_tools=)`, status lines)
- Modify: `backend/app/api/v1/endpoints/blocks.py` (`PLANNER_TOOLS_MODES`, `_planner_tools_mode`)
- Modify: `backend/app/core/config.py` (the comment on `PLANNER_TOOLS`), `docker-compose.yml` (api env)
- Create: `backend/scripts/probe_planner_tools.py`
- Test: create `backend/tests/test_planner_tools.py`; extend `backend/tests/test_dashboard_endpoint.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes:
  - `ToolBox(..., tools=PLANNER_TOOL_NAMES, kinds=...)`, `ToolBox.call(name, args, compact=True)` and `PLANNER_TOOL_NAMES` (Tasks 7–8);
  - `run_checked(..., rank=)`, `by_size` and `with_context(..., notes=)` (Task 2);
  - `Probe(name, args)` (`discovery.py`, existing);
  - from `backend/tests/test_dashboard_endpoint.py` (Task 2): `_wire(monkeypatch, seen)`, `_start(payload)`, `NoDb`, `SOURCE` and `DashboardBriefRequest`.
- Produces (Task 10 relies on these):
  - `planning_contract.PLANNER_TOOLS_NOTE: str`.
  - `discovery.run_tools(bound, messages: list, toolbox, compact: bool = False) -> Generator[Probe, None, reply | None]`. It appends each turn to `messages`, charges every call, and raises if a model call fails.
  - `planning.Ask = Callable[[list, int], Generator[Probe, None, str]]`, and `run_checked(..., ask: Ask | None = None)`, which yields `Retry | Probe`.
  - `plan_charts_steps(..., toolbox=None)` and `plan_charts(..., toolbox=None)`. A ToolBox makes the planner hold its tools.
  - `build_dashboard(..., planner_tools: bool = False)`. When true, the explorer is not used even if `explorer_llm` is given.
  - `blocks._planner_tools_mode() -> "on" | "planner" | "off"`. It raises HTTP 500 for any other value.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_planner_tools.py`:

```python
"""PLANNER_TOOLS=planner: the planner checks its own drafts with tools, at most
3 calls on its first try, then answers in JSON that the usual checks read."""
import json

import pandas as pd
from langchain_core.messages import AIMessage, ToolMessage

from app.services.agents.chartist import ChartistAgent
from app.services.agents.dashboard_flow import build_dashboard
from app.services.agents.data_tools import PLANNER_TOOL_NAMES, ToolBox, tool_specs
from app.services.agents.planning import plan_charts
from app.services.agents.planning_contract import PLANNER_TOOLS_NOTE
from app.services.agents.profiler import profile_table

WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOURS = pd.DataFrame({"weekday": [day for day in WEEK for _ in range(24)], "hourOfDay": list(range(24)) * 7,
                      "bounceRatePct": [30.5 + (i * 7) % 40 for i in range(168)]})
PROFILES = [profile_table("web", HOURS)]
DIRECTION = [{"question": "How does the bounce rate move through the day?", "why": "asked", "table": "web",
              "columns": ["hourOfDay", "bounceRatePct"]}]
PLAN = {"title": "Bounce rate by hour", "question": "How does the bounce rate move through the day?",
        "chart": "line", "table": "web", "x": "hourOfDay", "y": "bounceRatePct", "group": "", "agg": "mean",
        "grain": "", "sort": "", "top_n": 0}
ANSWER = AIMessage(content=json.dumps({"charts": [PLAN]}))
RAW_ANSWER = AIMessage(content=json.dumps({"charts": [{**PLAN, "agg": "none"}]}))


class ToolPlanner:
    """A stand-in planner model. Bound (tools offered) and plain calls read one
    script in order; each call is recorded with which of the two it was."""

    def __init__(self, *replies, bind_fails=False):
        self.replies, self.seen, self.bind_fails, self.specs = list(replies), [], bind_fails, None

    def bind_tools(self, specs):
        if self.bind_fails:
            raise NotImplementedError("this backend has no tools")
        self.specs = specs
        return Bound(self)

    def reply(self, kind, messages):
        self.seen.append((kind, list(messages)))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def invoke(self, messages):
        return self.reply("plain", messages)


class Bound:
    def __init__(self, planner):
        self.planner = planner

    def invoke(self, messages):
        return self.planner.reply("bound", messages)


def calls(*items):
    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"c{i}"} for i, (n, a) in enumerate(items)])


def box():
    return ToolBox({"web": {"type": "file", "name": "web"}}, "", loader=lambda source, data_dir: HOURS,
                   tools=PLANNER_TOOL_NAMES, kinds={"web": PROFILES[0].kinds()})


def plan(model, toolbox):
    return plan_charts(model, DIRECTION, PROFILES, validate=toolbox.validate_spec, toolbox=toolbox)


PREVIEW = ("preview_chart", {"plans": [{"chart": "line", "table": "web", "x": "hourOfDay", "y": "bounceRatePct",
                                        "agg": "none"}]})


def test_the_planner_previews_its_draft_then_answers():
    model, toolbox = ToolPlanner(calls(PREVIEW), ANSWER), box()
    step = plan(model, toolbox)
    assert step.errors == [] and step.items[0]["agg"] == "mean" and step.attempts == 1
    assert [kind for kind, _ in model.seen] == ["bound", "bound"]
    assert [t["function"]["name"] for t in model.specs] == list(PLANNER_TOOL_NAMES)
    first, second = model.seen[0][1], model.seen[1][1]
    assert first[1].content.endswith(PLANNER_TOOLS_NOTE)
    result = second[-1]
    assert isinstance(result, ToolMessage) and result.content.startswith("1. line bounceRatePct by hourOfDay:")
    assert "x repeats within a line" in result.content and not result.content.startswith("{")


def test_several_calls_in_one_reply_are_each_answered_and_charged():
    model, toolbox = ToolPlanner(calls(("row_grain", {"table": "web"}),
                                       ("inspect_column", {"table": "web", "column": "hourOfDay"})), ANSWER), box()
    plan(model, toolbox)
    assert [c.name for c in toolbox.calls] == ["row_grain", "inspect_column"]
    results = [m for m in model.seen[1][1] if isinstance(m, ToolMessage)]
    assert results[0].content.startswith("web: one row per weekday × hourOfDay")


def test_a_planner_that_keeps_calling_is_answered_by_the_plain_model_after_three():
    model = ToolPlanner(calls(("row_grain", {"table": "web"})), calls(PREVIEW),
                        calls(("inspect_column", {"table": "web", "column": "weekday"})), ANSWER)
    toolbox = box()
    step = plan(model, toolbox)
    assert len(toolbox.calls) == 3 and [kind for kind, _ in model.seen] == ["bound", "bound", "bound", "plain"]
    assert step.items and step.errors == []


def test_a_planner_that_calls_no_tool_answers_on_its_first_reply():
    model, toolbox = ToolPlanner(ANSWER), box()
    step = plan(model, toolbox)
    assert step.items and toolbox.calls == [] and [kind for kind, _ in model.seen] == ["bound"]


def test_a_retry_is_a_plain_call_with_the_checks_words():
    model, toolbox = ToolPlanner(RAW_ANSWER, ANSWER), box()
    step = plan(model, toolbox)
    assert step.attempts == 2 and step.items[0]["agg"] == "mean"
    assert [kind for kind, _ in model.seen] == ["bound", "plain"]
    assert "run back and forth" in model.seen[1][1][-1].content


def test_without_tool_support_the_planner_plans_without_them():
    model, toolbox = ToolPlanner(ANSWER, bind_fails=True), box()
    step = plan(model, toolbox)
    assert step.items and toolbox.calls == []
    assert PLANNER_TOOLS_NOTE not in model.seen[0][1][1].content


def test_a_tool_step_that_fails_plans_without_it():
    model, toolbox = ToolPlanner(ConnectionError("tools rejected"), ANSWER), box()
    step = plan(model, toolbox)
    assert step.items and [kind for kind, _ in model.seen] == ["bound", "plain"]


class Fixed:
    def invoke(self, variables):
        return ("import plotly.express as px\n"
                "d = df.groupby('hourOfDay', as_index=False)['bounceRatePct'].mean()\n"
                "fig = px.line(d, x='hourOfDay', y='bounceRatePct')\n"
                "print(fig.to_json())\n")


class Scripted:
    def __init__(self, *replies):
        self.replies = list(replies)

    def invoke(self, messages):
        return type("Reply", (), {"content": self.replies.pop(0)})()


def test_a_dashboard_with_planner_tools_has_no_explorer_step(tmp_path):
    path = tmp_path / "web.csv"
    HOURS.to_csv(path, index=False)
    directions = json.dumps({"directions": [{**DIRECTION[0], "table": "web.csv"}]})
    preview = ("preview_chart", {"plans": [{"chart": "line", "table": "web.csv", "x": "hourOfDay",
                                            "y": "bounceRatePct", "agg": "mean"}]})
    planner = ToolPlanner(calls(preview), AIMessage(content=json.dumps({"charts": [{**PLAN, "table": "web.csv"}]})))
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("bounce rate by hour", [{"type": "file", "name": "web.csv", "path": str(path)}],
                                  str(tmp_path), Scripted(directions), planner, chartist, planner_tools=True))
    labels = [e.data["label"] for e in events if e.kind == "status"]
    assert "Checking the data" not in labels and "Checking the data: previewing 1 draft plan" in labels
    assert [e.kind for e in events][-1] == "chart"


def test_what_the_planner_tools_add_to_the_prompt_is_capped_in_characters():
    # A character cap standing in for tokens. Measured with the base model's chat template while
    # this plan was written (2026-11-23): binding these five tools and this note adds ~850 tokens
    # to the planner's prompt (Spotify table: 1,407 -> 2,262), and three compact results ~675 more
    # (2,937); lora-v2 was trained at 2,048. The probe script prints the server's own counts.
    specs = json.dumps(tool_specs(["t"], PLANNER_TOOL_NAMES), separators=(",", ":"))
    assert len(specs) <= 2000 and len(PLANNER_TOOLS_NOTE) <= 450


class PickyPlanner(ToolPlanner):
    """A server that refuses tool turns when no tools are offered (the plain call)."""

    def invoke(self, messages):
        if any(isinstance(m, ToolMessage) for m in messages):
            self.seen.append(("plain refused", list(messages)))
            raise ValueError("tool messages need tools")
        return self.reply("plain", messages)


def test_a_server_that_refuses_tool_turns_unbound_still_gets_an_answer():
    model = PickyPlanner(calls(("row_grain", {"table": "web"})), calls(PREVIEW),
                         calls(("inspect_column", {"table": "web", "column": "weekday"})), ANSWER)
    step = plan(model, box())
    assert step.items and step.errors == []
    assert [kind for kind, _ in model.seen][-2:] == ["plain refused", "plain"]
    assert not any(isinstance(m, ToolMessage) for m in model.seen[-1][1])
```

Append to `backend/tests/test_dashboard_endpoint.py`:

```python


import pytest
from fastapi import HTTPException


def test_planner_mode_gives_the_planner_the_tools_and_no_explorer(monkeypatch):
    seen = {}
    _wire(monkeypatch, seen)
    monkeypatch.setattr(blocks.settings, "PLANNER_TOOLS", "planner")
    _start(DashboardBriefRequest(brief="bounce rate by hour"))
    assert seen["planner_tools"] is True and seen["explorer_llm"] is None


def test_on_mode_keeps_the_explorer(monkeypatch):
    seen = {}
    _wire(monkeypatch, seen)
    monkeypatch.setattr(blocks.settings, "PLANNER_TOOLS", "on")
    _start(DashboardBriefRequest(brief=""))
    assert seen["planner_tools"] is False and seen["explorer_llm"] == "explorer"


def test_an_unknown_tools_mode_is_refused_before_anything_runs(monkeypatch):
    seen = {}
    _wire(monkeypatch, seen)
    monkeypatch.setattr(blocks.settings, "PLANNER_TOOLS", "sometimes")
    with pytest.raises(HTTPException) as refused:
        _start(DashboardBriefRequest(brief=""))
    assert refused.value.status_code == 500 and "PLANNER_TOOLS" in refused.value.detail and seen == {}
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_planner_tools.py tests/test_dashboard_endpoint.py`
Expected:
- `test_planner_tools.py` errors at collection with `ImportError: cannot import name 'PLANNER_TOOLS_NOTE'`;
- in `test_dashboard_endpoint.py`, two tests fail with `KeyError: 'planner_tools'`, and the unknown-mode test fails with `DID NOT RAISE`;
- the Task 2 endpoint test still passes.

- [ ] **Step 3: Add the note** (`planning_contract.py`)

Directly after `FACTS_HEADER = "Facts checked on the full data:"`, add:

```python

# Appended to the planner's message when it holds the tools itself
# (PLANNER_TOOLS=planner). The trained system prompt stays as it is; this asks
# in words, because the adapter calls tools only when asked (measured 2026-11-23).
PLANNER_TOOLS_NOTE = """Before you reply, you may check your draft plans on the full data, with at most 3 tool calls, one at a time:
- preview_chart: what up to 7 draft plans would draw (points per line and whether x repeats, bars, slices or cells, the value range, and any problem the checks would raise),
- row_grain: which columns identify one row of a table,
- inspect_column, find_columns, relationship: facts about columns.
Then reply with the JSON only."""
```

- [ ] **Step 4: Share the tool loop** (`discovery.py`)

Replace the whole of `discover` with `run_tools` and a `discover` that uses it:

```python
def run_tools(bound: Any, messages: list, toolbox: ToolBox, compact: bool = False) -> Generator[Probe, None, Any]:
    """The tool loop, shared by the explorer and the planner: the model calls
    tools until it answers without one or the budget is used. Each turn is
    appended to `messages`; every call is charged, and a call past the budget
    gets an error result instead. Returns the model's last reply (None when the
    budget was used before it was asked). A failed model call raises."""
    reply = None
    while not toolbox.exhausted:
        reply = bound.invoke(messages)
        requested = list(getattr(reply, "tool_calls", None) or [])
        if not requested:
            return reply
        messages.append(reply)
        for call in requested:
            name, args, call_id = str(call.get("name", "")), dict(call.get("args") or {}), call.get("id") or ""
            if toolbox.exhausted:
                messages.append(ToolMessage(content='{"error":"tool budget used up"}', tool_call_id=call_id))
                continue
            yield Probe(name, args)
            messages.append(ToolMessage(content=toolbox.call(name, args, compact=compact), tool_call_id=call_id))
    return reply


def discover(llm: Any, request: str, profiles: list[TableProfile], toolbox: ToolBox) -> Generator[Probe, None, Findings]:
    """Let the model call tools, at most toolbox.max_calls times; return what it found."""
    try:
        bound = llm.bind_tools(toolbox.specs)
    except Exception as exc:  # noqa: BLE001 - no tools on this backend: plan without facts
        logger.warning("[discovery] tools unavailable: %s", exc)
        return Findings()
    messages: list = [
        SystemMessage(content=EXPLORER_SYSTEM_PROMPT),
        HumanMessage(content=EXPLORER_USER_TEMPLATE.format(
            request=(request or "").strip() or NO_REQUEST, profiles=render_profiles(profiles))),
    ]
    try:
        yield from run_tools(bound, messages, toolbox)
    except Exception as exc:  # noqa: BLE001 - a failed step never fails the build
        logger.warning("[discovery] model call failed: %s", exc)
    findings = Findings(facts=toolbox.facts(), calls=list(toolbox.calls))
    logger.info("[discovery] %d tool call(s): %s", len(findings.calls),
                "; ".join(f"{c.name}({c.args})" for c in findings.calls))
    return findings
```

The explorer behaves exactly as before: same budget, same error results past the budget, and a failed model call still ends the step quietly.

- [ ] **Step 5: Let the planner hold the tools** (`planning.py`)

1. Add imports. Replace `from langchain_core.messages import AIMessage, HumanMessage, SystemMessage` with:

```python
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
```

Then replace

```python
from app.services.agents.chart_kinds import include_kinds
from app.services.agents.planning_contract import (
```

with

```python
from app.services.agents.chart_kinds import include_kinds
from app.services.agents.discovery import Probe, run_tools
from app.services.agents.planning_contract import (
```

and add `PLANNER_TOOLS_NOTE,` to that import list, directly after `PLANNER_SYSTEM_PROMPT,`.

2. Add the `Ask` type. Directly after the line `Rank = Callable[[list[dict], list[str]], tuple]`, add:

```python
# How one try is answered when it is more than one model call (the planner with
# tools): given the messages and the try number, yields tool calls, returns the reply text.
Ask = Callable[[list, int], Generator[Probe, None, str]]
```

3. Give `run_checked` its `ask` parameter. Replace

```python
    rank: Rank = by_size,
) -> Generator[Retry, None, PlanStep]:
    """Call, check, and send problems back; yields a Retry before each retry, returns the PlanStep.
    The attempt kept is the one `rank` puts highest."""
```

with

```python
    rank: Rank = by_size,
    ask: Ask | None = None,
) -> Generator[Retry | Probe, None, PlanStep]:
    """Call, check, and send problems back; yields a Retry before each retry (and
    a Probe for each tool call, when `ask` makes them), returns the PlanStep.
    The attempt kept is the one `rank` puts highest."""
```

and replace

```python
        try:
            raw = _text(llm.invoke(messages))
```

with

```python
        try:
            raw = _text(llm.invoke(messages)) if ask is None else (yield from ask(messages, attempt))
```

4. Retype `finish`. Replace `def finish(steps: Generator[Retry, None, PlanStep]) -> PlanStep:` with:

```python
def finish(steps: Generator[Retry | Probe, None, PlanStep]) -> PlanStep:
```

5. Add `_tool_asker`. Insert this function directly above `def plan_charts_steps(`:

```python
def _tool_asker(llm: Any, toolbox: Any) -> Ask | None:
    """How the planner answers when it holds the tools. On its first try it may
    call them (at most toolbox.max_calls, each result its compact fact line);
    when it stops, that reply is its answer, and when the budget runs out the
    plain model answers. A retry is a plain call, as the planner was trained.
    Tools that fail mean planning without them, never a failed build."""
    try:
        bound = llm.bind_tools(toolbox.specs)
    except Exception as exc:  # noqa: BLE001 - no tools on this backend: plan without them
        logger.warning("[planning] planner tools unavailable, planning without them: %s", exc)
        return None

    def answer(messages: list) -> Any:
        """The plain model's reply. A server that will not take tool turns without
        tools offered gets the same messages without them."""
        try:
            return llm.invoke(messages)
        except Exception as exc:  # noqa: BLE001 - retried once below, without the tool turns
            plain = [m for m in messages if not isinstance(m, ToolMessage) and not getattr(m, "tool_calls", None)]
            if len(plain) == len(messages):
                raise
            logger.warning("[planning] answering with the tool turns failed, answering without them: %s", exc)
            return llm.invoke(plain)

    def ask(messages: list, attempt: int) -> Generator[Probe, None, str]:
        reply = None
        if attempt == 1:
            try:
                reply = yield from run_tools(bound, messages, toolbox, compact=True)
            except Exception as exc:  # noqa: BLE001 - the tool step failed: answer without it
                logger.warning("[planning] planner tool step failed, planning without it: %s", exc)
        if reply is None or getattr(reply, "tool_calls", None):
            reply = answer(messages)
        return _text(reply)

    return ask
```

A plain call that fails with no tool turns in its messages still raises, as before: `run_checked` reports a dead model as an error, not a 500.

6. Give `plan_charts_steps` a `toolbox`. Replace its signature tail and the start of its body,

```python
    required_kinds: tuple[str, ...] = (),
) -> Generator[Retry, None, PlanStep]:
    kinds = tuple(required_kinds)
    user = with_context(
        PLANNER_USER_TEMPLATE.format(profiles=render_profiles(profiles), directions=render_directions(directions)),
        facts,
        links=links,
        notes=(include_kinds(kinds),),
    )
```

with

```python
    required_kinds: tuple[str, ...] = (),
    toolbox: Any = None,
) -> Generator[Retry | Probe, None, PlanStep]:
    kinds = tuple(required_kinds)
    ask = _tool_asker(llm, toolbox) if toolbox is not None else None
    user = with_context(
        PLANNER_USER_TEMPLATE.format(profiles=render_profiles(profiles), directions=render_directions(directions)),
        facts,
        links=links,
        notes=(include_kinds(kinds), PLANNER_TOOLS_NOTE if ask is not None else ""),
    )
```

and its last line,

```python
    return run_checked(llm, PLANNER_SYSTEM_PROMPT, user, check, columns_by_table(profiles), "planner", rank=rank)
```

with

```python
    return run_checked(llm, PLANNER_SYSTEM_PROMPT, user, check, columns_by_table(profiles), "planner",
                       rank=rank, ask=ask)
```

7. Give `plan_charts` a `toolbox`. Replace its signature tail and body,

```python
    required_kinds: tuple[str, ...] = (),
) -> PlanStep:
    return finish(plan_charts_steps(llm, directions, profiles, facts, validate, links, required_kinds))
```

with

```python
    required_kinds: tuple[str, ...] = (),
    toolbox: Any = None,
) -> PlanStep:
    return finish(plan_charts_steps(llm, directions, profiles, facts, validate, links, required_kinds, toolbox))
```

`planning.py` now imports `discovery.py`, which imports `data_tools`, `planning_contract` and `profiler`. None of them imports `planning`, so there is no cycle.

- [ ] **Step 6: Wire the mode through the build** (`dashboard_flow.py`)

1. Update the imports. Replace `from app.services.agents.data_tools import ToolBox` with:

```python
from app.services.agents.data_tools import PLANNER_TOOL_NAMES, ToolBox
```

and `from app.services.agents.profiler import TableProfile, profile_table` with:

```python
from app.services.agents.profiler import TableProfile, columns_by_table, profile_table
```

2. Turn the planner's tool calls into status lines. Replace `_with_retry_status` with:

```python
def _with_retry_status(steps: Generator[Retry | Probe, None, PlanStep], label: str) -> Generator[Event, None, PlanStep]:
    """Run one checked planning call, turning each retry, and each tool call the
    planner makes, into a status line; returns its PlanStep."""
    while True:
        try:
            step = next(steps)
        except StopIteration as done:
            return done.value
        if isinstance(step, Probe):
            yield Event("status", {"label": f"Checking the data: {_probe_words(step)}"})
        else:
            yield Event("status", {"label": f"{label}, try {step.attempt} of {step.of}"})
```

3. Word the two new tools. In `_probe_words`, directly after the `relationship` branch, add:

```python
    if probe.name == "row_grain":
        return f"what one row of {args.get('table', 'the table')} is"
    if probe.name == "preview_chart":
        plans = args.get("plans")
        count = len(plans) if isinstance(plans, list) else 0
        return f"previewing {count} draft plan{'' if count == 1 else 's'}"
```

4. Add the `planner_tools` parameter. In `build_dashboard`'s signature, replace

```python
    required_kinds: tuple[str, ...] = (),
) -> Iterator[Event]:
```

with

```python
    required_kinds: tuple[str, ...] = (),
    planner_tools: bool = False,
) -> Iterator[Event]:
```

5. Build the planner's ToolBox instead of the explorer step. Replace

```python
    facts, validate = "", None
    if explorer_llm is not None:
```

with

```python
    facts, validate, planner_box = "", None, None
    if planner_tools:
        # PLANNER_TOOLS=planner: the planner holds the tools itself, so there is no explorer step.
        planner_box = ToolBox({entry.label: entry.source for entry in tables}, data_dir,
                              tools=PLANNER_TOOL_NAMES, kinds=columns_by_table(profiles))
        validate = planner_box.validate_spec
    elif explorer_llm is not None:
```

The explorer branch's body stays as it is.

6. Pass the ToolBox to the planner, and log its calls. Replace

```python
        plan_charts_steps(planner_llm, directions.items, profiles, facts, validate, links=links,
                           required_kinds=required_kinds), planning
    )
```

with

```python
        plan_charts_steps(planner_llm, directions.items, profiles, facts, validate, links=links,
                           required_kinds=required_kinds, toolbox=planner_box), planning
    )
    if planner_box is not None:
        logger.info("[dashboard] planner tool calls (%d): %s", len(planner_box.calls),
                    "; ".join(f"{call.name}({call.args})" for call in planner_box.calls))
```

- [ ] **Step 7: Read the mode at the API** (`blocks.py`)

1. Add the mode reader. Insert directly above `def _sse(`:

```python
# "on": an explorer step checks facts first; "planner": the planner holds the
# tools itself; "off": no tools and no data check. See config.PLANNER_TOOLS.
PLANNER_TOOLS_MODES = ("on", "planner", "off")


def _planner_tools_mode() -> str:
    mode = (settings.PLANNER_TOOLS or "off").strip().lower()
    if mode not in PLANNER_TOOLS_MODES:
        raise HTTPException(status_code=500, detail=f"PLANNER_TOOLS must be 'on', 'planner' or 'off', got {mode!r}")
    return mode


```

2. Refuse a bad setting before anything is recorded. In `generate_whole_dashboard`, replace

```python
    memory = _report_memory(db, report.id)  # before this request is recorded: it is the brief, not history
```

with

```python
    _planner_tools_mode()  # a bad setting is a 500 before anything is recorded
    memory = _report_memory(db, report.id)  # before this request is recorded: it is the brief, not history
```

3. Use the mode in `_ai_dashboard`. Replace

```python
    tools_on = (settings.PLANNER_TOOLS or "off").strip().lower() == "on"
```

with

```python
    mode = _planner_tools_mode()
```

and replace

```python
        explorer_llm=get_llm("explorer") if tools_on else None,
        memory=memory,
        required_kinds=tuple(chart_kinds or ()),
    )
```

with

```python
        explorer_llm=get_llm("explorer") if mode == "on" else None,
        memory=memory,
        required_kinds=tuple(chart_kinds or ()),
        planner_tools=mode == "planner",
    )
```

Before this, an unknown value silently meant off (final review, Minor 6).

- [ ] **Step 8: Document the setting and pass it through compose**

In `backend/app/core/config.py`, replace the comment above `PLANNER_TOOLS: str = "on"`:

```python
    # "on": before a dashboard is planned, the model checks facts about the data
    # with bounded tools (agents/data_tools.py, agents/discovery.py) and every
    # final chart plan is checked against the real data. "on" by the no-harm rule
    # on the first 40 frozen planning rows (chartist-finetune/measure_planning_tools.py,
    # AGENTS.md); "off" rolls back.
```

with

```python
    # "on": before a dashboard is planned, an explorer call checks facts about the
    # data with bounded tools (agents/data_tools.py, agents/discovery.py), and
    # every final chart plan is checked against the real data. "planner": no
    # explorer; the planner itself may call preview_chart, row_grain,
    # inspect_column, find_columns and relationship (at most 3 calls) before its
    # JSON, and the same data check runs. "off": neither. "on" by the no-harm
    # rule on the first 40 frozen planning rows (chartist-finetune/measure_planning_tools.py,
    # AGENTS.md); docker compose passes it through as ${PLANNER_TOOLS:-on}.
```

In `docker-compose.yml`, under the api service's `environment:`, replace

```yaml
      WORKFLOW_TIMEOUT_SECONDS: ${WORKFLOW_TIMEOUT_SECONDS:-0}
```

with

```yaml
      WORKFLOW_TIMEOUT_SECONDS: ${WORKFLOW_TIMEOUT_SECONDS:-0}
      # "on" (explorer step), "planner" (the planner holds the tools) or "off".
      PLANNER_TOOLS: ${PLANNER_TOOLS:-on}
```

Run: `grep -n "PLANNER_TOOLS" docker-compose.yml`
Expected: `PLANNER_TOOLS: ${PLANNER_TOOLS:-on}` on one line. Before this, the api container never saw the setting: compose lists its environment explicitly, and the image has no `.env`.

- [ ] **Step 9: Run the tests, the suite and the finetune suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_planner_tools.py tests/test_dashboard_endpoint.py tests/test_discovery.py tests/test_planning_steps.py tests/test_dashboard_flow.py tests/test_kind_request.py`
Expected: all pass.

Run: `cd backend && .venv/bin/python -m pytest -q tests`
Expected: 13 more tests than after Task 8 (183 with Task 4's fix, 181 without); the only failures are the 3 known ones.

Run: `cd chartist-finetune && ../backend/.venv/bin/python -m pytest -q tests`
Expected: 81 passed.

- [ ] **Step 10: Record it in AGENTS.md**

Insert this bullet directly after the line that starts with `` - `preview_chart(plans)` previews up to 7 draft plans``, which Task 8 added:

```markdown
- `PLANNER_TOOLS=planner`: there is no explorer step. The planner itself may call `preview_chart`, `row_grain`, `inspect_column`, `find_columns` and `relationship`, at most 3 calls, on its first try only, with each result its fact line. It then answers in the same JSON, which the same checks read.
  - A retry is a plain call. When the budget runs out the unbound model answers, and a tool failure plans without tools. A server that refuses tool turns in a plain call is asked again without them.
  - Binding the tools adds ~850 tokens to the planner's prompt, measured with the chat template on the Spotify table: 1,407 -> 2,262, and 2,937 after 3 calls. That is past the 2,048 lora-v2 was trained at. A test pins the tool specs (at most 2,000 chars) and the note (at most 450).
  - `docker-compose.yml` now passes `PLANNER_TOOLS` (default `on`), so `PLANNER_TOOLS=planner make up` works. An unknown value is a 500.
```

- [ ] **Step 11: Write the server probe** (`backend/scripts/probe_planner_tools.py`)

The fakes above cannot show two server behaviours:
- whether `preview_chart`'s `plans` arrives as a list;
- whether a plain call carrying tool turns still answers.

This script asks the real server, from the host, saving nothing.

```python
"""Probe the model server for two things PLANNER_TOOLS=planner relies on that
the tests' fake models cannot show. Host-side, against `make serve-model`;
it saves nothing and draws nothing.

    cd backend && .venv/bin/python scripts/probe_planner_tools.py

1. Offered the planner's tools and asked to check its draft, does the planner
   call any, and does preview_chart's `plans` arrive as a list?
2. After a tool call and its result, does a plain call (no tools offered)
   still answer with the plan JSON? If it raises, planning.py answers again
   without the tool turns, at the cost of one failed call per tool-using try.
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("LLM_BACKEND", "mlx")
os.environ.setdefault("MLX_BASE_URL", "http://127.0.0.1:8080/v1")
os.environ.setdefault("MLX_MODEL", "default_model")

import pandas as pd  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402

from app.services.agents.data_tools import PLANNER_TOOL_NAMES, ToolBox  # noqa: E402
from app.services.agents.planning_contract import (  # noqa: E402
    PLANNER_SYSTEM_PROMPT, PLANNER_TOOLS_NOTE, PLANNER_USER_TEMPLATE, extract_json, render_directions,
    with_context)
from app.services.agents.profiler import profile_table, render_profiles  # noqa: E402
from app.services.llm import get_llm  # noqa: E402

TABLE = "web_traffic.csv"
frame = pd.read_csv(BACKEND / "uploads" / TABLE)
profile = profile_table(TABLE, frame)
direction = [{"question": "How does the bounce rate move through the day?", "why": "asked", "table": TABLE,
              "columns": ["hourOfDay", "bounceRatePct"]}]
user = with_context(PLANNER_USER_TEMPLATE.format(profiles=render_profiles([profile]),
                                                 directions=render_directions(direction)),
                    notes=(PLANNER_TOOLS_NOTE,))
box = ToolBox({TABLE: {"type": "file", "name": TABLE}}, str(BACKEND / "uploads"),
              loader=lambda source, data_dir: frame, tools=PLANNER_TOOL_NAMES, kinds={TABLE: profile.kinds()})
planner = get_llm("spec_planner")
messages = [SystemMessage(content=PLANNER_SYSTEM_PROMPT), HumanMessage(content=user)]

def prompt_tokens(message) -> object:
    """The server's own prompt token count, when it reports usage."""
    usage = (getattr(message, "response_metadata", None) or {}).get("token_usage") or {}
    return usage.get("prompt_tokens", "not reported")


reply = planner.bind_tools(box.specs).invoke(messages)
asked = list(getattr(reply, "tool_calls", None) or [])
print("1. tool calls:", [call.get("name") for call in asked] or "none")
print("   prompt tokens (server):", prompt_tokens(reply))
for call in asked:
    if call.get("name") == "preview_chart":
        print("   preview_chart plans arrived as", type((call.get("args") or {}).get("plans")).__name__)

draft = [{"chart": "line", "table": TABLE, "x": "hourOfDay", "y": "bounceRatePct", "agg": "none"}]
turns = messages + [
    AIMessage(content="", tool_calls=[{"name": "preview_chart", "args": {"plans": draft}, "id": "probe-1"}]),
    ToolMessage(content=box.call("preview_chart", {"plans": draft}, compact=True), tool_call_id="probe-1"),
]
try:
    answer = planner.invoke(turns)
    text = str(getattr(answer, "content", "") or "")
    payload = extract_json(text)
    found = isinstance(payload, dict) and "charts" in payload
    print("2. plain call after tool turns:", "JSON with charts" if found else f"no plan JSON: {text[:200]!r}")
    print("   prompt tokens (server):", prompt_tokens(answer))
except Exception as exc:  # noqa: BLE001 - this is what the probe is for
    print("2. plain call after tool turns raised:", exc)
```

Run: `cd backend && .venv/bin/python -m py_compile scripts/probe_planner_tools.py`
Expected: no output.

- [ ] **Step 12: Commit**

```bash
git add backend/app/services/agents/planning_contract.py backend/app/services/agents/discovery.py \
  backend/app/services/agents/planning.py backend/app/services/agents/dashboard_flow.py \
  backend/app/api/v1/endpoints/blocks.py backend/app/core/config.py docker-compose.yml \
  backend/scripts/probe_planner_tools.py \
  backend/tests/test_planner_tools.py backend/tests/test_dashboard_endpoint.py AGENTS.md
git commit -m "feat(planning): PLANNER_TOOLS=planner lets the planner hold the tools itself

No explorer step: the planner call gets preview_chart, row_grain,
inspect_column, find_columns and relationship bound and may call them (at
most 3, first try only, compact fact lines) before its JSON; the same checks
and retries follow, a retry is plain, and a tool failure plans without tools.
The tool loop is shared with the explorer (discovery.run_tools). Compose now
passes PLANNER_TOOLS (default on); an unknown value is a 500.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 13: Probe the real server (controller)**

The model server must be running on the host (`make serve-model MLX_HOST=127.0.0.1`, lora-v2), and `backend/uploads/web_traffic.csv` must exist (`make sample-data`).

Run: `cd backend && .venv/bin/python scripts/probe_planner_tools.py`

Expected, in this shape:

```
1. tool calls: ['preview_chart']
   prompt tokens (server): <n>
   preview_chart plans arrived as list
2. plain call after tool turns: JSON with charts
   prompt tokens (server): <n>
```

Each line has a fallback outcome:
- **"tool calls: none".** A finding: the planner did not take the offer.
- **`plans` arrived as `str`.** Handled by the `json.loads` in `_preview_chart`.
- **Line 2 "raised".** Every tool-using try then costs one failed call before `answer()` retries without the tool turns. Tell the user before Task 10's 3-hour run.
- **Prompt tokens.** Add the two server counts to the AGENTS.md bullet from Step 10, labelled as the server's count on `web_traffic.csv` (the chat-template numbers there are on the Spotify table).

Keep the three lines: Task 10 Step 13 records them.

---

### Task 10: Measure `planner` against `on`, time the tools, and decide the default

The user's goal is that the model decides what to look at. This task measures whether letting the planner hold the tools is at least as good as today's explorer step:
- on the first 40 frozen planning requests, both arms on the same code and the same rows;
- with the first 3 charts of each dashboard drawn through the app's own path.

**The decision rule (from the user).** `planner` becomes the default only if, against `on`:
- the render rate is not lower;
- the first-try rate is not lower;
- the planned-kind rate is not lower;
- lines with repeated x are not higher;
- and the median seconds per dashboard rise by less than 30.

"Lines with repeated x" is counted as the number of times the model drew one. A rendered figure can never contain such a line after Task 6, so the count is each time the drawing check sent the code back, plus a final failure for it (`repair_reasons`, Task 6). "Seconds per dashboard" are the planning seconds, explorer or tool time included, as in the earlier gate. Drawing time is reported separately.

**Files:**
- Modify: `chartist-finetune/measure_planning_tools.py`, replaced whole (the existing functions are kept unchanged)
- Test: `chartist-finetune/tests/test_measure_planning_tools.py`
- Create: `backend/scripts/time_planner_tools.py`
- Created by the runs: `chartist-finetune/data/v2/planning_tools_tools-on-draw3.json` and `.rows.jsonl`, `planning_tools_tools-planner-draw3.json` and `.rows.jsonl`, and `planning_tools_planner_compare.json`
- Modify, only if the rule says `planner`: `backend/app/core/config.py`, `docker-compose.yml`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes:
  - `plan_charts(..., toolbox=)`, `ToolBox(tools=PLANNER_TOOL_NAMES, kinds=)` and `columns_by_table` (Tasks 8–9);
  - `run_spec(spec, source, chartist, data_dir)`, which returns `repairs` and `repair_reasons`, and `REPEATED_X_FIX` (Task 6);
  - `measure_planning.plan_matches(chart, figure_type, code)` (existing; the trace type plus the area tie-break).
- Produces:
  - `draw_first(specs, source, chartist, data_dir, n, run=None) -> list[dict]`. Each dict has `chart`, `rendered`, `kind_ok`, `repairs`, `repeated_x`, `error` and `seconds`.
  - `summarize(rows)`. When rows carry `drawn`, it adds `charts_drawn`, `render_rate`, `planned_kind_rate` (of the rendered charts, as `measure_planning.py`), `repairs_per_chart`, `repeated_x_per_dashboard` and `median_draw_seconds`. Rows without `drawn` give exactly the old keys.
  - `compare_planner(on_rows, planner_rows) -> dict`, with keys `paired_rows`, `on`, `planner`, `first_try`, `median_seconds_delta` and `decision`. `decision` holds `render_not_lower`, `first_try_not_lower`, `planned_kind_not_lower`, `repeated_x_not_higher`, `median_seconds_rise_under_30`, `planner_uses_tools`, `dropped_not_higher`, `both_drew_charts` and `planner_by_default`. After the Task 10 review (fix round 1): `dropped_not_higher` compares charts dropped per dashboard, so an arm that plans fewer charts is not rewarded by rates over drawn charts; `both_drew_charts` makes the draw checks count only when both arms drew charts; `repeated_x_per_dashboard` and `median_draw_seconds` are taken over the dashboards that drew at least one chart. `planner_uses_tools` (controller, 2026-11-23) is true only when the planner arm made at least one tool call per dashboard on average above zero: a planner arm that calls no tool is the `on` flow minus the explorer, and must never become the default.
  - CLI: `--tools {on,off,planner}`, `--draw N` and `--compare-planner`. A `--draw` run writes files labelled `tools-<arm>-draw<N>`, so the committed `tools-on`/`tools-off` rows, which already hold these 40 ids, are never resumed into. `compare` and its decision keys are unchanged.

**Who does what.** An implementer does Steps 1-8 and stops after Step 8. Step 6 reads `backend/uploads/spotify_songs.csv`, which exists on this machine; download it only if it is missing. The controller runs Steps 9-14: they need Task 9's probe (its Step 13), the model server and the two background runs.

- [ ] **Step 1: Write the failing tests** (append to `chartist-finetune/tests/test_measure_planning_tools.py`; `_row`, `summarize` and `sign_test_p` are already there)

```python


from measure_planning_tools import REPEATED_X_FIX, compare_planner, draw_first


def _drawn(rendered=True, kind_ok=True, repairs=0, repeated_x=0):
    return {"chart": "line", "rendered": rendered, "kind_ok": kind_ok, "repairs": repairs,
            "repeated_x": repeated_x, "error": "", "seconds": 5.0}


def test_summarize_adds_draw_scores_only_when_charts_were_drawn():
    assert "render_rate" not in summarize([_row("a")])
    rows = [{**_row("a"), "drawn": [_drawn(), _drawn(rendered=False, kind_ok=False, repairs=2)], "draw_seconds": 20.0},
            {**_row("b"), "drawn": [_drawn(kind_ok=False, repairs=1, repeated_x=1)], "draw_seconds": 10.0}]
    s = summarize(rows)
    assert s["charts_drawn"] == 3 and s["render_rate"] == 2 / 3 and s["planned_kind_rate"] == 0.5
    assert s["repairs_per_chart"] == 1.0 and s["repeated_x_per_dashboard"] == 0.5 and s["median_draw_seconds"] == 15.0


def test_draw_first_scores_each_chart_and_counts_lines_drawn_back_and_forth():
    loopy = "the line 'x' has 168 points but only 24 x values, so it runs back and forth: " + REPEATED_X_FIX

    def run(spec, source, chartist, data_dir):
        if spec["chart"] == "line":
            return {"execution_result": {"figure": {"data": [{"type": "scatter", "mode": "lines"}]}}, "error": "",
                    "code": "fig = px.line(d)", "repairs": 1, "repair_reasons": [loopy]}
        return {"execution_result": {}, "error": "The model could not draw this chart: " + loopy, "code": "",
                "repairs": 2, "repair_reasons": [loopy, loopy]}

    drawn = draw_first([{"chart": "line"}, {"chart": "area"}, {"chart": "bar"}], {}, None, "", 2, run=run)
    assert [(d["rendered"], d["kind_ok"], d["repairs"], d["repeated_x"]) for d in drawn] == [
        (True, True, 1, 1), (False, False, 2, 3)]


def _draw_arms():
    on, planner = [], []
    for rid in "abcd":
        on.append({**_row(rid, planner_attempts=2, seconds=60.0), "drawn": [_drawn(repeated_x=1)], "draw_seconds": 9.0})
        planner.append({**_row(rid, planner_attempts=1, seconds=75.0), "drawn": [_drawn()], "draw_seconds": 8.0,
                        "tool_calls": ["preview_chart"]})
    return on, planner


def test_compare_planner_applies_the_default_rule():
    on, planner = _draw_arms()
    result = compare_planner(on, planner)
    assert result["paired_rows"] == 4 and result["first_try"]["planner_better"] == 4
    assert result["decision"] == {"render_not_lower": True, "first_try_not_lower": True,
                                  "planned_kind_not_lower": True, "repeated_x_not_higher": True,
                                  "median_seconds_rise_under_30": True, "planner_uses_tools": True,
                                  "planner_by_default": True}


def test_compare_planner_keeps_on_when_the_planner_is_slow_or_draws_more_loops():
    on, planner = _draw_arms()
    slow = [{**r, "seconds": r["seconds"] + 30.0} for r in planner]
    assert compare_planner(on, slow)["decision"]["planner_by_default"] is False
    loopy = [{**r, "drawn": [_drawn(repeated_x=2)]} for r in planner]
    decision = compare_planner(on, loopy)["decision"]
    assert decision["repeated_x_not_higher"] is False and decision["planner_by_default"] is False


def test_compare_planner_keeps_on_when_the_planner_calls_no_tool():
    on, planner = _draw_arms()
    decision = compare_planner(on, [{**r, "tool_calls": []} for r in planner])["decision"]
    assert decision["planner_uses_tools"] is False and decision["planner_by_default"] is False
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd chartist-finetune && ../backend/.venv/bin/python -m pytest -q tests/test_measure_planning_tools.py`
Expected: a collection error, `ImportError: cannot import name 'REPEATED_X_FIX' from 'measure_planning_tools'`.

- [ ] **Step 3: Implement**

Replace the whole of `chartist-finetune/measure_planning_tools.py` with:

```python
#!/usr/bin/env python3
"""Does the planner plan better when it may check the data first?

Runs the backend's own planning code (tool step, analyst, planner, checks) on
the frozen planning test set, over HTTP against the running model server, on
the same rows in each arm: tools off, on (an explorer step first) or planner
(the planner holds the tools). With --draw N the first N plans of each
dashboard are drawn through the app's own path (run_spec: chartist, executor,
repair loop) and scored. Rows are saved as they finish; rerunning resumes.

    cd chartist-finetune
    ../backend/.venv/bin/python measure_planning_tools.py --tools off --limit 40
    ../backend/.venv/bin/python measure_planning_tools.py --tools on --limit 40
    ../backend/.venv/bin/python measure_planning_tools.py --tools on --draw 3 --limit 40
    ../backend/.venv/bin/python measure_planning_tools.py --tools planner --draw 3 --limit 40
    ../backend/.venv/bin/python measure_planning_tools.py --compare-planner --draw 3
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))
os.environ.setdefault("LLM_BACKEND", "mlx")
os.environ.setdefault("MLX_BASE_URL", "http://127.0.0.1:8080/v1")
os.environ.setdefault("MLX_MODEL", "default_model")

import pandas as pd  # noqa: E402

from app.services.agents.architect import spread_sample  # noqa: E402
from app.services.agents.chartist_contract import REPEATED_X_FIX  # noqa: E402
from app.services.agents.data_tools import PLANNER_TOOL_NAMES, ToolBox  # noqa: E402
from app.services.agents.discovery import discover  # noqa: E402
from app.services.agents.planning import finish, plan_charts, propose_directions  # noqa: E402
from app.services.agents.profiler import columns_by_table, profile_table  # noqa: E402
from app.services.llm import get_llm  # noqa: E402
from measure_planning import plan_matches  # noqa: E402

SAMPLE_ROWS = 2000


def first_try(r: dict) -> bool:
    return r["planner_attempts"] == 1 and r["charts"] > 0


def sign_test_p(a: int, b: int) -> float:
    """Exact two-sided sign test on a wins one way and b the other."""
    n = a + b
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(a, b) + 1))
    return min(1.0, 2 * tail / 2 ** n)


def read_rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def draw_first(specs: list[dict], source: dict, chartist, data_dir: str, n: int, run=None) -> list[dict]:
    """Draw the first n plans through the app's own path and score each one:
    rendered, the planned kind, repairs used, and how many times the model drew
    a line whose x repeats (each time the drawing check sent it back, plus a
    final failure for it)."""
    if run is None:
        from app.services.agents.spec_runner import run_spec as run
    drawn = []
    for spec in specs[:n]:
        started = time.perf_counter()
        result = run(spec, source, chartist, data_dir)
        figure = (result.get("execution_result") or {}).get("figure")
        rendered = bool(figure) and not result.get("error")
        traces = (figure or {}).get("data") or []
        figure_type = (traces[0].get("type") or "scatter") if traces else None
        error = str(result.get("error") or "")
        drawn.append({
            "chart": spec["chart"], "rendered": rendered,
            "kind_ok": rendered and plan_matches(spec["chart"], figure_type, str(result.get("code") or "")),
            "repairs": int(result.get("repairs") or 0),
            "repeated_x": sum(1 for reason in result.get("repair_reasons", []) if REPEATED_X_FIX in reason)
                          + (1 if REPEATED_X_FIX in error else 0),
            "error": error[:160],
            "seconds": round(time.perf_counter() - started, 1),
        })
    return drawn


def summarize(rows: list[dict]) -> dict:
    planned = [r for r in rows if r["charts"]]
    asked = [r for r in rows if r["directions"]]
    drawn = [d for r in rows for d in r.get("drawn", [])]
    rendered = [d for d in drawn if d["rendered"]]
    draws = {
        "charts_drawn": len(drawn),
        "render_rate": len(rendered) / len(drawn),
        # Of the charts that rendered, how many are the kind that was planned (as measure_planning.py).
        "planned_kind_rate": sum(1 for d in rendered if d["kind_ok"]) / len(rendered) if rendered else 0.0,
        "repairs_per_chart": statistics.mean(d["repairs"] for d in drawn),
        "repeated_x_per_dashboard": statistics.mean(sum(d["repeated_x"] for d in r.get("drawn", [])) for r in rows),
        "median_draw_seconds": statistics.median(r.get("draw_seconds", 0.0) for r in rows),
    } if drawn else {}
    return {
        "rows": len(rows),
        "analyst_usable_rate": sum(1 for r in rows if r["directions"]) / len(rows),
        "analyst_retry_rate": sum(1 for r in rows if r["analyst_attempts"] > 1) / len(rows),
        "planner_first_try_rate": sum(1 for r in planned if r["planner_attempts"] == 1) / len(planned) if planned else 0.0,
        "mean_charts": statistics.mean(r["charts"] for r in planned) if planned else 0.0,
        "dropped_per_dashboard": statistics.mean(r["dropped"] for r in planned) if planned else 0.0,
        "tool_calls_per_dashboard": statistics.mean(len(r["tool_calls"]) for r in rows),
        "median_seconds": statistics.median(r["seconds"] for r in rows),
        "asked_rows": len(asked),
        "first_try_rate_counting_failures": sum(1 for r in asked if first_try(r)) / len(asked) if asked else 0.0,
        "total_failure_rate": sum(1 for r in asked if r["charts"] == 0) / len(asked) if asked else 0.0,
        "charts_dropped_per_dashboard": statistics.mean(r["directions"] - r["charts"] for r in asked) if asked else 0.0,
        **draws,
    }


def compare(off_rows: list[dict], on_rows: list[dict]) -> dict:
    off = {r["request_id"]: r for r in off_rows}
    on = {r["request_id"]: r for r in on_rows}
    ids = [rid for rid in on if rid in off]
    # first try and dropped charts are compared only where both arms asked the analyst
    both = [rid for rid in ids if off[rid]["directions"] and on[rid]["directions"]]
    dropped = lambda r: r["directions"] - r["charts"]  # noqa: E731
    on_better = sum(1 for rid in both if first_try(on[rid]) and not first_try(off[rid]))
    off_better = sum(1 for rid in both if first_try(off[rid]) and not first_try(on[rid]))
    on_fewer = sum(1 for rid in both if dropped(on[rid]) < dropped(off[rid]))
    off_fewer = sum(1 for rid in both if dropped(off[rid]) < dropped(on[rid]))
    on_s = summarize([on[rid] for rid in ids])
    off_s = summarize([off[rid] for rid in ids])
    decision = {
        "first_try_not_lower": on_s["first_try_rate_counting_failures"] >= off_s["first_try_rate_counting_failures"],
        "dropped_not_higher": on_s["charts_dropped_per_dashboard"] <= off_s["charts_dropped_per_dashboard"],
        "analyst_usable_not_lower": on_s["analyst_usable_rate"] >= off_s["analyst_usable_rate"],
        "median_seconds_rise_under_30": on_s["median_seconds"] - off_s["median_seconds"] < 30,
    }
    decision["tools_on_by_default"] = all(decision.values())
    return {
        "paired_rows": len(ids),
        "first_try": {"on_better": on_better, "off_better": off_better,
                      "p": sign_test_p(on_better, off_better)},
        "charts_dropped": {"on_fewer": on_fewer, "off_fewer": off_fewer,
                           "p": sign_test_p(on_fewer, off_fewer)},
        "median_seconds_delta": statistics.median(on[rid]["seconds"] - off[rid]["seconds"] for rid in ids),
        "decision": decision,
    }


def compare_planner(on_rows: list[dict], planner_rows: list[dict]) -> dict:
    """PLANNER_TOOLS=planner against today's on, paired on the same request ids,
    with the rule that decides the default (AGENTS.md)."""
    on = {r["request_id"]: r for r in on_rows}
    planner = {r["request_id"]: r for r in planner_rows}
    ids = [rid for rid in planner if rid in on]
    both = [rid for rid in ids if on[rid]["directions"] and planner[rid]["directions"]]
    planner_better = sum(1 for rid in both if first_try(planner[rid]) and not first_try(on[rid]))
    on_better = sum(1 for rid in both if first_try(on[rid]) and not first_try(planner[rid]))
    on_s = summarize([on[rid] for rid in ids])
    pl_s = summarize([planner[rid] for rid in ids])
    decision = {
        "render_not_lower": pl_s.get("render_rate", 0.0) >= on_s.get("render_rate", 0.0),
        "first_try_not_lower": pl_s["first_try_rate_counting_failures"] >= on_s["first_try_rate_counting_failures"],
        "planned_kind_not_lower": pl_s.get("planned_kind_rate", 0.0) >= on_s.get("planned_kind_rate", 0.0),
        "repeated_x_not_higher": pl_s.get("repeated_x_per_dashboard", 0.0) <= on_s.get("repeated_x_per_dashboard", 0.0),
        "median_seconds_rise_under_30": pl_s["median_seconds"] - on_s["median_seconds"] < 30,
        # A planner arm that calls no tool is the on flow minus the explorer; never the default.
        "planner_uses_tools": pl_s.get("tool_calls_per_dashboard", 0.0) > 0,
    }
    decision["planner_by_default"] = all(decision.values())
    return {
        "paired_rows": len(ids),
        "on": on_s,
        "planner": pl_s,
        "first_try": {"planner_better": planner_better, "on_better": on_better,
                      "p": sign_test_p(planner_better, on_better)},
        "median_seconds_delta": statistics.median(planner[rid]["seconds"] - on[rid]["seconds"] for rid in ids),
        "decision": decision,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", choices=["on", "off", "planner"])
    ap.add_argument("--testset", default="data/v2/planning_testset.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--draw", type=int, default=0,
                    help="draw the first N plans of each dashboard through run_spec and score them")
    ap.add_argument("--compare", action="store_true",
                    help="score the two finished arms from their rows files; no model call")
    ap.add_argument("--compare-planner", action="store_true",
                    help="score planner against on from the --draw N rows files; no model call")
    args = ap.parse_args()
    if args.compare_planner:
        if not args.draw:
            ap.error("--compare-planner needs the --draw N the two arms ran with")
        result = compare_planner(read_rows(ROOT / f"data/v2/planning_tools_tools-on-draw{args.draw}.rows.jsonl"),
                                 read_rows(ROOT / f"data/v2/planning_tools_tools-planner-draw{args.draw}.rows.jsonl"))
        (ROOT / "data/v2/planning_tools_planner_compare.json").write_text(json.dumps(result, indent=2),
                                                                         encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.compare:
        result = compare(read_rows(ROOT / "data/v2/planning_tools_tools-off.rows.jsonl"),
                         read_rows(ROOT / "data/v2/planning_tools_tools-on.rows.jsonl"))
        (ROOT / "data/v2/planning_tools_compare.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.tools is None:
        ap.error("--tools is required unless --compare or --compare-planner is given")
    # A --draw run gets files of its own, so the committed tools-on/off rows are never resumed into.
    label = f"tools-{args.tools}" + (f"-draw{args.draw}" if args.draw else "")

    schemas = {r["schema_id"]: r for r in (json.loads(l) for l in
               (ROOT / "data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)}
    rows = [json.loads(l) for l in (ROOT / args.testset).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = rows[: args.limit] if args.limit else rows
    out = ROOT / f"data/v2/planning_tools_{label}.json"
    ckpt = out.with_suffix(".rows.jsonl")
    done = ({json.loads(l)["request_id"] for l in ckpt.read_text(encoding="utf-8").splitlines() if l.strip()}
            if ckpt.exists() else set())
    analyst, planner = get_llm("analyst"), get_llm("spec_planner")
    explorer = get_llm("explorer") if args.tools == "on" else None
    chartist = None
    if args.draw:
        from app.services.agents.chartist import ChartistAgent

        chartist = ChartistAgent(get_llm("chartist"))

    for row in rows:
        if row["request_id"] in done:
            continue
        schema = schemas[row["schema_id"]]
        frame = pd.read_csv(ROOT / schema["fixture_csv"])
        table = schema["table_name"]
        profiles = [profile_table(table, spread_sample(frame, SAMPLE_ROWS))]
        started = time.perf_counter()
        facts, validate, calls, planner_box = "", None, [], None
        if explorer is not None:
            toolbox = ToolBox({table: {"type": "file", "name": table}}, str(ROOT), loader=lambda s, d: frame)
            findings = finish(discover(explorer, row["request"], profiles, toolbox))
            facts, validate, calls = findings.note, toolbox.validate_spec, [c.name for c in findings.calls]
        elif args.tools == "planner":
            planner_box = ToolBox({table: {"type": "file", "name": table}}, str(ROOT), loader=lambda s, d: frame,
                                  tools=PLANNER_TOOL_NAMES, kinds=columns_by_table(profiles))
            validate = planner_box.validate_spec
        directions = propose_directions(analyst, row["request"], profiles, facts)
        charts = (plan_charts(planner, directions.items, profiles, facts, validate, toolbox=planner_box)
                  if directions.items else None)
        if planner_box is not None:
            calls = [c.name for c in planner_box.calls]
        record = {
            "request_id": row["request_id"], "request": row["request"], "tools": args.tools,
            "tool_calls": calls, "facts_chars": len(facts),
            "directions": len(directions.items), "analyst_attempts": directions.attempts,
            "charts": len(charts.items) if charts else 0, "planner_attempts": charts.attempts if charts else 0,
            "dropped": sum(1 for e in (charts.errors if charts else []) if e.startswith("chart ")),
            "seconds": round(time.perf_counter() - started, 1),
        }
        if args.draw:
            source = {"type": "file", "name": Path(schema["fixture_csv"]).name, "path": str(ROOT / schema["fixture_csv"])}
            drawing = time.perf_counter()
            record["drawn"] = draw_first(charts.items if charts else [], source, chartist, str(ROOT), args.draw)
            record["draw_seconds"] = round(time.perf_counter() - drawing, 1)
        with ckpt.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        drew = (f", drew {sum(d['rendered'] for d in record['drawn'])}/{len(record['drawn'])}"
                if args.draw else "")
        print(f"{row['request_id']}: tools {calls} -> {record['charts']} charts, "
              f"planner tries {record['planner_attempts']}, {record['seconds']}s{drew}", flush=True)

    all_rows = read_rows(ckpt)
    summary = {"label": label, **summarize(all_rows)}
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Summary of the changes against the old file:
- **Unchanged:** `first_try`, `sign_test_p`, `read_rows`, `compare` and the `--compare` path.
- **New:** `draw_first`, `compare_planner`, the `planner` arm, `--draw` and `--compare-planner`.
- **Changed:** `summarize` gained the draw keys.

- [ ] **Step 4: Run the finetune suite**

Run: `cd chartist-finetune && ../backend/.venv/bin/python -m pytest -q tests`
Expected: 89 passed (81 + 8, with the Task 10 review's fix round).

- [ ] **Step 5: Write the speed script** (`backend/scripts/time_planner_tools.py`)

```python
"""How long each planner tool takes as tables grow. Offline: no model, no server.

    cd backend && .venv/bin/python scripts/time_planner_tools.py

Three tables: the web-traffic sample (`make sample-data`), the Spotify CSV
(32,833 rows; AGENTS.md says how to fetch it) and a generated 50,000-row table
with 120 columns. Each table is loaded once; each tool then runs 5 times on it
and the median is printed, in milliseconds.
"""
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.services.agents.architect import spread_sample  # noqa: E402
from app.services.agents.data_tools import PLANNER_TOOL_NAMES, ToolBox  # noqa: E402
from app.services.agents.profiler import profile_table  # noqa: E402

UPLOADS = BACKEND / "uploads"
RUNS = 5


def wide_table(rows: int = 50_000, measures: int = 115) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    columns = {"id": np.arange(1, rows + 1), "region": rng.choice(["North", "South", "East", "West"], rows),
               "segment": rng.choice(["Consumer", "SMB", "Enterprise"], rows),
               "channel": rng.choice(["web", "app", "store"], rows),
               "day": np.repeat(pd.date_range("2023-01-01", periods=500).astype(str), rows // 500)}
    columns.update({f"metric_{i:03d}": rng.normal(100, 15, rows).round(3) for i in range(measures)})
    return pd.DataFrame(columns)


def tool_calls(table: str, kinds: dict[str, str]) -> list[tuple[str, dict]]:
    measure = next(c for c, k in kinds.items() if k == "number")
    category = next(c for c, k in kinds.items() if k == "category")
    plans = [{"chart": "bar", "table": table, "x": category, "y": measure, "agg": "sum"},
             {"chart": "kpi", "table": table, "y": measure, "agg": "mean"},
             {"chart": "histogram", "table": table, "x": measure, "agg": "none"}]
    return [("preview_chart", {"plans": plans}), ("row_grain", {"table": table}),
            ("inspect_column", {"table": table, "column": category}),
            ("find_columns", {"query": measure.split("_")[0]}),
            ("relationship", {"table": table, "a": category, "b": measure})]


def main() -> int:
    tables = {"web_traffic": pd.read_csv(UPLOADS / "web_traffic.csv"),
              "spotify": pd.read_csv(UPLOADS / "spotify_songs.csv"),
              "wide": wide_table()}
    timings: dict[str, dict[str, float]] = {}
    for name, frame in tables.items():
        kinds = profile_table(name, spread_sample(frame, 2000)).kinds()
        box = ToolBox({name: {"type": "file", "name": name}}, "", max_calls=10_000,
                      loader=lambda source, data_dir, f=frame: f, tools=PLANNER_TOOL_NAMES, kinds={name: kinds})
        box.frame(name)  # loaded once, outside the timings
        for tool, args in tool_calls(name, kinds):
            runs = []
            for _ in range(RUNS):
                started = time.perf_counter()
                box.call(tool, args, compact=True)
                runs.append((time.perf_counter() - started) * 1000)
            timings.setdefault(tool, {})[name] = statistics.median(runs)
    shapes = {name: f"{name} {len(f):,}x{len(f.columns)}" for name, f in tables.items()}
    print(f"{'tool':16s}" + "".join(f"{shapes[n]:>26s}" for n in tables))
    for tool, by_table in timings.items():
        print(f"{tool:16s}" + "".join(f"{by_table[n]:>23.1f} ms" for n in tables))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Time the tools**

Run: `cd backend && .venv/bin/python scripts/time_planner_tools.py`

It needs `backend/uploads/web_traffic.csv` (`make sample-data`) and `backend/uploads/spotify_songs.csv`; AGENTS.md has the `curl` that fetches the second. The numbers below came from a scratch copy of the repo on this machine, idle (your numbers will vary):

```
tool                     web_traffic 168x6         spotify 32,833x23           wide 50,000x120
preview_chart                       1.3 ms                    3.7 ms                    4.7 ms
row_grain                           0.4 ms                   15.4 ms                   11.4 ms
inspect_column                      0.8 ms                    4.2 ms                    5.8 ms
find_columns                        1.6 ms                  192.4 ms                  113.2 ms
relationship                        1.4 ms                    4.5 ms                    5.6 ms
```

Expected: every tool under 0.25 s on all three tables, and every tool except `find_columns` under 20 ms.

`find_columns` is not flat, for two reasons measured with cProfile in the scratch copy. Both are bounded by the 2,000-row sample, not the row count.
- **Spotify.** Most of its ~190 ms is `profiler._parse_dates` (`pd.to_datetime(format="mixed")`). It runs while the kind of each matched text column is tested: "track" matches 7 columns, 5 of them text, at about 30 ms each.
- **The 120-column table.** Its ~115 ms is the value scan of every column's sample (`astype(str)` and `value_counts`), about 1 ms per column.

Keep the printed table for Step 13.

- [ ] **Step 7: Commit the harness and the script**

```bash
git add chartist-finetune/measure_planning_tools.py chartist-finetune/tests/test_measure_planning_tools.py backend/scripts/time_planner_tools.py
git commit -m "feat(measure): a planner arm, drawn charts, and a speed script for the tools

measure_planning_tools.py gains --tools planner and --draw N: the first N
plans of each dashboard are drawn through run_spec and scored (rendered,
planned kind, repairs, lines drawn back and forth), and --compare-planner
applies the default rule. time_planner_tools.py times each tool on 168 rows,
32,833 rows and a 50,000 x 120 table.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 8: Check the frozen set is untouched**

Run: `cd chartist-finetune && shasum -a 256 data/v2/planning_testset.jsonl && cat data/v2/planning_testset.sha256`
Expected: the two hashes match (`8af1473a...`).

- [ ] **Step 9: Smoke-test both arms on 2 rows (controller)**

The model server must be running on the host (`make serve-model MLX_HOST=127.0.0.1`, lora-v2), and Task 9 Step 13's probe must have run. If its line 2 "raised", tell the user before the long runs: every tool-using try will cost one extra call.

Run:

```bash
cd chartist-finetune
../backend/.venv/bin/python measure_planning_tools.py --tools planner --draw 3 --limit 2
../backend/.venv/bin/python measure_planning_tools.py --tools on --draw 3 --limit 2
rm data/v2/planning_tools_tools-planner-draw3.json data/v2/planning_tools_tools-planner-draw3.rows.jsonl    data/v2/planning_tools_tools-on-draw3.json data/v2/planning_tools_tools-on-draw3.rows.jsonl
```

Expected: two lines per arm, such as `<id>: tools ['preview_chart'] -> 6 charts, planner tries 1, 41.2s, drew 3/3`, then a summary with `render_rate` and `repeated_x_per_dashboard`, and no traceback.

If the planner arm shows `tools []` on both rows, the planner called no tool. Record that as a finding for Step 13; it is not a bug.

- [ ] **Step 10: Run both arms on the same 40 rows (controller, background)**

Each arm takes about 1.5 hours: planning takes about 65–80 s per row, and 3 drawn charts add about 50 s. Run the arms one after the other, not in parallel, on an otherwise idle machine, because the earlier gate's timing was muddied by load. Write down the commit both arms start from.

Run (in the background):

```bash
cd chartist-finetune && git rev-parse --short HEAD &&   ../backend/.venv/bin/python measure_planning_tools.py --tools on --draw 3 --limit 40 &&   ../backend/.venv/bin/python measure_planning_tools.py --tools planner --draw 3 --limit 40
```

Expected: `data/v2/planning_tools_tools-on-draw3.json` and `data/v2/planning_tools_tools-planner-draw3.json`, each with `"rows": 40`. An interrupted run resumes from its rows file when started again.

- [ ] **Step 11: Compare**

Run: `cd chartist-finetune && ../backend/.venv/bin/python measure_planning_tools.py --compare-planner --draw 3`
Expected: `data/v2/planning_tools_planner_compare.json` with `"paired_rows": 40` and the `decision` object.

- [ ] **Step 12: Apply the decision rule**

- **`decision.planner_by_default` is `true`:**
  - In `backend/app/core/config.py`, set `PLANNER_TOOLS: str = "planner"`, and in its comment change `"on" by the no-harm rule on the first 40 frozen planning rows` to `"planner" by the rule in AGENTS.md`.
  - In `docker-compose.yml`, change `PLANNER_TOOLS: ${PLANNER_TOOLS:-on}` to `PLANNER_TOOLS: ${PLANNER_TOOLS:-planner}`.
  - Then run the backend suite: it gives the same count as after Task 9, because no test reads the default.
- **Otherwise:** keep `on`, and write down which decision keys were false.

- [ ] **Step 13: Record the measurement in AGENTS.md**

Insert these bullets directly after the line that starts with `` - `PLANNER_TOOLS=planner`: there is no explorer step``, which Task 9 added. Replace each `<...>` with the values from `planning_tools_planner_compare.json`, the two summary files and Step 6; nothing in angle brackets may remain.

```markdown
- Measured `planner` against `on`, first 40 frozen planning requests, first 3 charts drawn (`measure_planning_tools.py --draw 3`, `data/v2/planning_tools_tools-{on,planner}-draw3.*`, both arms from `<commit>`), on against planner:
  - render <x>% against <y>%;
  - first try <x>% against <y>% (paired <a> better planner, <b> better on, p=<p>);
  - planned kind <x>% against <y>%;
  - lines drawn back and forth <x> against <y> per dashboard;
  - repairs per chart <x> against <y>;
  - median planning seconds <x> against <y>;
  - tool calls per dashboard <x> against <y>.
- Default: `<on|planner>`, because <the failing keys | all eight checks pass>.
- Server probe (`backend/scripts/probe_planner_tools.py`): the planner offered its tools called <names | none>; `plans` arrived as <list | str>; a plain call after tool turns <answered with the plan JSON | raised, so planning answers again without the tool turns>.
- Tool speed, median of 5 calls on an idle machine (`backend/scripts/time_planner_tools.py`), on 168 rows, 32,833 rows and 50,000 × 120: preview_chart <a>/<b>/<c> ms, row_grain <...>, inspect_column <...>, relationship <...>. find_columns <...> is not flat: on Spotify it parses dates while testing each matched text column's kind, about 30 ms each; on the wide table it scans every column's 2,000-row sample, about 1 ms per column.
```

- [ ] **Step 14: Commit**

```bash
git add chartist-finetune/data/v2/planning_tools_tools-on-draw3.json chartist-finetune/data/v2/planning_tools_tools-on-draw3.rows.jsonl   chartist-finetune/data/v2/planning_tools_tools-planner-draw3.json chartist-finetune/data/v2/planning_tools_tools-planner-draw3.rows.jsonl   chartist-finetune/data/v2/planning_tools_planner_compare.json AGENTS.md backend/app/core/config.py docker-compose.yml
git commit -m "data(planning): planner vs on on 40 frozen rows, 3 charts drawn each

render: on X% -> planner Y%; first try: X% -> Y%; planned kind: X% -> Y%;
lines drawn back and forth per dashboard: X -> Y; median planning s: X -> Y.
Default: on|planner, because <the failing keys | all eight checks pass>.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
# Before running: put the measured numbers in place of every X and Y and the
# decision in the last line. config.py and docker-compose.yml change only
# when the rule says planner; git add skips them otherwise.
```

---

### Task 11: Browser check: "bounce rate by hour" now draws one point per hour

The end-to-end proof for Part B, on the stack people actually run: the user's broken chart, regenerated from a copy of the same sample data. The whole task is run by the **controller** on a test account.

**Files:**
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes:
  - everything above;
  - the SSE build (`generateDashboard`);
  - `GET /api/v1/dashboard/{id}/blocks`, which returns stored figures already decoded from typed arrays;
  - the api log lines from Tasks 5, 6 and 9: `[dashboard] chart plan`, `asking the model to fix its code` and `planner tool calls`.
- Produces: one AGENTS.md bullet with the result.

- [ ] **Step 1: Bring the stack up on the final code (controller)**

Run: `make sample-data && make serve-model` (terminal 1, lora-v2), then `make up` (terminal 2), then `make doctor`.
Expected: every `make doctor` line OK, and `backend/uploads/web_traffic.csv` present (168 rows × 6 columns).

`PLANNER_TOOLS` is whatever Task 10 left as the default. Write it down for Step 6.

- [ ] **Step 2: Upload a copy of the sample (controller)**

`SCRATCH` is any directory outside the repo, such as the controller's scratchpad.

Run: `cp backend/uploads/web_traffic.csv "$SCRATCH/web_traffic_copy.csv"`

Upload `web_traffic_copy.csv` as a file source for the test account on `/data`. If the browser cannot drive the file picker, use the API with the account's token. In the browser, `localStorage.getItem("promptdash_access_token")` gives the token.

Run: `curl -sS -H "Authorization: Bearer $TOKEN" -F "file=@$SCRATCH/web_traffic_copy.csv" http://localhost:8000/api/v1/data-sources/upload`
Expected: a JSON data source with `"status": "active"`.

- [ ] **Step 3: Ask for the chart (controller)**

On `/reports/new`, create a report whose only source is `web_traffic_copy.csv`, open its canvas, and type `bounce rate by hour` in the ask bar (no "/" kind). Wait for the block.

- [ ] **Step 4: Check the figure has one point per hour (controller)**

Run (with the report's id from the URL):

```bash
curl -sS -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/v1/dashboard/$REPORT/blocks" | python3 -c '
import json, sys
for block in json.load(sys.stdin):
    for trace in (block.get("figure") or {}).get("data", []):
        xs = trace.get("x") or []
        print(block["title"], "|", trace.get("type"), trace.get("mode"), "|", len(xs), "points,", len(set(map(str, xs))), "distinct x")'
```

Expected: every line trace of the bounce-rate block prints `24 points, 24 distinct x`. A grouped chart (one line per weekday) prints that once per line. Take a screenshot of the canvas.

Then check the log:

Run: `docker compose logs api --since 15m --no-log-prefix | grep -E "asking the model to fix its code|back and forth" | tail -5`
Expected: either nothing, meaning the model aggregated on its first try, or a repair whose problem names "back and forth". Record which.

- [ ] **Step 5: The same question as a dashboard (controller)**

On the same report, click Generate dashboard with the brief `bounce rate by hour` and let the build finish. Then run the Step 4 `curl` again, and the log check below.

Run: `docker compose logs api --since 15m --no-log-prefix | grep -E "\[dashboard\] chart plan|planner tool calls|missing kinds" | tail -12`

Expected:
- one `[dashboard] chart plan N of M: {...}` line per placed chart, with every field;
- for any line or area plan over `hourOfDay`, `agg` is not `none` or a `group` is set;
- every line trace in the new blocks prints as many points as distinct x;
- with `PLANNER_TOOLS=planner`, a `planner tool calls (n): ...` line.

- [ ] **Step 6: Record it in AGENTS.md**

Insert this bullet directly after the line that starts with `- The drawing check (`, which Task 6 added. Fill every `<...>`; nothing in angle brackets may remain.

```markdown
- Browser check <date> (lora-v2, `PLANNER_TOOLS=<mode>`, a copy of `web_traffic.csv`, 168 weekday × hour rows):
  - "bounce rate by hour" in the ask bar drew <n> line(s) of 24 points, x 0–23 once each. The drawing check <did not fire | sent the code back <k> time(s)>.
  - The dashboard brief "bounce rate by hour" logged <m> chart plans; the line plan over `hourOfDay` had agg <agg> (group <group or none>).
  - Every line in the new blocks had one point per x.
```

- [ ] **Step 7: Run every suite one last time**

Run: `cd backend && .venv/bin/python -m pytest -q tests`
Expected: 183 tests with Task 4's fix (181 without); the only failures are the 3 known ones in `test_chartist_contract.py`.

Run: `cd chartist-finetune && ../backend/.venv/bin/python -m pytest -q tests`
Expected: 89 passed.

Run: `cd byd-web && npm test && npx tsc --noEmit -p . && npx eslint lib/kind-notice.ts lib/blocks.ts components/report-canvas.tsx tests/kind-notice.test.mts`
Expected: `pass 8`, and no output from tsc or eslint.

Run: `grep -n "A picked kind is never dropped without a word" byd-web/DESIGN.md`
Expected: one line (from Task 3).

- [ ] **Step 8: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): bounce rate by hour now draws one point per hour

Browser check on a copy of the web-traffic sample: the ask bar and a
dashboard brief both drew 24 points per line; plans logged with every field.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Spec coverage

| Requirement | Task |
|---|---|
| A1: `links_on` skips keys into another schema, tested with a faked inspector | 1 |
| A2: best attempt ranked by required kinds first; the reviewer's reproduction as a test | 2 |
| A2: the planner told the kinds in an appended section, worded like the analyst's; trained prompts byte-identical (sha256 test) | 2 |
| A2: `missing_kinds` in the plan event, passed on by `blocks.py`, shown as one notice line (not `skipped`) | 2, 3 |
| A2: test that `chart_kinds` from the request reach `build_dashboard` | 2 |
| A3: live check of `/box` "energy by genre" on Spotify, and of a wide joined table (the demo gains `visits`) | 4 |
| A3: conditional fix: order the direction's columns by the brief's overlap helper, then fill to 12 | 4 |
| B4: data check for a line or area with `agg=none` whose x repeats per series, in one function shared with `preview_chart` | 5, 8 |
| B5: drawing check in `run_on_frame` on every path, typed arrays decoded, line-mode traces only, repair counted against `MAX_REPAIRS` | 6 |
| B6: one log line per placed plan, with every field | 5 |
| C7: `row_grain` (sample search, full-table confirmation, values only) and `inspect_column` repeats | 7 |
| C8: `preview_chart`: batched, at most 7 plans, one line each, from `preview` and the Part B function, bounded | 5, 8 |
| C9: `PLANNER_TOOLS=planner`: the planner holds 5 tools, at most 3 calls, appended instructions, same checks and retries, failures never fail a build; compose env | 9 |
| C10: harness `--tools planner` and `--draw N`, two 40-row runs, the speed script on three tables, the decision rule, AGENTS.md | 10 |
| C11: AGENTS.md (each task), DESIGN.md (Task 3), the bounce-rate browser check | 3, 11 |
