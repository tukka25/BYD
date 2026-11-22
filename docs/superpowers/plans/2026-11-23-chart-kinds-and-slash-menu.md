# Chart Kinds Panel and "/" Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the chart kinds the model can draw in a right-side panel, each with an example chart the model itself drew and its name. Let the user pick a kind by typing "/" in either prompt. The pick reaches the agent as a structured field, and the model plans and draws that kind.

**Architecture:**
- **One list of kinds.** The backend serves the list from `planning_contract.CHART_KINDS`, which the planner's checks already use, plus user-facing words, so the UI can never offer a kind the planner rejects.
- **A pick is a field, not text.** A pick travels as `chart_kind` (one chart) or `chart_kinds` (a dashboard brief), never as prompt text.
- **One chart in a picked kind.** It takes the dashboard's path shrunk to one chart: the detective picks the table, and the planner writes one plan that must be that kind (checked and retried). The chartist reads it as the `Chart plan:` block lora-v2 was trained on, and draws it through the repair loop.
- **Model-drawn examples.** The panel's thumbnails are figures the model drew through that same path on a seeded sample file. A kind with no example says so.
- **The "/" menu is an ARIA combobox.** Focus stays in the field, the highlighted option goes through `aria-activedescendant`, and the list filters as you type. Up and Down move, Enter or Tab pick, Esc closes, and a pick shows as a removable chip.

**Tech Stack:** FastAPI and pydantic v2, Next.js 16 with React 19, Tailwind 4, lucide-react, bundled Plotly (`plotly.js-dist-min`), pytest, and Node 24's built-in test runner (`node --test` with native TypeScript type stripping, so no test framework is added).

**Order:** run this after `2026-11-23-planner-tools-and-memory.md` and `2026-11-23-database-relationships.md`. It extends the planning functions' final signatures from those plans.

## Global Constraints

- Never hardcode charts. The examples are charts the model drew; a kind it could not draw gets no image, never a stand-in, and icons label kinds in the menu only.
- A picked kind is a structured field (`chart_kind`, `chart_kinds`), never prompt text, and is checked against `CHART_KINDS` at the API boundary (422 otherwise).
- A brief takes at most 4 kinds; a single chart takes 1.
- The chartist learns the kind only through the chart plan (`render_spec`), the form lora-v2 was trained on. `CHARTIST_CHART_TYPE_HINT` stays `off`.
- UI follows `byd-web/DESIGN.md`:
  - Components come from `components/ui.tsx` (`Button`, `IconButton`, `Chip`, `Panel`).
  - lucide icons use `strokeWidth={2.25}`.
  - Colours are tokens (`bg-surface`, `text-muted`, `bg-pine-wash`), never hex.
  - `--muted` is the lightest text.
- The menu is accessible: `role="combobox"`, `aria-expanded`, `aria-controls`, `aria-autocomplete="list"` and `aria-activedescendant` on the field, plus `role="listbox"` and `role="option"` with `aria-selected`.
- Backend tests: `cd backend && .venv/bin/python -m pytest -q tests`. Three failures in `tests/test_chartist_contract.py` predate this plan, and no new failure is allowed.
- Frontend checks: `cd byd-web && npm test && npx tsc --noEmit -p . && npx eslint <changed files>`.
- Commit after every task, with messages ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File Structure

- Create `backend/app/services/agents/chart_kinds.py`: the user-facing words for each `CHART_KINDS` entry.
- Create `backend/app/api/v1/endpoints/chart_kinds.py` and register it in `backend/app/api/v1/router.py`: `GET /api/v1/chart-kinds`.
- Modify `backend/app/services/agents/planning_contract.py`: `check_specs(..., required_kinds=())`.
- Modify `backend/app/services/agents/planning.py`: a `required_kinds` parameter.
- Modify `backend/app/services/agents/dashboard_flow.py`: `required_kinds`.
- Create `backend/app/services/agents/kind_request.py`: one chart in a picked kind.
- Modify `backend/app/api/v1/endpoints/blocks.py`: `chart_kind` and `chart_kinds` fields and routing.
- Create `backend/scripts/make_chart_kind_examples.py` and the generated `byd-web/public/chart-kinds/examples.json`.
- Create `byd-web/lib/slash-menu.ts` (pure logic), `byd-web/tests/slash-menu.test.mts`, `byd-web/lib/chart-kinds.ts`, `byd-web/components/kind-menu.tsx` and `byd-web/components/chart-kinds-panel.tsx`.
- Modify `byd-web/lib/blocks.ts`, `byd-web/components/report-canvas.tsx`, `byd-web/components/plot.tsx`, `byd-web/tsconfig.json` and `byd-web/package.json`.
- Tests: create `backend/tests/test_chart_kinds.py` and `backend/tests/test_kind_request.py`; modify `backend/tests/test_planning_contract.py` and `backend/tests/test_dashboard_flow.py`.
- Docs: `byd-web/DESIGN.md` and `AGENTS.md`.

---

### Task 1: The chart kinds catalogue and its endpoint

**Files:**
- Create: `backend/app/services/agents/chart_kinds.py`
- Create: `backend/app/api/v1/endpoints/chart_kinds.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_chart_kinds.py`

**Interfaces:**
- Consumes: `planning_contract.CHART_KINDS`.
- Produces:
  - `KIND_INFO: dict[str, dict]` with keys `label`, `best_for`, `needs` and `aliases`.
  - `chart_kinds() -> list[dict]`, each item `{"kind", "label", "best_for", "needs", "aliases"}`, in `CHART_KINDS` order.
  - `GET /api/v1/chart-kinds` (authenticated).

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_chart_kinds.py`)

```python
"""The kinds the UI offers are exactly the kinds the planner accepts."""
from app.api.v1.endpoints.chart_kinds import list_chart_kinds
from app.services.agents.chart_kinds import KIND_INFO, chart_kinds
from app.services.agents.planning_contract import CHART_KINDS


def test_every_planner_kind_has_words_for_the_user_and_nothing_else_does():
    assert set(KIND_INFO) == set(CHART_KINDS)


def test_the_list_follows_the_planner_order_and_carries_what_the_ui_shows():
    kinds = chart_kinds()
    assert [k["kind"] for k in kinds] == list(CHART_KINDS)
    assert all(k["label"] and k["best_for"] and k["needs"] and isinstance(k["aliases"], list) for k in kinds)


def test_the_endpoint_returns_the_list():
    assert list_chart_kinds(current_user=None) == chart_kinds()
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_chart_kinds.py`
Expected: ImportError.

- [ ] **Step 3: Implement**

`backend/app/services/agents/chart_kinds.py`:

```python
"""The chart kinds the model can draw, in the words the user sees.

Keyed by planning_contract.CHART_KINDS, the list the planner's checks use, so
the panel and the "/" menu can never offer a kind the planner would reject.
"""
from __future__ import annotations

from app.services.agents.planning_contract import CHART_KINDS

KIND_INFO: dict[str, dict] = {
    "kpi": {"label": "KPI card", "best_for": "One headline number", "needs": "a measure",
            "aliases": ["number", "metric", "indicator", "card"]},
    "bar": {"label": "Bar chart", "best_for": "Comparing groups, or a top 10", "needs": "a category and a measure",
            "aliases": ["column", "ranking", "top"]},
    "line": {"label": "Line chart", "best_for": "A trend over time", "needs": "a date or year and a measure",
             "aliases": ["trend", "timeline"]},
    "area": {"label": "Area chart", "best_for": "A total building up over time", "needs": "a date or year and a measure",
             "aliases": ["stacked", "cumulative"]},
    "scatter": {"label": "Scatter plot", "best_for": "How two measures relate", "needs": "two measures",
                "aliases": ["correlation", "relationship", "dots"]},
    "pie": {"label": "Pie chart", "best_for": "Shares of a whole, few slices", "needs": "a category and a measure",
            "aliases": ["donut", "share"]},
    "histogram": {"label": "Histogram", "best_for": "How one measure is spread", "needs": "one measure",
                  "aliases": ["distribution", "spread"]},
    "box": {"label": "Box plot", "best_for": "Spread and outliers by group", "needs": "a measure, optionally a category",
            "aliases": ["boxplot", "outliers"]},
    "heatmap": {"label": "Heatmap", "best_for": "Two groupings at once", "needs": "two categories or dates and a measure",
                "aliases": ["matrix", "grid"]},
    "treemap": {"label": "Treemap", "best_for": "Parts of a whole, nested", "needs": "one or two categories and a measure",
                "aliases": ["hierarchy", "nested"]},
    "sunburst": {"label": "Sunburst", "best_for": "A hierarchy in rings", "needs": "two categories and a measure",
                 "aliases": ["rings", "radial"]},
    "funnel": {"label": "Funnel", "best_for": "Drop-off between stages", "needs": "a stage category and a measure",
               "aliases": ["conversion", "stages"]},
    "waterfall": {"label": "Waterfall", "best_for": "How a total is built up step by step",
                  "needs": "a category or period and amounts", "aliases": ["bridge", "contribution"]},
}


def chart_kinds() -> list[dict]:
    return [{"kind": kind, **KIND_INFO[kind]} for kind in CHART_KINDS]
```

`backend/app/api/v1/endpoints/chart_kinds.py`:

```python
from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.models.user import User
from app.services.agents.chart_kinds import chart_kinds

router = APIRouter()


@router.get("")
def list_chart_kinds(current_user: User = Depends(get_current_user)) -> list[dict]:
    """The kinds the "/" menu and the chart kinds panel offer."""
    return chart_kinds()
```

In `router.py`, add `chart_kinds` to the endpoints import and add:

```python
api_router.include_router(chart_kinds.router, prefix="/chart-kinds", tags=["chart-kinds"])
```

- [ ] **Step 4: Run the tests and check the live route**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_chart_kinds.py`
Expected: 3 passed.

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/chart-kinds`
Expected: `401` (the route exists and wants a token).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/chart_kinds.py backend/app/api/v1/endpoints/chart_kinds.py backend/app/api/v1/router.py backend/tests/test_chart_kinds.py
git commit -m "feat(api): the chart kinds the model can draw, from the planner's own list

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Requested kinds in the planner checks and the dashboard flow

**Files:**
- Modify: `backend/app/services/agents/planning_contract.py` (`check_specs`)
- Modify: `backend/app/services/agents/planning.py` (`plan_charts_steps`, `plan_charts`)
- Modify: `backend/app/services/agents/dashboard_flow.py` (`build_dashboard`)
- Test: `backend/tests/test_planning_contract.py` and `backend/tests/test_dashboard_flow.py` (append)

**Interfaces:**
- Consumes: `KIND_INFO` (Task 1). `check_specs(payload, tables, validate=None)` and `plan_charts_steps(llm, directions, profiles, facts="", validate=None, links="")` from the earlier plans.
- Produces:
  - `check_specs(payload, tables, validate=None, required_kinds=())`.
  - `plan_charts_steps(..., links="", required_kinds=())` and `plan_charts(...)` with the same parameters.
  - `build_dashboard(..., memory="", required_kinds: tuple[str, ...] = ())`.

- [ ] **Step 1: Write the failing tests**

Append to `test_planning_contract.py`:

```python
def test_a_requested_kind_must_be_among_the_charts():
    valid, errors = check_specs({"charts": [spec()]}, TABLES, required_kinds=("treemap",))
    assert valid and any("asked for a treemap" in error for error in errors)


def test_a_requested_kind_that_is_there_passes():
    tree = spec(chart="treemap", x="cntry_cd", group="plan_tier", sort="", top_n=0)
    assert check_specs({"charts": [tree]}, TABLES, required_kinds=("treemap",))[1] == []
```

Append to `test_dashboard_flow.py` (it reuses `Recorder` from the planner-tools plan):

```python
def test_a_requested_kind_is_asked_for_and_must_be_in_the_plan(tmp_path):
    analyst = Recorder(DIRECTIONS)
    planner = Recorder(CHARTS, CHARTS.replace('"chart": "bar"', '"chart": "pie"'))
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("churn", [_source(tmp_path)], str(tmp_path), analyst, planner, chartist,
                                  required_kinds=("pie",)))
    plan = next(e for e in events if e.kind == "plan").data
    assert plan["placed"][0].spec["chart"] == "pie"
    assert "Include these chart kinds: Pie chart." in analyst.seen[0][-1].content
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_planning_contract.py tests/test_dashboard_flow.py -k "requested_kind"`
Expected: 3 failed on the unexpected keyword `required_kinds`.

- [ ] **Step 3: Implement**

In `check_specs`, add a `required_kinds: tuple[str, ...] = ()` parameter. Before `if not valid:`, add:

```python
    for kind in required_kinds:
        if not any(spec["chart"] == kind for spec in valid):
            errors.append(f"the user asked for a {kind}: make one of the charts a {kind}")
```

In `planning.py`, replace `plan_charts_steps` and `plan_charts` with:

```python
def plan_charts_steps(
    llm: Any,
    directions: list[dict],
    profiles: list[TableProfile],
    facts: str = "",
    validate: Callable[[dict], list[str]] | None = None,
    links: str = "",
    required_kinds: tuple[str, ...] = (),
) -> Generator[Retry, None, PlanStep]:
    user = with_context(
        PLANNER_USER_TEMPLATE.format(profiles=render_profiles(profiles), directions=render_directions(directions)),
        facts,
        links=links,
    )
    kinds = tuple(required_kinds)

    def check(payload: Any, tables: dict[str, dict[str, str]]) -> tuple[list[dict], list[str]]:
        return check_specs(payload, tables, validate, kinds)

    return run_checked(llm, PLANNER_SYSTEM_PROMPT, user, check, columns_by_table(profiles), "planner")


def plan_charts(
    llm: Any,
    directions: list[dict],
    profiles: list[TableProfile],
    facts: str = "",
    validate: Callable[[dict], list[str]] | None = None,
    links: str = "",
    required_kinds: tuple[str, ...] = (),
) -> PlanStep:
    return finish(plan_charts_steps(llm, directions, profiles, facts, validate, links, required_kinds))
```

In `dashboard_flow.py`, import `KIND_INFO` from `chart_kinds` and add `required_kinds: tuple[str, ...] = ()` as the last parameter of `build_dashboard`. After `profiles = ...`, add:

```python
    request = brief
    if required_kinds:
        labels = ", ".join(KIND_INFO[kind]["label"] for kind in required_kinds)
        request = f"{brief}\nInclude these chart kinds: {labels}.".strip()
```

Pass `request` (not `brief`) to `propose_directions_steps(...)` and `discover(...)`, and `required_kinds=required_kinds` to `plan_charts_steps(...)`. Leave `brief` where it was for `profile_sources` and `intro_html`.

- [ ] **Step 4: Run the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests`
Expected: only the 3 known failures.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/planning_contract.py backend/app/services/agents/planning.py backend/app/services/agents/dashboard_flow.py backend/tests/test_planning_contract.py backend/tests/test_dashboard_flow.py
git commit -m "feat(planning): a dashboard brief can require chart kinds

The analyst is told which kinds to include and the planner's checks send a
plan back until it has one of each.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: One chart in a picked kind, and the request fields

**Files:**
- Create: `backend/app/services/agents/kind_request.py`
- Modify: `backend/app/api/v1/endpoints/blocks.py` (`GenerateBlockRequest`, `DashboardBriefRequest`, `generate_block`, `generate_whole_dashboard`, `_ai_dashboard`)
- Test: `backend/tests/test_kind_request.py`

**Interfaces:**
- Consumes: `plan_charts(..., required_kinds=)` (Task 2); `profile_sources`; `run_spec`; `KIND_INFO`; `workflow.data_sourcing_node(state)`, which returns `{"source_decision": {"selected": source}, "data_context": ...}` or `{"error": ...}`.
- Produces:
  - `run_kind_request(question, chart_kind, sources, selected_source, planner_llm, chartist, data_dir, detect=None) -> dict`, with keys `code`, `execution_result`, `error`, `data_context`, `repairs`, `spec` and `plan` (or `error` alone).
  - `GenerateBlockRequest.chart_kind: Optional[str]` and `DashboardBriefRequest.chart_kinds: list[str]` (at most 4).

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_kind_request.py`)

```python
"""A chart in the kind picked with "/": planned as that kind, drawn by the model."""
import json

import pandas as pd
import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.blocks import DashboardBriefRequest, GenerateBlockRequest
from app.services.agents.chartist import ChartistAgent
from app.services.agents.kind_request import run_kind_request

TREEMAP_CODE = ("import plotly.express as px\n"
                "fig = px.treemap(df, path=['cntry_cd'], values='churn_cnt')\n"
                "print(fig.to_json())\n")


class Recorder:
    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def invoke(self, messages):
        self.seen.append(list(messages))
        return type("Reply", (), {"content": self.replies.pop(0)})()


class Fixed:
    def __init__(self, code):
        self.code = code

    def invoke(self, variables):
        return self.code


def _source(tmp_path):
    path = tmp_path / "saas.csv"
    pd.DataFrame({"cntry_cd": ["DE", "US"] * 5, "churn_cnt": range(10)}).to_csv(path, index=False)
    return {"id": "saas.csv", "type": "file", "name": "saas.csv", "path": str(path)}


def plan(chart):
    return json.dumps({"charts": [{"title": "Churn by country", "question": "q", "chart": chart, "table": "saas.csv",
                                   "x": "cntry_cd", "y": "churn_cnt", "group": "", "agg": "sum", "grain": "",
                                   "sort": "", "top_n": 0}]})


def test_the_picked_kind_is_planned_and_drawn_by_the_model(tmp_path):
    source = _source(tmp_path)
    planner = Recorder(plan("bar"), plan("treemap"))
    chartist = ChartistAgent(llm=None, generator=Fixed(TREEMAP_CODE), chart_type_hint_style="off")
    result = run_kind_request("churn by country", "treemap", [source], "", planner, chartist, str(tmp_path),
                              detect=lambda state: {"source_decision": {"selected": source}})
    assert result["plan"] == {"visualization_type": "treemap", "chart_type_source": "user"}
    assert result["spec"]["chart"] == "treemap"
    assert result["execution_result"]["figure"]["data"][0]["type"] == "treemap"
    assert "asked for a treemap" in planner.seen[1][-1].content


def test_a_kind_the_model_will_not_plan_is_an_error_not_a_different_chart(tmp_path):
    source = _source(tmp_path)
    result = run_kind_request("churn by country", "treemap", [source], "", Recorder(*[plan("bar")] * 3), None,
                              str(tmp_path), detect=lambda state: {"source_decision": {"selected": source}})
    assert "could not plan a treemap" in result["error"] and "execution_result" not in result


def test_unknown_kinds_are_refused_at_the_door():
    with pytest.raises(ValidationError):
        GenerateBlockRequest(prompt="x", chart_kind="sankey")
    assert GenerateBlockRequest(prompt="x", chart_kind="treemap").chart_kind == "treemap"
    assert DashboardBriefRequest(brief="", chart_kinds=["pie", "funnel"]).chart_kinds == ["pie", "funnel"]
    with pytest.raises(ValidationError):
        DashboardBriefRequest(brief="", chart_kinds=["pie", "bar", "line", "area", "box"])
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_kind_request.py`
Expected: an ImportError on `kind_request`.

- [ ] **Step 3: Implement**

`backend/app/services/agents/kind_request.py`:

```python
"""A single chart in the kind the user picked with "/".

The pick travels as a field, not as words in the prompt, and reaches the
chartist the way lora-v2 was trained to read a chart kind: inside a chart plan.
So this is the dashboard's path shrunk to one chart. The detective picks the
table, the planner writes one plan that must be that kind (checked, retried),
and the chartist draws it through the same repair loop. Nothing here draws a chart.
"""
from __future__ import annotations

from typing import Any, Callable

from app.services.agents.chart_kinds import KIND_INFO
from app.services.agents.dashboard_flow import profile_sources
from app.services.agents.planning import plan_charts
from app.services.agents.spec_runner import run_spec

MAX_DIRECTION_COLUMNS = 12


def run_kind_request(
    question: str,
    chart_kind: str,
    sources: list[dict],
    selected_source: str,
    planner_llm: Any,
    chartist: Any,
    data_dir: str,
    detect: Callable[[dict], dict] | None = None,
) -> dict:
    if detect is None:
        from app.services.agents.workflow import data_sourcing_node as detect
    label = KIND_INFO[chart_kind]["label"].lower()
    asked = {"visualization_type": chart_kind, "chart_type_source": "user"}
    decision = detect({"user_query": question, "plan": {"visualization_type": chart_kind},
                       "selected_source": selected_source, "available_sources": sources})
    if decision.get("error"):
        return {"error": decision["error"], "plan": asked}
    selected = (decision.get("source_decision") or {}).get("selected") or {}
    entries = profile_sources([selected], data_dir)
    if not entries:
        return {"error": f"Could not read {selected.get('name', 'that source')}.", "plan": asked}
    entry = entries[0]
    direction = {"question": question.strip(), "why": f"the user asked for a {label}", "table": entry.label,
                 "columns": [column.name for column in entry.profile.columns][:MAX_DIRECTION_COLUMNS]}
    step = plan_charts(planner_llm, [direction], [entry.profile], required_kinds=(chart_kind,))
    spec = next((s for s in step.items if s["chart"] == chart_kind), None)
    if spec is None:
        return {"error": f"The model could not plan a {label} for this question: " + "; ".join(step.errors[:3]),
                "plan": asked}
    return {**run_spec(spec, entry.source, chartist, data_dir), "spec": spec, "plan": asked}
```

In `blocks.py`:
- Change the pydantic import to `from pydantic import BaseModel, Field, field_validator`.
- Add `from app.services.agents.planning_contract import CHART_KINDS` and `from app.services.agents.kind_request import run_kind_request`.
- Replace the two request models:

```python
class GenerateBlockRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    data_source: Optional[str] = None
    # A kind picked with "/" in the ask bar: a field, never prompt text.
    chart_kind: Optional[str] = None

    @field_validator("chart_kind")
    @classmethod
    def _known_kind(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in CHART_KINDS:
            raise ValueError(f"chart_kind must be one of: {', '.join(CHART_KINDS)}")
        return value
```

```python
class DashboardBriefRequest(BaseModel):
    brief: str = Field(default="", max_length=400)
    # Kinds picked with "/" in the brief; the plan must include one of each.
    chart_kinds: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("chart_kinds")
    @classmethod
    def _known_kinds(cls, value: list[str]) -> list[str]:
        unknown = [kind for kind in value if kind not in CHART_KINDS]
        if unknown:
            raise ValueError(f"unknown chart kinds {unknown}; kinds are: {', '.join(CHART_KINDS)}")
        return list(dict.fromkeys(value))
```

Keep the existing `brief` field definition and comment if they differ only in wording.

In `generate_block`, replace the `result = await asyncio.to_thread(run_agent_workflow, ...)` call with:

```python
    sources = _user_sources(db, report)
    if payload.chart_kind:
        result = await asyncio.to_thread(
            run_kind_request, payload.prompt, payload.chart_kind, sources, payload.data_source or "",
            get_llm("spec_planner"), _agents()[2], settings.UPLOAD_DIR,
        )
    else:
        result = await asyncio.to_thread(run_agent_workflow, payload.prompt, payload.data_source or "", sources)
```

Then change the title line so a planned chart keeps the planner's title:

```python
    title = metric_label or (result.get("spec") or {}).get("title") or await asyncio.to_thread(
        _narrator().title_for,
        payload.prompt,
        data_context.get("columns") or [],
    )
```

`chart_type=plan.get("visualization_type")` already records the picked kind, because `result["plan"]` carries it.

In `generate_whole_dashboard`, replace the last three lines (from the planner-tools plan) with:

```python
    memory = _report_memory(db, report.id)  # before this request is recorded: it is the brief, not history
    _record_request(db, report, current_user, "dashboard", brief)
    kinds = list(payload.chart_kinds) if payload else []
    return _ai_dashboard(report, sources, brief, current_user, db, memory, kinds)
```

Change `_ai_dashboard` to accept and pass the kinds:

```python
def _ai_dashboard(report, sources, brief, current_user, db, memory: str = "", chart_kinds: list[str] | None = None):
    """The analyst proposes, the planner plans every chart at once, code checks
    both against the real tables, and the chartist draws each chart from its plan
    (agents/dashboard_flow.py). Nothing here reads a column name."""
    base_row = _next_row(db, report.id)
    tools_on = (settings.PLANNER_TOOLS or "off").strip().lower() == "on"
    flow = build_dashboard(
        brief,
        sources,
        settings.UPLOAD_DIR,
        get_llm("analyst"),
        get_llm("spec_planner"),
        _agents()[2],
        top=base_row,
        explorer_llm=get_llm("explorer") if tools_on else None,
        memory=memory,
        required_kinds=tuple(chart_kinds or ()),
    )
```

The rest of `_ai_dashboard` (the `events()` generator) is unchanged.

- [ ] **Step 4: Run the tests and the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_kind_request.py && .venv/bin/python -m pytest -q tests`
Expected: 3 passed, and only the 3 known failures in the suite.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/kind_request.py backend/app/api/v1/endpoints/blocks.py backend/tests/test_kind_request.py
git commit -m "feat(blocks): a chart in the kind the user picked

chart_kind (one chart) and chart_kinds (a brief, up to 4) arrive as
checked fields. One chart in a picked kind is planned like a dashboard
chart, as one plan that must be that kind, so the chartist reads the kind in
the Chart plan block it was trained on. A kind the model will not plan is
an error, never a different chart.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Example charts drawn by the model, one per kind

**Files:**
- Create: `backend/scripts/make_chart_kind_examples.py`
- Create (generated): `byd-web/public/chart-kinds/examples.json`

**Interfaces:**
- Consumes: `run_kind_request` (Task 3), `chart_kinds()` (Task 1), `decode_typed_arrays`, and the seeded `backend/uploads/ecommerce_orders.csv` (from `make sample-data`).
- Produces: a JSON list of `{"kind", "title", "figure"}`, one entry per kind the model drew.

- [ ] **Step 1: Write the script**

```python
"""Ask the model for one example of each chart kind, for the chart kinds panel.

Every example is the model's own chart, made through the same path a user's
"/kind" request takes (run_kind_request), on a seeded sample file. A kind the
model cannot draw is left out, and the panel says so; nothing stands in.

    docker exec -i promptdash-api python /app/scripts/make_chart_kind_examples.py > byd-web/public/chart-kinds/examples.json
"""
import json
import logging
import sys

sys.path.insert(0, "/app")
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)  # stdout is the JSON

from app.core.config import get_settings  # noqa: E402
from app.services.agents.chart_kinds import chart_kinds  # noqa: E402
from app.services.agents.kind_request import run_kind_request  # noqa: E402
from app.services.agents.workflow import _agents  # noqa: E402
from app.services.llm import get_llm  # noqa: E402
from app.utils.figure_json import decode_typed_arrays  # noqa: E402

MAX_FIGURE_CHARS = 150_000  # a thumbnail; a bigger figure would slow the panel for nothing
settings = get_settings()
source = {"id": "ecommerce_orders.csv", "type": "file", "name": "ecommerce_orders.csv",
          "path": f"{settings.UPLOAD_DIR}/ecommerce_orders.csv"}
planner, chartist = get_llm("spec_planner"), _agents()[2]
examples = []
for kind in chart_kinds():
    result = run_kind_request(f"Show this data as a {kind['label'].lower()}", kind["kind"], [source], source["id"],
                              planner, chartist, settings.UPLOAD_DIR)
    figure = (result.get("execution_result") or {}).get("figure")
    if not figure:
        print(f"[examples] no {kind['kind']}: {result.get('error')}", file=sys.stderr)
        continue
    figure = decode_typed_arrays(figure)
    if len(json.dumps(figure)) > MAX_FIGURE_CHARS:
        print(f"[examples] {kind['kind']} is too large for a thumbnail; left out", file=sys.stderr)
        continue
    print(f"[examples] {kind['kind']}: {result['spec']['title']}", file=sys.stderr)
    examples.append({"kind": kind["kind"], "title": result["spec"]["title"], "figure": figure})
print(json.dumps(examples))
```

- [ ] **Step 2: Generate the examples** (the model server must be running)

Run: `mkdir -p byd-web/public/chart-kinds && docker exec -i promptdash-api python /app/scripts/make_chart_kind_examples.py > byd-web/public/chart-kinds/examples.json`
Expected: one `[examples] <kind>: <title>` line per kind on stderr, and a JSON list in the file.

Run: `python3 -c "import json; d = json.load(open('byd-web/public/chart-kinds/examples.json')); print(len(d), [e['kind'] for e in d]); import os; print(os.path.getsize('byd-web/public/chart-kinds/examples.json'), 'bytes')"`
Expected: 10-13 kinds, under 2 MB. Record which kinds have no example; the panel will show "No example yet" for them.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/make_chart_kind_examples.py byd-web/public/chart-kinds/examples.json
git commit -m "feat(examples): one chart per kind, drawn by the model

N of 13 kinds drawn by lora-v2 on the seeded ecommerce sample through the
same path a '/kind' request takes; KINDS had none and get no image.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
# Before running: replace N with the count from Step 2 and KINDS with the
# kinds that printed "no <kind>" (or drop that clause if none did).
```

---

### Task 5: The "/" menu's logic, tested with Node's own runner

**Files:**
- Create: `byd-web/lib/slash-menu.ts`
- Create: `byd-web/tests/slash-menu.test.mts`
- Modify: `byd-web/tsconfig.json` (add `"allowImportingTsExtensions": true` to `compilerOptions`; `noEmit` is already on)
- Modify: `byd-web/package.json` (scripts)

**Interfaces:**
- Produces:
  - `KindOption { kind; label; best_for; needs; aliases: string[] }`.
  - `SlashToken { query; start; end }`.
  - `slashTokenAt(text, caret) -> SlashToken | null`.
  - `filterKinds(options, query) -> KindOption[]`.
  - `removeToken(text, token) -> { text; caret }`.

- [ ] **Step 1: Write the failing test** (`byd-web/tests/slash-menu.test.mts`)

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { filterKinds, removeToken, slashTokenAt } from "../lib/slash-menu.ts";

const KINDS = [
  { kind: "bar", label: "Bar chart", best_for: "", needs: "", aliases: ["ranking", "top"] },
  { kind: "treemap", label: "Treemap", best_for: "", needs: "", aliases: ["hierarchy", "nested"] },
  { kind: "kpi", label: "KPI card", best_for: "", needs: "", aliases: ["number", "metric"] },
];

test("a slash at the start or after a space opens the menu", () => {
  assert.deepEqual(slashTokenAt("/tre", 4), { query: "tre", start: 0, end: 4 });
  assert.deepEqual(slashTokenAt("sales by /ba", 12), { query: "ba", start: 9, end: 12 });
  assert.deepEqual(slashTokenAt("/", 1), { query: "", start: 0, end: 1 });
});

test("a slash inside a word does not", () => {
  assert.equal(slashTokenAt("revenue/user", 12), null);
});

test("kinds filter by name first, then by alias", () => {
  assert.deepEqual(filterKinds(KINDS, "tree").map((k) => k.kind), ["treemap"]);
  assert.deepEqual(filterKinds(KINDS, "metric").map((k) => k.kind), ["kpi"]);
  assert.equal(filterKinds(KINDS, "").length, 3);
  assert.deepEqual(filterKinds(KINDS, "zzz"), []);
});

test("picking a kind removes the typed token and puts the caret where it was", () => {
  const token = slashTokenAt("sales by /ba region", 12)!;
  assert.deepEqual(removeToken("sales by /ba region", token), { text: "sales by region", caret: 9 });
});
```

In `package.json` scripts, add:

```json
"test": "node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --test tests/*.test.mts"
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd byd-web && npm test`
Expected: FAIL with "Cannot find module ... lib/slash-menu.ts".

- [ ] **Step 3: Implement** (`byd-web/lib/slash-menu.ts`)

```ts
/* The "/" menu's logic, kept free of React and of imports so Node's own test
   runner loads it directly (`npm test`). */

export interface KindOption {
  kind: string;
  label: string;
  best_for: string;
  needs: string;
  aliases: string[];
}

export interface SlashToken {
  query: string;
  start: number;
  end: number;
}

/** The "/word" being typed at the caret: a "/" at the start or after a space. */
export function slashTokenAt(text: string, caret: number): SlashToken | null {
  const before = text.slice(0, caret);
  const match = /(^|\s)\/([\w-]*)$/.exec(before);
  if (!match) return null;
  return { query: match[2], start: caret - match[2].length - 1, end: caret };
}

/** Kinds matching the query: names that start with it, then words or aliases
    that do, then any that contain it. */
export function filterKinds(options: KindOption[], query: string): KindOption[] {
  const q = query.trim().toLowerCase();
  if (!q) return options;
  const rank = (option: KindOption): number => {
    const label = option.label.toLowerCase();
    if (option.kind.startsWith(q) || label.startsWith(q)) return 0;
    const words = [...label.split(/\s+/), ...option.aliases.map((alias) => alias.toLowerCase())];
    if (words.some((word) => word.startsWith(q))) return 1;
    if ([option.kind, ...words].some((word) => word.includes(q))) return 2;
    return -1;
  };
  return options
    .map((option) => ({ option, score: rank(option) }))
    .filter((entry) => entry.score >= 0)
    .sort((a, b) => a.score - b.score)
    .map((entry) => entry.option);
}

/** The text without the typed "/word", and where the caret goes. */
export function removeToken(text: string, token: SlashToken): { text: string; caret: number } {
  const head = text.slice(0, token.start);
  const tail = text.slice(token.end).replace(/^ /, "");
  return { text: head + tail, caret: token.start };
}
```

- [ ] **Step 4: Run the tests, the typecheck and lint**

Run: `cd byd-web && npm test && npx tsc --noEmit -p . && npx eslint lib/slash-menu.ts tests/slash-menu.test.mts`
Expected: 4 tests pass; tsc and eslint print nothing.

- [ ] **Step 5: Commit**

```bash
git add byd-web/lib/slash-menu.ts byd-web/tests/slash-menu.test.mts byd-web/tsconfig.json byd-web/package.json
git commit -m "feat(web): the slash menu's parsing and filtering, with tests

Pure functions run by Node's built-in test runner (npm test); no test
framework added.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The "/" menu in both prompts, sent as structured fields

**Files:**
- Create: `byd-web/lib/chart-kinds.ts`
- Create: `byd-web/components/kind-menu.tsx`
- Modify: `byd-web/lib/blocks.ts` (`generateBlock`, `generateDashboard`)
- Modify: `byd-web/components/report-canvas.tsx`

**Interfaces:**
- Consumes: Task 5's pure functions; `GET /api/v1/chart-kinds` (Task 1); the `chart_kind` and `chart_kinds` request fields (Task 3).
- Produces:
  - `listChartKinds(token) -> Promise<ChartKind[]>`.
  - `loadKindExamples() -> Promise<Record<string, KindExample>>`.
  - `useKindMenu(kinds, onPick)`.
  - `<KindMenu id options active onPick onHighlight placement>` and `<KindChip kind onRemove>`.
  - `KIND_ICONS`.
  - `generateBlock(token, reportId, { prompt, dataSource?, chartKind? })` and `generateDashboard(token, reportId, { brief, chartKinds? }, handlers, signal?)`.

- [ ] **Step 1: Add the client helpers**

`byd-web/lib/chart-kinds.ts`:

```ts
import { authorizedFetch } from "@/lib/backend";
import type { KindOption } from "@/lib/slash-menu";

export type ChartKind = KindOption;

export interface KindExample {
  kind: string;
  title: string;
  figure: Record<string, unknown>;
}

/** The kinds the planner accepts, from the backend, so the UI never offers one it rejects. */
export async function listChartKinds(token: string): Promise<ChartKind[]> {
  return authorizedFetch<ChartKind[]>("/api/v1/chart-kinds", token);
}

/** Charts the model drew, one per kind it managed. A kind it did not draw has none. */
export async function loadKindExamples(): Promise<Record<string, KindExample>> {
  const response = await fetch("/chart-kinds/examples.json", { cache: "no-store" });
  if (!response.ok) return {};
  const examples = (await response.json()) as KindExample[];
  return Object.fromEntries(examples.map((example) => [example.kind, example]));
}
```

In `byd-web/lib/blocks.ts`, change `generateBlock`'s input type to `{ prompt: string; dataSource?: string; chartKind?: string }` and its body to:

```ts
    body: JSON.stringify({
      prompt: input.prompt,
      data_source: input.dataSource ?? null,
      chart_kind: input.chartKind ?? null,
    }),
```

Change `generateDashboard`'s third parameter from `brief: string` to `request: { brief: string; chartKinds?: string[] }`, and its body to:

```ts
      body: JSON.stringify({ brief: request.brief, chart_kinds: request.chartKinds ?? [] }),
```

- [ ] **Step 2: Add the menu component** (`byd-web/components/kind-menu.tsx`)

```tsx
"use client";

import { useMemo, useState, type KeyboardEvent } from "react";
import {
  ChartArea,
  ChartBarStacked,
  ChartCandlestick,
  ChartColumn,
  ChartLine,
  ChartNoAxesColumn,
  ChartPie,
  ChartScatter,
  Funnel,
  Grid3x3,
  Hash,
  LayoutDashboard,
  Sun,
  X,
  type LucideIcon,
} from "lucide-react";
import { Chip } from "@/components/ui";
import type { ChartKind } from "@/lib/chart-kinds";
import { filterKinds, removeToken, slashTokenAt, type SlashToken } from "@/lib/slash-menu";

/* One icon per kind, as a label in the menu. The chart kinds panel shows a
   chart the model drew instead; an icon never stands in for a chart. */
export const KIND_ICONS: Record<string, LucideIcon> = {
  kpi: Hash,
  bar: ChartColumn,
  line: ChartLine,
  area: ChartArea,
  scatter: ChartScatter,
  pie: ChartPie,
  histogram: ChartNoAxesColumn,
  box: ChartCandlestick,
  heatmap: Grid3x3,
  treemap: LayoutDashboard,
  sunburst: Sun,
  funnel: Funnel,
  waterfall: ChartBarStacked,
};

/** The "/" menu's state for one field. Focus never leaves the field: the
    highlighted option is announced through aria-activedescendant. */
export function useKindMenu(
  kinds: ChartKind[],
  onPick: (kind: ChartKind, next: { text: string; caret: number }) => void,
) {
  const [state, setState] = useState<{ token: SlashToken; index: number } | null>(null);
  const options = useMemo(() => (state ? filterKinds(kinds, state.token.query) : []), [kinds, state]);
  const active = state && options.length ? options[Math.min(state.index, options.length - 1)] : null;

  function sync(text: string, caret: number) {
    const token = slashTokenAt(text, caret);
    setState(token ? { token, index: 0 } : null);
  }

  function pick(text: string, kind: ChartKind) {
    if (!state) return;
    onPick(kind, removeToken(text, state.token));
    setState(null);
  }

  /** True when the key belonged to the menu, so the field must not act on it. */
  function keyDown(event: KeyboardEvent, text: string): boolean {
    if (!state) return false;
    if (event.key === "Escape") {
      event.preventDefault();
      setState(null);
      return true;
    }
    if (!options.length) return false;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setState({ ...state, index: (state.index + step + options.length) % options.length });
      return true;
    }
    if ((event.key === "Enter" || event.key === "Tab") && active) {
      event.preventDefault();
      pick(text, active);
      return true;
    }
    return false;
  }

  return {
    open: state !== null,
    options,
    active,
    sync,
    pick,
    keyDown,
    close: () => setState(null),
    highlight: (index: number) => setState((current) => (current ? { ...current, index } : current)),
  };
}

export function KindMenu({
  id,
  options,
  active,
  onPick,
  onHighlight,
  placement = "above",
}: {
  id: string;
  options: ChartKind[];
  active: ChartKind | null;
  onPick: (kind: ChartKind) => void;
  onHighlight: (index: number) => void;
  placement?: "above" | "below";
}) {
  return (
    <ul
      id={id}
      role="listbox"
      aria-label="Chart kinds"
      className={[
        "absolute left-0 right-0 z-30 max-h-72 overflow-y-auto rounded-[var(--r-card)] bg-surface p-1.5 shadow-[var(--lift-2)]",
        placement === "above" ? "bottom-full mb-2" : "top-full mt-2",
      ].join(" ")}
    >
      {options.map((option, index) => {
        const Icon = KIND_ICONS[option.kind] ?? ChartColumn;
        const selected = active?.kind === option.kind;
        return (
          <li
            key={option.kind}
            id={`${id}-${option.kind}`}
            role="option"
            aria-selected={selected}
            onMouseDown={(event) => {
              event.preventDefault(); // keep focus in the field
              onPick(option);
            }}
            onMouseEnter={() => onHighlight(index)}
            className={[
              "flex cursor-pointer items-center gap-3 rounded-[var(--r-control)] px-2.5 py-2",
              selected ? "bg-pine-wash" : "hover:bg-sunken",
            ].join(" ")}
          >
            <Icon size={16} strokeWidth={2.25} className={selected ? "text-pine" : "text-muted"} />
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] font-semibold text-ink">{option.label}</span>
              <span className="block truncate text-[12px] text-muted">{option.best_for}</span>
            </span>
            <span className="shrink-0 text-[12px] text-muted tabular">/{option.kind}</span>
          </li>
        );
      })}
      {options.length === 0 ? (
        <li role="presentation" className="px-2.5 py-2 text-[12.5px] text-muted">
          No chart kind matches
        </li>
      ) : null}
    </ul>
  );
}

export function KindChip({ kind, onRemove }: { kind: ChartKind; onRemove: () => void }) {
  const Icon = KIND_ICONS[kind.kind] ?? ChartColumn;
  return (
    <Chip tone="pine">
      <Icon size={12} strokeWidth={2.25} />
      {kind.label}
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${kind.label}`}
        className="-mr-1 grid size-4 place-items-center rounded-full hover:bg-surface"
      >
        <X size={11} strokeWidth={2.25} />
      </button>
    </Chip>
  );
}
```

- [ ] **Step 3: Wire both prompts in `report-canvas.tsx`**

Imports: add `import { KindChip, KindMenu, useKindMenu } from "@/components/kind-menu";` and `import { listChartKinds, type ChartKind } from "@/lib/chart-kinds";`.

State: add after `const [briefOpen, setBriefOpen] = useState(false);`:

```tsx
  const [kinds, setKinds] = useState<ChartKind[]>([]);
  const [askKind, setAskKind] = useState<ChartKind | null>(null);
  const [briefKinds, setBriefKinds] = useState<ChartKind[]>([]);
  const askMenu = useKindMenu(kinds, (picked, next) => {
    setAskKind(picked);
    setPrompt(next.text);
    requestAnimationFrame(() => askRef.current?.setSelectionRange(next.caret, next.caret));
  });
  const briefMenu = useKindMenu(kinds, (picked, next) => {
    setBriefKinds((current) =>
      current.some((k) => k.kind === picked.kind) ? current : [...current, picked].slice(0, 4),
    );
    setBrief(next.text);
  });

  useEffect(() => {
    if (!token) return;
    listChartKinds(token).then(setKinds).catch(() => setKinds([]));
  }, [token]);
```

In `ask()`, send the kind and clear it after success:

```tsx
      const block = await generateBlock(token, report.id, { prompt: question, chartKind: askKind?.kind });
      setBlocks((current) => [...current, block]);
      setPrompt("");
      setAskKind(null);
```

In `buildDashboard()`, call `generateDashboard(token, report.id, { brief, chartKinds: briefKinds.map((k) => k.kind) }, {` and add `setBriefKinds([]);` after `setSaveState("saved");`.

Replace the brief field (the `<label className="min-w-[14rem] flex-1">` element and its contents) with:

```tsx
            <div className="relative min-w-[14rem] flex-1">
              <label htmlFor="brief-input" className="mb-1.5 block text-[13px] font-semibold text-ink">
                What should this dashboard be about?
              </label>
              {briefKinds.length ? (
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {briefKinds.map((k) => (
                    <KindChip
                      key={k.kind}
                      kind={k}
                      onRemove={() => setBriefKinds((current) => current.filter((c) => c.kind !== k.kind))}
                    />
                  ))}
                </div>
              ) : null}
              <input
                id="brief-input"
                autoFocus
                value={brief}
                role="combobox"
                aria-expanded={briefMenu.open}
                aria-controls="brief-kinds"
                aria-autocomplete="list"
                aria-activedescendant={briefMenu.active ? `brief-kinds-${briefMenu.active.kind}` : undefined}
                onChange={(event) => {
                  setBrief(event.target.value);
                  briefMenu.sync(event.target.value, event.target.selectionStart ?? event.target.value.length);
                }}
                onBlur={briefMenu.close}
                onKeyDown={(event) => {
                  if (briefMenu.keyDown(event, brief)) return;
                  if (event.key === "Enter") void buildDashboard();
                  if (event.key === "Escape") setBriefOpen(false);
                }}
                placeholder="e.g. churn by region — type / to ask for a chart kind"
                className={inputClass}
              />
              {briefMenu.open ? (
                <KindMenu
                  id="brief-kinds"
                  options={briefMenu.options}
                  active={briefMenu.active}
                  onPick={(k) => briefMenu.pick(brief, k)}
                  onHighlight={briefMenu.highlight}
                  placement="below"
                />
              ) : null}
            </div>
```

Replace the ask bar's `<div className="flex items-end gap-2 p-2.5">` block (the textarea and the Add block button) with:

```tsx
            {askKind ? (
              <div className="flex items-center gap-2 px-3 pt-2.5">
                <KindChip kind={askKind} onRemove={() => setAskKind(null)} />
                <span className="text-[12px] text-muted">
                  The model will draw this as a {askKind.label.toLowerCase()}.
                </span>
              </div>
            ) : null}
            <div className="relative flex items-end gap-2 p-2.5">
              {askMenu.open ? (
                <KindMenu
                  id="ask-kinds"
                  options={askMenu.options}
                  active={askMenu.active}
                  onPick={(k) => askMenu.pick(prompt, k)}
                  onHighlight={askMenu.highlight}
                />
              ) : null}
              <textarea
                ref={askRef}
                rows={1}
                value={prompt}
                disabled={busy}
                aria-label="Ask for a chart"
                role="combobox"
                aria-expanded={askMenu.open}
                aria-controls="ask-kinds"
                aria-autocomplete="list"
                aria-activedescendant={askMenu.active ? `ask-kinds-${askMenu.active.kind}` : undefined}
                onFocus={() => setAskFocused(true)}
                onBlur={() => {
                  setAskFocused(false);
                  askMenu.close();
                }}
                onChange={(event) => {
                  setPrompt(event.target.value);
                  askMenu.sync(event.target.value, event.target.selectionStart ?? event.target.value.length);
                }}
                onKeyDown={(event) => {
                  if (askMenu.keyDown(event, prompt)) return;
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void ask();
                  }
                }}
                placeholder="Ask for a chart… type / to pick a chart kind"
                className="max-h-32 min-h-11 w-full resize-none rounded-[var(--r-control)] bg-surface px-3.5 py-3 text-sm text-ink placeholder:text-muted focus:outline-none"
              />
              <Button variant="primary" onClick={ask} disabled={busy || !prompt.trim()} className="shrink-0">
                {busy ? "Working…" : "Add block"}
                {busy ? null : <ArrowUp size={15} strokeWidth={2.25} />}
              </Button>
            </div>
```

- [ ] **Step 4: Typecheck, lint, test**

Run: `cd byd-web && npm test && npx tsc --noEmit -p . && npx eslint components/kind-menu.tsx components/report-canvas.tsx lib/chart-kinds.ts lib/blocks.ts`
Expected: tests pass; tsc and eslint print nothing.

- [ ] **Step 5: Commit**

```bash
git add byd-web/lib/chart-kinds.ts byd-web/components/kind-menu.tsx byd-web/lib/blocks.ts byd-web/components/report-canvas.tsx
git commit -m "feat(web): pick a chart kind with / in the ask bar and the brief

Typing / opens a filtered list of the kinds the planner accepts; up and
down move, Enter or Tab pick, Esc closes, and focus never leaves the
field (aria-activedescendant). A pick becomes a removable chip and travels
as chart_kind or chart_kinds, never as prompt text.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The chart kinds panel, with the model's examples as thumbnails

**Files:**
- Create: `byd-web/components/chart-kinds-panel.tsx`
- Modify: `byd-web/components/plot.tsx` (`interactive` and `compact` props)
- Modify: `byd-web/components/report-canvas.tsx` (toolbar button and panel)

**Interfaces:**
- Consumes: `loadKindExamples` and `ChartKind` (Task 6); `Plot`.
- Produces:
  - `<ChartKindsPanel kinds onClose onUse>`.
  - `Plot({ figure, className, interactive = true, compact = false })`.

- [ ] **Step 1: Give `Plot` a thumbnail mode**

In `plot.tsx`, extend the props to `{ figure; className?; interactive?: boolean; compact?: boolean }`, with defaults `interactive = true` and `compact = false`. In the effect, after `const { data, layout } = themed(figure);`, add:

```tsx
        const shown = compact
          ? {
              ...layout,
              margin: { l: 2, r: 2, t: 2, b: 2 },
              showlegend: false,
              xaxis: { ...((layout.xaxis as Record<string, unknown>) ?? {}), visible: false },
              yaxis: { ...((layout.yaxis as Record<string, unknown>) ?? {}), visible: false },
            }
          : layout;
```

Replace the existing `Plotly.react(host.current, data, layout, { ... })` call with:

```tsx
        Plotly.react(host.current, data, shown, {
          displayModeBar: false,
          responsive: true,
          scrollZoom: false,
          staticPlot: !interactive,
        }).catch((error: unknown) => {
          if (!cancelled) setFailed(error instanceof Error ? error.message : "Could not draw this chart");
        });
```

Change the effect's closing `}, [figure]);` (line 403) to `}, [figure, interactive, compact]);`.

- [ ] **Step 2: Write the panel** (`byd-web/components/chart-kinds-panel.tsx`)

```tsx
"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { Plot } from "@/components/plot";
import { IconButton } from "@/components/ui";
import { loadKindExamples, type ChartKind, type KindExample } from "@/lib/chart-kinds";

/* The chart kinds the model can draw. Each thumbnail is a real chart the model
   drew from sample data (backend/scripts/make_chart_kind_examples.py). A kind it
   has no example for says so rather than showing a stand-in. */
export function ChartKindsPanel({
  kinds,
  onClose,
  onUse,
}: {
  kinds: ChartKind[];
  onClose: () => void;
  onUse: (kind: ChartKind) => void;
}) {
  const [examples, setExamples] = useState<Record<string, KindExample>>({});

  useEffect(() => {
    let live = true;
    loadKindExamples()
      .then((found) => {
        if (live) setExamples(found);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside
      aria-label="Chart kinds"
      className="fixed inset-y-0 right-0 z-40 flex w-[min(380px,100vw)] flex-col bg-surface shadow-[var(--lift-2)] print:hidden"
    >
      <header className="flex items-start justify-between gap-3 px-5 pt-5 pb-3">
        <div>
          <h2 className="text-[15px] font-semibold text-ink">Chart kinds</h2>
          <p className="mt-0.5 text-[12.5px] text-muted">
            What the model can draw. Pick one here, or type / in the ask bar.
          </p>
        </div>
        <IconButton label="Close chart kinds" onClick={onClose}>
          <X size={16} strokeWidth={2.25} />
        </IconButton>
      </header>
      <ul className="app-scroll flex-1 space-y-1.5 px-3 pb-5">
        {kinds.map((kind) => {
          const example = examples[kind.kind];
          return (
            <li key={kind.kind}>
              <button
                type="button"
                onClick={() => onUse(kind)}
                className="flex w-full items-center gap-3 rounded-[var(--r-card)] p-2 text-left transition-colors hover:bg-sunken"
              >
                <span className="block h-16 w-24 shrink-0 overflow-hidden rounded-[var(--r-control)] bg-canvas">
                  {example ? (
                    <Plot figure={example.figure} interactive={false} compact className="h-full w-full" />
                  ) : (
                    <span className="grid h-full place-items-center px-2 text-center text-[11px] text-muted">
                      No example yet
                    </span>
                  )}
                </span>
                <span className="min-w-0">
                  <span className="block text-[13px] font-semibold text-ink">{kind.label}</span>
                  <span className="block text-[12px] text-muted">{kind.best_for}</span>
                  <span className="block text-[11.5px] text-muted">Needs {kind.needs}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
```

- [ ] **Step 3: Open it from the canvas toolbar**

In `report-canvas.tsx`:
- Add `Shapes` to the lucide-react import and `import { ChartKindsPanel } from "@/components/chart-kinds-panel";`.
- Add `const [kindsOpen, setKindsOpen] = useState(false);` next to the other kind state.
- Put this button right before the toolbar's "Note" button:

```tsx
          <Button variant="secondary" onClick={() => setKindsOpen((open) => !open)} aria-expanded={kindsOpen}>
            <Shapes size={15} strokeWidth={2.25} />
            Chart kinds
          </Button>
```

Then add, just before the component's final closing `</div>`:

```tsx
      {kindsOpen ? (
        <ChartKindsPanel
          kinds={kinds}
          onClose={() => setKindsOpen(false)}
          onUse={(k) => {
            setAskKind(k);
            setKindsOpen(false);
            askRef.current?.focus();
          }}
        />
      ) : null}
```

- [ ] **Step 4: Typecheck and lint**

Run: `cd byd-web && npx tsc --noEmit -p . && npx eslint components/chart-kinds-panel.tsx components/plot.tsx components/report-canvas.tsx`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add byd-web/components/chart-kinds-panel.tsx byd-web/components/plot.tsx byd-web/components/report-canvas.tsx
git commit -m "feat(web): a chart kinds panel with the model's own examples

A right-side panel lists every kind the planner accepts with a static
thumbnail of a chart the model drew for it, or 'No example yet'. Picking
one sets the ask bar's kind.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Check it in the browser, then document it

**Files:**
- Modify: `byd-web/DESIGN.md` (§5 Components)
- Modify: `AGENTS.md`

- [ ] **Step 1: Browser check** (in-app browser at `http://localhost:3000`, signed in with a test account on the local stack)

1. Open a report.
2. Click "Chart kinds". The panel lists 13 kinds, with thumbnails for those in `examples.json` and "No example yet" for the rest. Esc closes it.
3. In the ask bar, type `/tre`. The list narrows to Treemap. Press Enter: a "Treemap" chip appears and `/tre` is gone from the text.
4. Type "churn by country" and press Enter. A treemap block appears, and the api log shows `chart_kind` handled through the planner with `chart_type_source: user`.
5. Use `read_page` to confirm the textarea has `role=combobox` with `aria-expanded` and the list has `role=listbox` and options.
6. Open "Generate dashboard", type `/pie` and press Enter, then type "churn". The dashboard includes a pie.

Write down any step that does not behave as described, and fix it in its task before going on.

- [ ] **Step 2: Document**

Add to `byd-web/DESIGN.md` §5:

```markdown
- **KindMenu** (`components/kind-menu.tsx`): the "/" menu. A listbox anchored to its field (above the ask bar, below the brief), filtered as you type; up/down move, Enter or Tab pick, Esc closes. Focus stays in the field and the highlighted option goes through `aria-activedescendant`. Icons label kinds here only.
- **KindChip**: a pine chip with the kind's icon and a remove button; a picked kind always shows as one.
- **ChartKindsPanel** (`components/chart-kinds-panel.tsx`): a 380px right-side panel. Each row is a static thumbnail of a chart the model drew (`public/chart-kinds/examples.json`), the kind's name, what it is best for and what it needs. A kind without an example says "No example yet"; nothing stands in.
```

Add to `AGENTS.md` under "Frontend integration details":

```markdown
- Chart kinds: `GET /api/v1/chart-kinds` serves `planning_contract.CHART_KINDS` with labels (`agents/chart_kinds.py`), so the "/" menu and the chart kinds panel can only offer kinds the planner accepts. A pick travels as `chart_kind` (one chart) or `chart_kinds` (a brief, up to 4), checked at the API (422 otherwise), never as prompt text. One chart in a picked kind goes through `agents/kind_request.py`: the detective picks the table, the planner writes one plan that must be that kind, and the chartist reads it as the `Chart plan:` block lora-v2 was trained on. The panel's thumbnails are figures the model drew (`backend/scripts/make_chart_kind_examples.py` -> `byd-web/public/chart-kinds/examples.json`); regenerate after an adapter change. Frontend logic tests run with `npm test` (Node's own runner, no framework).
```

- [ ] **Step 3: Commit**

```bash
git add byd-web/DESIGN.md AGENTS.md
git commit -m "docs: the / menu, the chart kinds panel, and how a picked kind travels

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
