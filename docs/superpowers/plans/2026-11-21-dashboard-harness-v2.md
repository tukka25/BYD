# Dashboard Harness v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the rule-based dashboard architect with an AI-planned, code-checked flow; build the multi-task v2 training set inside a $35 Claude API budget; prepare — and only after the user's approval, run — the v2 adapter fine-tune on Runpod.

**Architecture:** Three phases. Phase 1 builds the new dashboard flow on today's adapter (lora-v1) with prompts only: a profiler that reads values instead of names, an analyst that proposes directions, a reusable planner that writes every chart plan in one call, code checks with retries, layout by chart type, and a chartist that follows the plan. Phase 2 manufactures training data for exactly those prompts: plans for the 1,897 existing answers, the missing chart kinds, and planning examples written by Claude Opus 5.5. Phase 3 trains one rank-16 adapter on all three jobs on an A100 and brings it home through the existing PEFT→MLX path.

**Tech Stack:** FastAPI + LangChain (`ChatOpenAI` → `mlx_lm server`), pandas 3.1.1, Next.js 16, the Anthropic Python SDK (Message Batches + structured outputs), mlx-lm 0.32.2 (local), transformers 5.23 + peft 0.22 on a Runpod A100.

## Global Constraints

- `chartist-finetune/data/testset.jsonl` is frozen (sha256 `bf385c5940db55f2af6ca48c4d0a6ecf6bdda0257b94c1621a32ab854d5714ff`) and is never regenerated or edited.
- No test-split schema (the 60 in `data/schemas.jsonl` with `"split": "test"`) may appear in any training row. Every exporter runs a leak check and refuses to write on a hit.
- The new planning test set `data/v2/planning_testset.jsonl` is frozen before any v2 training data is generated, and is never regenerated.
- `CLAUDE_API_KEY` lives in the repo-root `.env`; it is never printed, logged or committed. Scripts read it through `chartist-finetune/client.py`.
- v2 API spend is capped at **$35.00** in total (the account holds about $40). Every API script tags its ledger rows `"phase": "v2"`, calls `client.guard()` before every batch, and runs a pilot of at most 20 requests before any full batch.
- Model ids are exactly `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`. Opus 5.5 prices are $4 / $20 per million input / output tokens, cache reads $0.20; Batches are 50% off. Server-side refusal fallbacks are rejected on Batches, so a refused request is dropped and counted, never answered by another model.
- Prompts and checks shared between training and production live in backend contract modules (`chartist_contract.py`, `planning_contract.py`, `profiler.py`) and are loaded by path in the fine-tune repo. No copies.
- The new dashboard flow reads no meaning from column names. Types come from values; meaning comes from the model reading the values.
- LoRA configuration is unchanged from v1: rank 16, alpha 32, dropout 0.05, `target_modules = [q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj]`, linear-attention projections excluded.
- No Runpod resource is created until the user approves Task 19. Rented resources are stopped and deleted as soon as the run finishes.
- Commit after every task (the user's standing rule). Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Backend tests run with `cd backend && PYTHONPATH=. .venv/bin/python -m pytest <path> -v`. Fine-tune tests run with `cd chartist-finetune && .venv/bin/python -m pytest <path> -v`.

## File Structure

**Shared contracts (backend, loaded by path in the fine-tune repo)**
- `backend/app/services/agents/profiler.py` — NEW. Describes a table from its values. pandas + stdlib only.
- `backend/app/services/agents/planning_contract.py` — NEW. Chart kinds, analyst and planner prompts, JSON schemas, `extract_json`, `check_directions`, `check_specs`, `render_directions`. stdlib only.
- `backend/app/services/agents/chartist_contract.py` — MODIFY. Adds `render_spec`, the chartist's task text for a chart plan.
- `chartist-finetune/contract.py` — MODIFY. Loads the two new modules by path and re-exports them.

**Dashboard flow (backend + web)**
- `backend/app/services/agents/planning.py` — NEW. `run_checked`, `propose_directions`, `plan_charts`.
- `backend/app/services/agents/layout.py` — NEW. `Placed`, `lay_out`, `intro_html`.
- `backend/app/services/agents/spec_runner.py` — NEW. Draws one chart from its plan through the existing executor.
- `backend/app/services/agents/dashboard_flow.py` — NEW. `build_dashboard`, a pure event generator.
- `backend/app/services/agents/chartist.py` — MODIFY. `generate_code(..., spec=None)`.
- `backend/app/services/llm.py` — MODIFY. Roles `analyst` and `spec_planner`.
- `backend/app/core/config.py` — MODIFY. `DASHBOARD_PLANNER` ("ai" | "rules").
- `backend/app/api/v1/endpoints/blocks.py` — MODIFY. The dashboard endpoint drives `build_dashboard`; the old rule path stays behind the setting.
- `backend/scripts/smoke_dashboard_flow.py` — NEW. Runs the flow against the real model server, no database.
- `byd-web/lib/blocks.ts`, `byd-web/components/report-canvas.tsx` — MODIFY. `status` and `error` stream events.

**v2 data pipeline (fine-tune repo)**
- `chartist-finetune/client.py` — MODIFY. Opus prices, `phase_spend`, `worst_case_cost`, `guard`.
- `chartist-finetune/gen_requests.py` — NEW. Dashboard requests per schema (Haiku).
- `chartist-finetune/freeze_planning_testset.py` — NEW. Locks the planning test set.
- `chartist-finetune/measure_planning.py` — NEW. End-to-end planning eval on the local model.
- `chartist-finetune/extract_specs.py` — NEW. A plan for each existing answer (Haiku).
- `chartist-finetune/gen_v2_targets.py` — NEW. Funnel, sunburst, waterfall and KPI answers with their plans (Haiku + Sonnet).
- `chartist-finetune/gen_plans.py` — NEW. Analyst and planner examples (Opus).
- `chartist-finetune/gen_spec_code.py` — NEW. Code for Opus's plans (Sonnet).
- `chartist-finetune/export_v2.py` — NEW. Multi-task export with leak and contract checks.
- `chartist-finetune/verify_v2_rows.py` — NEW. Checks every row's prompt/answer split and length with the real tokenizer.
- `chartist-finetune/cloud/RUNBOOK_v2.md` — NEW. The Runpod run, step by step.

## Budget

| Step | Model | Estimate | Script cap |
|---|---|---|---|
| Requests, 180 schemas | Haiku | ~$0.05 | $1.00 |
| Plans for 1,897 answers | Haiku | ~$1.00 | $3.00 |
| Missing kinds, ~570 answers | Haiku + Sonnet | ~$3.00 | $5.00 |
| Planning examples | Opus | sized from a 20-request pilot | $22.00 |
| Code for Opus's plans | Sonnet | ~$3.00 | $4.00 |
| **Total** | | | **$35.00** (`client.V2_BUDGET`) |

---

## Phase 1 — The AI-planned dashboard, on today's adapter

### Task 1: Value-based profiler

**Files:**
- Create: `backend/app/services/agents/profiler.py`
- Test: `backend/tests/test_profiler.py`

**Interfaces:**
- Produces: `KINDS: tuple[str, ...]`; `ColumnProfile(name, kind, distinct, nulls, examples, low, high)`; `TableProfile(name, rows, columns, truncated)` with `.kinds() -> dict[str, str]`; `profile_column(name: str, series: pd.Series) -> ColumnProfile`; `profile_table(name: str, frame: pd.DataFrame) -> TableProfile`; `render_profiles(profiles: list[TableProfile]) -> str`; `columns_by_table(profiles: list[TableProfile]) -> dict[str, dict[str, str]]`.

- [ ] **Step 1: Install pytest in the backend venv**

Run: `cd backend && .venv/bin/pip install pytest`
Expected: `Successfully installed ... pytest-...`

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_profiler.py
import pandas as pd

from app.services.agents.profiler import (
    columns_by_table,
    profile_column,
    profile_table,
    render_profiles,
)


def _saas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "snap_dt": ["2024-01-09", "2025-01-03", "2024-06-30", "2024-03-01"] * 10,
            "cntry_cd": ["DE", "US", "BR", "AU"] * 10,
            "mrr_usd": [2224859.79, 1458369.58, 7799.0, 99.5] * 10,
            "yr": [2021, 2022, 2023, 2024] * 10,
            "row_no": list(range(1, 41)),
            "note": [f"free text number {i}" for i in range(40)],
        }
    )


def test_text_dates_are_found_from_values_not_names():
    column = profile_column("snap_dt", _saas()["snap_dt"])
    assert column.kind == "date"
    assert (column.low, column.high) == ("2024-01-09", "2025-01-03")


def test_codes_are_a_category_with_examples():
    column = profile_column("cntry_cd", _saas()["cntry_cd"])
    assert column.kind == "category"
    assert column.distinct == 4
    assert column.examples == ["AU", "BR", "DE", "US"]


def test_numbers_years_and_ids():
    frame = _saas()
    assert profile_column("mrr_usd", frame["mrr_usd"]).kind == "number"
    assert profile_column("yr", frame["yr"]).kind == "year"
    assert profile_column("row_no", frame["row_no"]).kind == "id"
    assert profile_column("note", frame["note"]).kind == "id"


def test_numbers_stored_as_text_are_not_dates():
    assert profile_column("code", pd.Series(["101", "202", "303"] * 5)).kind == "category"


def test_render_lists_every_column_with_its_kind():
    text = render_profiles([profile_table("saas_metrics", _saas())])
    assert text.startswith("table: saas_metrics (40 rows in sample)")
    assert "snap_dt" in text and "date" in text
    assert "4 values: AU, BR, DE, US" in text


def test_columns_by_table():
    tables = columns_by_table([profile_table("saas_metrics", _saas())])
    assert tables["saas_metrics"]["mrr_usd"] == "number"
    assert tables["saas_metrics"]["snap_dt"] == "date"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_profiler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.agents.profiler'`

- [ ] **Step 4: Write the implementation**

```python
# backend/app/services/agents/profiler.py
"""Describe a table from its values, never its column names.

The rule-based architect decided what a column meant from its spelling:
`snap_dt` was not a date because the name did not say "date", and "country"
never found `cntry_cd`. It missed the date column in 57 of 180 test tables.
This module looks only at values, and the model reads the result, so the
examples `DE, US, BR` tell it what `cntry_cd` is.

Shared on purpose: the backend builds the planner's prompt with it, and
chartist-finetune/contract.py loads this file by path to build training
prompts, so production and training can never describe a table differently.
Keep it to pandas and the standard library.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import pandas as pd

KINDS = ("date", "year", "number", "category", "text", "id")
DATE_SHARE = 0.8          # share of non-empty values that must parse as dates
MAX_CATEGORIES = 30       # a text column with at most this many values is a category
CATEGORY_SHARE = 0.05     # ...or one whose distinct values are under 5% of the rows
MAX_EXAMPLES = 4
MAX_COLUMNS = 40          # a wider table is cut, and the cut is stated in the text


@dataclass
class ColumnProfile:
    name: str
    kind: str
    distinct: int
    nulls: int
    examples: list[str] = field(default_factory=list)
    low: str | None = None
    high: str | None = None


@dataclass
class TableProfile:
    name: str
    rows: int
    columns: list[ColumnProfile] = field(default_factory=list)
    truncated: int = 0

    def kinds(self) -> dict[str, str]:
        return {column.name: column.kind for column in self.columns}


def _short(value: object, limit: int = 24) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _number(value: float) -> str:
    value = float(value)
    return f"{int(value):,}" if value.is_integer() else f"{value:,.2f}"


def _examples(values: pd.Series) -> list[str]:
    counts = values.astype(str).value_counts()
    # Most frequent first, ties broken by the value, so the text is deterministic.
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [_short(value) for value, _ in ranked[:MAX_EXAMPLES]]


def _parse_dates(text: pd.Series) -> pd.Series | None:
    if text.str.fullmatch(r"\s*-?\d+(\.\d+)?\s*").all():
        return None  # numbers stored as text are not dates
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(text, errors="coerce", format="mixed")
    return parsed if parsed.notna().mean() >= DATE_SHARE else None


def profile_column(name: str, series: pd.Series) -> ColumnProfile:
    values = series.dropna()
    nulls = int(series.isna().sum())
    if values.empty:
        return ColumnProfile(name, "text", 0, nulls)
    distinct = int(values.nunique())

    if pd.api.types.is_bool_dtype(series):
        return ColumnProfile(name, "category", distinct, nulls, _examples(values))

    if pd.api.types.is_datetime64_any_dtype(series):
        return ColumnProfile(
            name, "date", distinct, nulls, [], f"{values.min():%Y-%m-%d}", f"{values.max():%Y-%m-%d}"
        )

    if pd.api.types.is_numeric_dtype(series):
        if bool((values % 1 == 0).all()):
            whole = values.astype("int64")
            span = int(whole.max() - whole.min())
            if whole.between(1800, 2200).all() and span <= 250:
                return ColumnProfile(name, "year", distinct, nulls, [], str(whole.min()), str(whole.max()))
            if distinct == len(whole) > 20 and span + 1 == len(whole):
                return ColumnProfile(name, "id", distinct, nulls)
        return ColumnProfile(name, "number", distinct, nulls, [], _number(values.min()), _number(values.max()))

    text = values.astype(str)
    parsed = _parse_dates(text)
    if parsed is not None:
        good = parsed.dropna()
        return ColumnProfile(
            name, "date", distinct, nulls, [], f"{good.min():%Y-%m-%d}", f"{good.max():%Y-%m-%d}"
        )
    if distinct <= MAX_CATEGORIES or distinct <= CATEGORY_SHARE * len(text):
        return ColumnProfile(name, "category", distinct, nulls, _examples(text))
    if distinct == len(text):
        return ColumnProfile(name, "id", distinct, nulls, _examples(text)[:2])
    return ColumnProfile(name, "text", distinct, nulls, _examples(text)[:2])


def profile_table(name: str, frame: pd.DataFrame) -> TableProfile:
    kept = list(frame.columns)[:MAX_COLUMNS]
    return TableProfile(
        name=name,
        rows=int(len(frame)),
        columns=[profile_column(str(column), frame[column]) for column in kept],
        truncated=max(0, len(frame.columns) - MAX_COLUMNS),
    )


def _describe(column: ColumnProfile) -> str:
    if column.kind in ("date", "year", "number"):
        span = f"{column.low} to {column.high}" if column.low is not None else ""
        return f"{column.kind:<9} {span}".rstrip()
    if column.kind == "category":
        return f"category  {column.distinct} values: {', '.join(column.examples)}"
    if column.kind == "id":
        return "id        unique per row"
    if column.examples:
        return f"text      free text, e.g. {', '.join(column.examples)}"
    return "text"


def render_profiles(profiles: list[TableProfile]) -> str:
    blocks = []
    for profile in profiles:
        width = max([len(column.name) for column in profile.columns] + [4])
        lines = [f"table: {profile.name} ({profile.rows:,} rows in sample)"]
        for column in profile.columns:
            lines.append(f"  {column.name:<{width}}  {_describe(column)}")
        if profile.truncated:
            lines.append(f"  ... and {profile.truncated} more columns not shown")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def columns_by_table(profiles: list[TableProfile]) -> dict[str, dict[str, str]]:
    return {profile.name: profile.kinds() for profile in profiles}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_profiler.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/agents/profiler.py backend/tests/test_profiler.py
git commit -m "feat(agents): describe tables from their values, not their names"
```

### Task 2: Planning contract — prompts, kinds and checks

**Files:**
- Create: `backend/app/services/agents/planning_contract.py`
- Test: `backend/tests/test_planning_contract.py`

**Interfaces:**
- Consumes: nothing (stdlib only). `tables` arguments are `dict[str, dict[str, str]]` from `profiler.columns_by_table`.
- Produces: `CHART_KINDS`, `AGGREGATIONS`, `GRAINS`, `SORTS`, `KIND_TRACES: dict[str, set[str]]`, `NO_REQUEST: str`, `SPEC_RULES: str`, `ANALYST_SYSTEM_PROMPT`, `ANALYST_USER_TEMPLATE` (fields `request`, `profiles`), `PLANNER_SYSTEM_PROMPT`, `PLANNER_USER_TEMPLATE` (fields `profiles`, `directions`), `FIX_PROMPT` (field `errors`), `ANALYST_MAX_TOKENS = 1024`, `PLANNER_MAX_TOKENS = 2048`, `DIRECTIONS_SCHEMA`, `SPEC_SCHEMA`, `SPECS_SCHEMA`, `extract_json(text: str | None) -> dict | None`, `check_directions(payload, tables) -> tuple[list[dict], list[str]]`, `check_spec(item: dict, tables) -> tuple[dict | None, list[str]]`, `check_specs(payload, tables) -> tuple[list[dict], list[str]]`, `render_directions(directions: list[dict]) -> str`. A direction is `{"question", "why", "table", "columns"}`; a spec is `{"title", "question", "chart", "table", "x", "y", "group", "agg", "grain", "sort", "top_n"}` with `""` for absent strings and `0` for no `top_n`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_planning_contract.py
import json

from app.services.agents.planning_contract import (
    CHART_KINDS,
    DIRECTIONS_SCHEMA,
    KIND_TRACES,
    SPECS_SCHEMA,
    check_directions,
    check_specs,
    extract_json,
    render_directions,
)

TABLES = {
    "saas": {
        "snap_dt": "date",
        "cntry_cd": "category",
        "plan_tier": "category",
        "churn_cnt": "number",
        "mrr_usd": "number",
        "row_no": "id",
    }
}


def spec(**overrides):
    base = {
        "title": "Churn by country", "question": "Where is churn highest?", "chart": "bar",
        "table": "saas", "x": "cntry_cd", "y": "churn_cnt", "group": "", "agg": "sum",
        "grain": "", "sort": "desc", "top_n": 0,
    }
    base.update(overrides)
    return base


def test_extract_json_finds_the_object_wherever_it_sits():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Sure.\n</think>\n\n{"a": {"b": 2}} trailing') == {"a": {"b": 2}}
    assert extract_json("no json here") is None
    assert extract_json(None) is None


def test_directions_valid():
    payload = {"directions": [{"question": "Where is churn highest?", "why": "asked",
                               "table": "saas", "columns": ["cntry_cd", "churn_cnt"]}]}
    valid, errors = check_directions(payload, TABLES)
    assert errors == [] and valid[0]["columns"] == ["cntry_cd", "churn_cnt"]


def test_directions_name_the_real_columns_when_one_is_wrong():
    payload = {"directions": [{"question": "q", "why": "", "table": "saas", "columns": ["country"]}]}
    valid, errors = check_directions(payload, TABLES)
    assert valid == []
    assert "'country' not in table 'saas'" in errors[0]
    assert "cntry_cd" in errors[0]


def test_directions_unknown_table_and_repeats():
    payload = {"directions": [
        {"question": "q", "why": "", "table": "nope", "columns": ["x"]},
        {"question": "Same", "why": "", "table": "saas", "columns": ["mrr_usd"]},
        {"question": "same", "why": "", "table": "saas", "columns": ["mrr_usd"]},
    ]}
    valid, errors = check_directions(payload, TABLES)
    assert len(valid) == 1
    assert any("table 'nope' does not exist" in e for e in errors)
    assert any("repeats" in e for e in errors)


def test_directions_wrong_shape():
    assert check_directions({"items": []}, TABLES) == ([], ['Reply with {"directions": [...]}.'])


def test_specs_valid_bar():
    valid, errors = check_specs({"charts": [spec()]}, TABLES)
    assert errors == [] and valid[0]["chart"] == "bar"


def test_specs_kind_rules():
    cases = [
        spec(chart="kpi", x="cntry_cd"),                       # kpi has no x
        spec(chart="line", x="cntry_cd"),                      # line needs time or number on x
        spec(chart="line", x="snap_dt", agg="none"),           # trend needs an aggregation
        spec(chart="bar", y="cntry_cd", agg="mean"),           # mean of a category
        spec(chart="histogram", x="cntry_cd", y="", agg="none"),
        spec(grain="month"),                                   # grain on a non-date x
        spec(chart="sankey"),
        spec(x="country"),
    ]
    for case in cases:
        valid, errors = check_specs({"charts": [case]}, TABLES)
        assert valid == [] and errors, case


def test_specs_count_needs_no_measure():
    valid, errors = check_specs({"charts": [spec(chart="kpi", x="", y="", agg="count")]}, TABLES)
    assert errors == [] and valid[0]["agg"] == "count"


def test_specs_time_trend_with_grain():
    valid, errors = check_specs(
        {"charts": [spec(chart="line", x="snap_dt", grain="month", sort="")]}, TABLES
    )
    assert errors == [] and valid[0]["grain"] == "month"


def test_specs_duplicates_dropped():
    valid, errors = check_specs({"charts": [spec(), spec(title="Again")]}, TABLES)
    assert len(valid) == 1 and any("same chart" in e for e in errors)


def test_every_kind_has_traces_and_schemas_are_json():
    assert set(KIND_TRACES) == set(CHART_KINDS)
    json.dumps(DIRECTIONS_SCHEMA)
    json.dumps(SPECS_SCHEMA)


def test_render_directions():
    text = render_directions([{"question": "Where is churn highest?", "why": "asked for",
                               "table": "saas", "columns": ["cntry_cd", "churn_cnt"]}])
    assert text == "1. Where is churn highest? Why: asked for. Table: saas. Columns: cntry_cd, churn_cnt."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_planning_contract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.agents.planning_contract'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/agents/planning_contract.py
"""What the dashboard analyst and planner are told, and how their replies are checked.

A single source of truth, like chartist_contract.py: the backend sends these
exact prompts, and chartist-finetune/contract.py loads this file by path, so
training rows and live calls cannot drift. Standard library only.

The checks are what make an AI planner safe. The rule-based architect existed
because an unchecked model invented columns. Here the model decides, every
column it names is checked against the real table before anything is drawn,
and a failed check goes back to the model as a plain-language error.
"""
from __future__ import annotations

import json
from typing import Any

CHART_KINDS = (
    "kpi", "bar", "line", "area", "scatter", "pie", "histogram", "box",
    "heatmap", "treemap", "sunburst", "funnel", "waterfall",
)
AGGREGATIONS = ("sum", "mean", "median", "count", "min", "max", "none")
GRAINS = ("day", "week", "month", "quarter", "year")
SORTS = ("asc", "desc")
MAX_DIRECTIONS = 8
MAX_TITLE = 80
ANALYST_MAX_TOKENS = 1024
PLANNER_MAX_TOKENS = 2048

# The Plotly trace types a drawn figure may have for each planned kind, so an
# eval can tell whether the chart that rendered is the chart that was planned.
KIND_TRACES: dict[str, set[str]] = {
    "kpi": {"indicator"},
    "bar": {"bar"},
    "line": {"scatter", "scattergl"},
    "area": {"scatter", "scattergl"},
    "scatter": {"scatter", "scattergl"},
    "pie": {"pie"},
    "histogram": {"histogram", "bar"},
    "box": {"box"},
    "heatmap": {"heatmap", "histogram2d"},
    "treemap": {"treemap"},
    "sunburst": {"sunburst"},
    "funnel": {"funnel", "funnelarea"},
    "waterfall": {"waterfall"},
}

NO_REQUEST = "(none: plan from the data)"

ANALYST_SYSTEM_PROMPT = """You plan analytics dashboards. You read a description of the user's tables, built from their actual values, and the user's request, and you decide what the dashboard should answer.

Return JSON: {"directions": [...]} with 4 to 7 directions. Each direction is
{"question": a question the data can answer, in plain words,
 "why": one short sentence on why it matters for this request,
 "table": the table name exactly as given,
 "columns": the exact column names it needs}.

Rules:
- Use only tables and columns from the description, spelled exactly.
- Read meaning from the values, not the names: a column whose values are DE, US, BR holds countries.
- Put the user's request first. With no request, cover the main measures over time and across the main groups.
- Include one headline number when there is a clear measure, one trend when there is a date or year, and breakdowns across the main groups.
- No two directions may ask the same thing.
Reply with the JSON only."""

ANALYST_USER_TEMPLATE = """Request: {request}

Tables:
{profiles}"""

SPEC_RULES = """Each chart plan is
{"title": a short block title, at most 7 words, naming what the chart shows,
 "question": the question it answers,
 "chart": one of kpi, bar, line, area, scatter, pie, histogram, box, heatmap, treemap, sunburst, funnel, waterfall,
 "table": the table name exactly as given,
 "x": column or "", "y": column or "", "group": column or "",
 "agg": one of sum, mean, median, count, min, max, none,
 "grain": day, week, month, quarter, year, or "" (only when x is a date),
 "sort": asc, desc, or "",
 "top_n": how many categories to keep, or 0 for all}.

How to fill it:
- kpi: one number. y = the measure, agg = sum or mean (count to count rows), x = "".
- line or area: a trend. x = a date or year column, y = the measure, agg; grain when x is a date; group = a category for one line per value.
- bar: x = a category (or a date), y = the measure, agg; group = a second category for grouped bars.
- pie: x = the category for the slices, y = the measure, agg.
- scatter: x and y = two number columns, agg = none; group optional.
- histogram: x = one number column, y = "", agg = none.
- box: y = the number column, x = an optional category, agg = none.
- heatmap: x = a category or date, group = another category, y = the measure, agg.
- treemap or sunburst: x = the outer category, group = the inner category, y = the measure, agg.
- funnel: x = the stage category, y = the measure, agg, sort = desc.
- waterfall: x = the category or period, y = the amounts that add up, agg.
- Use sum for totals; use mean for rates, percentages, scores and averages.
- Use only columns from the description, spelled exactly. y must be a number column unless agg is count."""

PLANNER_SYSTEM_PROMPT = (
    "You turn dashboard directions into chart plans: one plan per direction, all in one "
    "reply, so the dashboard has no duplicates and a sensible mix of charts.\n\n"
    'Return JSON: {"charts": [...]}. '
    + SPEC_RULES
    + "\nReply with the JSON only."
)

PLANNER_USER_TEMPLATE = """Tables:
{profiles}

Directions:
{directions}"""

FIX_PROMPT = """Some of that did not check out:
{errors}
Reply again with the whole JSON, fixed."""

_DIRECTION_ITEM = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "why": {"type": "string"},
        "table": {"type": "string"},
        "columns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["question", "why", "table", "columns"],
    "additionalProperties": False,
}

DIRECTIONS_SCHEMA = {
    "type": "object",
    "properties": {"directions": {"type": "array", "items": _DIRECTION_ITEM}},
    "required": ["directions"],
    "additionalProperties": False,
}

SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "question": {"type": "string"},
        "chart": {"type": "string", "enum": list(CHART_KINDS)},
        "table": {"type": "string"},
        "x": {"type": "string"},
        "y": {"type": "string"},
        "group": {"type": "string"},
        "agg": {"type": "string", "enum": list(AGGREGATIONS)},
        "grain": {"type": "string", "enum": ["", *GRAINS]},
        "sort": {"type": "string", "enum": ["", *SORTS]},
        "top_n": {"type": "integer"},
    },
    "required": ["title", "question", "chart", "table", "x", "y", "group", "agg", "grain", "sort", "top_n"],
    "additionalProperties": False,
}

SPECS_SCHEMA = {
    "type": "object",
    "properties": {"charts": {"type": "array", "items": SPEC_SCHEMA}},
    "required": ["charts"],
    "additionalProperties": False,
}

_TIME = {"date", "year"}
_NUMBER = {"number"}
_DIMENSION = {"category", "date", "year"}


def extract_json(text: str | None) -> dict | None:
    """The first JSON object in a reply, wherever it sits."""
    if not text:
        return None
    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _norm(value: Any) -> str:
    return " ".join(str(value if value is not None else "").split())


def check_directions(payload: Any, tables: dict[str, dict[str, str]]) -> tuple[list[dict], list[str]]:
    items = payload.get("directions") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return [], ['Reply with {"directions": [...]}.']
    valid: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()
    for n, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append(f"direction {n} is not an object")
            continue
        question, table = _norm(item.get("question")), _norm(item.get("table"))
        columns = item.get("columns")
        if not question:
            errors.append(f"direction {n} has no question")
            continue
        if table not in tables:
            errors.append(f"direction {n}: table '{table}' does not exist; tables are: {', '.join(tables)}")
            continue
        if not isinstance(columns, list) or not columns:
            errors.append(f"direction {n}: list the columns it needs")
            continue
        names = [_norm(column) for column in columns]
        unknown = [name for name in names if name not in tables[table]]
        if unknown:
            errors.append(
                f"direction {n}: {', '.join(repr(u) for u in unknown)} not in table '{table}'; "
                f"its columns are: {', '.join(tables[table])}"
            )
            continue
        key = question.lower()
        if key in seen:
            errors.append(f"direction {n} repeats an earlier question")
            continue
        seen.add(key)
        valid.append({"question": question, "why": _norm(item.get("why")), "table": table, "columns": names})
    if not valid:
        errors.append("no usable directions")
    return valid[:MAX_DIRECTIONS], errors


def check_spec(item: Any, tables: dict[str, dict[str, str]]) -> tuple[dict | None, list[str]]:
    """One chart plan: the normalised plan, or None and the reasons it failed."""
    if not isinstance(item, dict):
        return None, ["a chart plan must be an object"]
    problems: list[str] = []
    chart = _norm(item.get("chart")).lower()
    table = _norm(item.get("table"))
    agg = _norm(item.get("agg")).lower() or "none"
    grain = _norm(item.get("grain")).lower()
    sort = _norm(item.get("sort")).lower()
    x, y, group = (_norm(item.get(key)) for key in ("x", "y", "group"))
    title = _norm(item.get("title"))[:MAX_TITLE]
    question = _norm(item.get("question"))
    try:
        top_n = int(item.get("top_n") or 0)
    except (TypeError, ValueError):
        top_n = -1

    if chart not in CHART_KINDS:
        problems.append(f"chart '{chart}' is not one of: {', '.join(CHART_KINDS)}")
    if agg not in AGGREGATIONS:
        problems.append(f"agg '{agg}' is not one of: {', '.join(AGGREGATIONS)}")
    if grain and grain not in GRAINS:
        problems.append(f"grain '{grain}' is not one of: {', '.join(GRAINS)}")
    if sort and sort not in SORTS:
        problems.append(f"sort '{sort}' must be asc, desc or empty")
    if top_n < 0:
        problems.append("top_n must be 0 or a positive whole number")
    if not title:
        problems.append("give it a title")
    if table not in tables:
        problems.append(f"table '{table}' does not exist; tables are: {', '.join(tables)}")
        return None, problems
    kinds = tables[table]
    for name, value in (("x", x), ("y", y), ("group", group)):
        if value and value not in kinds:
            problems.append(f"{name} '{value}' is not a column of '{table}'; its columns are: {', '.join(kinds)}")
    if problems:
        return None, problems

    kx, ky, kg = kinds.get(x), kinds.get(y), kinds.get(group)
    measure = ky in _NUMBER or agg == "count"

    def need(condition: bool, message: str) -> None:
        if not condition:
            problems.append(message)

    if chart == "kpi":
        need(not x, "a kpi has no x")
        need(agg != "none", "a kpi needs agg: sum, mean or count")
        need(bool(y) or agg == "count", "a kpi needs y, the measure")
    elif chart in ("line", "area"):
        need(kx in _TIME or kx in _NUMBER, f"a {chart} needs a date, year or number column on x")
        need(measure, f"a {chart} needs a number column as y, or agg count")
        need(not (kx in _TIME and agg == "none"), f"a {chart} over time needs an aggregation, so each period is one point")
    elif chart == "bar":
        need(kx in _DIMENSION, "a bar chart needs a category, date or year column on x")
        need(measure, "a bar chart needs a number column as y, or agg count")
        need(agg != "none", "a bar chart needs an aggregation")
    elif chart == "pie":
        need(kx == "category", "a pie needs a category column on x for the slices")
        need(measure, "a pie needs a number column as y, or agg count")
        need(agg != "none", "a pie needs an aggregation")
    elif chart == "scatter":
        need(kx in _NUMBER and ky in _NUMBER, "a scatter needs two number columns on x and y")
        need(agg == "none", "a scatter plots raw points: agg none")
    elif chart == "histogram":
        need(kx in _NUMBER, "a histogram needs a number column on x")
        need(not y, "a histogram has no y")
        need(agg == "none", "a histogram counts raw values: agg none")
    elif chart == "box":
        need(ky in _NUMBER, "a box plot needs a number column on y")
        need(not x or kx == "category", "a box plot's x, if any, must be a category")
        need(agg == "none", "a box plot shows raw values: agg none")
    elif chart == "heatmap":
        need(kx in _DIMENSION and kg in _DIMENSION, "a heatmap needs two category or date columns, on x and group")
        need(measure, "a heatmap needs a number column as y, or agg count")
        need(agg != "none", "a heatmap needs an aggregation")
    elif chart in ("treemap", "sunburst"):
        need(kx == "category", f"a {chart} needs a category column on x")
        need(not group or kg == "category", f"a {chart}'s inner level (group) must be a category")
        need(measure, f"a {chart} needs a number column as y, or agg count")
        need(agg != "none", f"a {chart} needs an aggregation")
    elif chart == "funnel":
        need(kx == "category", "a funnel needs the stage category on x")
        need(measure, "a funnel needs a number column as y, or agg count")
        need(agg != "none", "a funnel needs an aggregation")
    elif chart == "waterfall":
        need(kx in _DIMENSION, "a waterfall needs a category or period on x")
        need(ky in _NUMBER, "a waterfall needs a number column as y")
        need(agg != "none", "a waterfall needs an aggregation")
    if grain and kx != "date":
        problems.append("grain is only for a date column on x")
    if agg in ("sum", "mean", "median", "min", "max") and ky not in _NUMBER:
        problems.append(f"agg {agg} needs a number column as y; '{y or '(empty)'}' is not one")
    if problems:
        return None, sorted(set(problems), key=problems.index)
    return {
        "title": title, "question": question or title, "chart": chart, "table": table,
        "x": x, "y": y, "group": group, "agg": agg, "grain": grain, "sort": sort, "top_n": top_n,
    }, []


def check_specs(payload: Any, tables: dict[str, dict[str, str]]) -> tuple[list[dict], list[str]]:
    items = payload.get("charts") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return [], ['Reply with {"charts": [...]}.']
    valid: list[dict] = []
    errors: list[str] = []
    seen: set[tuple] = set()
    for n, item in enumerate(items, 1):
        spec, problems = check_spec(item, tables)
        if spec is None:
            errors.extend(f"chart {n}: {problem}" for problem in problems)
            continue
        key = (spec["chart"], spec["table"], spec["x"], spec["y"], spec["group"], spec["agg"], spec["grain"])
        if key in seen:
            errors.append(f"chart {n} is the same chart as an earlier one")
            continue
        seen.add(key)
        valid.append(spec)
    if not valid:
        errors.append("no usable chart plans")
    return valid, errors


def render_directions(directions: list[dict]) -> str:
    lines = []
    for n, direction in enumerate(directions, 1):
        why = f" Why: {direction['why'].rstrip('.')}." if direction.get("why") else ""
        lines.append(
            f"{n}. {direction['question']}{why} Table: {direction['table']}. "
            f"Columns: {', '.join(direction['columns'])}."
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_planning_contract.py -v`
Expected: PASS, 12 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/planning_contract.py backend/tests/test_planning_contract.py
git commit -m "feat(agents): planning contract with checked directions and chart plans"
```

### Task 3: The chartist follows a chart plan

**Files:**
- Modify: `backend/app/services/agents/chartist_contract.py` (append after `chart_type_hint`)
- Modify: `backend/app/services/agents/chartist.py` (imports; `generate_code`)
- Test: `backend/tests/test_render_spec.py`

**Interfaces:**
- Consumes: spec dicts as produced by `planning_contract.check_spec`.
- Produces: `render_spec(spec: dict) -> str`; `ChartistAgent.generate_code(user_query, task_plan, data_context, dataframe_plan=None, spec=None) -> str`, where a given `spec` replaces the task text with `render_spec(spec)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_render_spec.py
from app.services.agents.chartist import ChartistAgent
from app.services.agents.chartist_contract import render_spec

SPEC = {
    "title": "Churn by country", "question": "Where is churn highest?", "chart": "bar",
    "table": "saas", "x": "cntry_cd", "y": "churn_cnt", "group": "", "agg": "sum",
    "grain": "", "sort": "desc", "top_n": 10,
}


def test_render_spec_reads_as_a_plan():
    assert render_spec(SPEC) == (
        "Where is churn highest?\n\n"
        "Chart plan:\n"
        "- chart: bar\n"
        "- x: cntry_cd\n"
        "- y: churn_cnt (sum)\n"
        "- order: descending, top 10\n"
        "- title: Churn by country"
    )


def test_render_spec_count_and_grain():
    text = render_spec({**SPEC, "chart": "line", "x": "snap_dt", "y": "", "agg": "count",
                        "grain": "month", "sort": "", "top_n": 0})
    assert "- y: row count" in text and "- time grain: month" in text and "order" not in text


class _Recorder:
    def __init__(self):
        self.seen = None

    def invoke(self, variables):
        self.seen = variables
        return "import plotly.express as px\nfig = px.bar(df, x='cntry_cd', y='churn_cnt')\nprint(fig.to_json())\n"


def test_generate_code_sends_the_plan_as_the_task():
    recorder = _Recorder()
    agent = ChartistAgent(llm=None, generator=recorder, chart_type_hint_style="off")
    context = {"columns": ["cntry_cd", "churn_cnt"], "dtypes": {}, "sample": []}
    agent.generate_code("ignored question", {"visualization_type": "bar"}, context, spec=SPEC)
    assert recorder.seen["task"] == render_spec(SPEC)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_render_spec.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_spec'`

- [ ] **Step 3: Add `render_spec` to the contract**

Append to `backend/app/services/agents/chartist_contract.py`:

```python
def render_spec(spec: dict) -> str:
    """The chartist's task text for one chart plan.

    The dashboard planner hands the chartist an exact plan, so it no longer has
    to guess the chart type and columns from a question. The v2 training rows are
    built with this same function (re-exported by chartist-finetune/contract.py):
    the plan a model was trained on and the plan the app sends are the same text.
    """
    lines = [str(spec.get("question") or spec.get("title") or "").strip(), "", "Chart plan:"]
    lines.append(f"- chart: {spec['chart']}")
    agg = str(spec.get("agg") or "")
    for key in ("x", "y", "group"):
        value = str(spec.get(key) or "").strip()
        if not value:
            continue
        if key == "y" and agg not in ("", "none"):
            lines.append(f"- y: {value} ({agg})")
        else:
            lines.append(f"- {key}: {value}")
    if not str(spec.get("y") or "").strip() and agg == "count":
        lines.append("- y: row count")
    if spec.get("grain"):
        lines.append(f"- time grain: {spec['grain']}")
    sort, top = str(spec.get("sort") or ""), int(spec.get("top_n") or 0)
    if sort or top:
        parts = (["descending" if sort == "desc" else "ascending"] if sort else []) + (
            [f"top {top}"] if top else []
        )
        lines.append(f"- order: {', '.join(parts)}")
    title = str(spec.get("title") or "").strip()
    if title:
        lines.append(f"- title: {title}")
    return "\n".join(lines)
```

- [ ] **Step 4: Let `generate_code` take a plan**

In `backend/app/services/agents/chartist.py`, add `render_spec` to the import from `chartist_contract`:

```python
from app.services.agents.chartist_contract import (
    CHARTIST_SYSTEM_PROMPT,
    CHARTIST_USER_TEMPLATE,
    HINT_STYLES,
    ContractViolation,
    chart_type_hint,
    render_spec,
    validate_chart_code,
)
```

Replace the signature and the `raw = source.invoke({...})` call in `generate_code`:

```python
    def generate_code(
        self,
        user_query: str,
        task_plan: Dict[str, Any],
        data_context: Dict[str, Any],
        dataframe_plan: Optional[Dict[str, Any]] = None,
        spec: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generates Plotly code for the user's question against this schema.

        With a `spec` (a chart plan from the dashboard planner) the task text is
        the plan itself; the question-only path is unchanged for single blocks.
        """
        viz_type = task_plan.get("visualization_type", "bar")
        try:
            source = self.generator or self.chain
            if source is None:
                raise RuntimeError("chartist has neither a model nor a generator")
            task = (
                render_spec(spec)
                if spec
                else self._task_description(user_query, task_plan, dataframe_plan)
            )
            raw = source.invoke({
                "task": task,
                "columns": str(data_context.get("columns", [])),
                "dtypes": str(data_context.get("dtypes", {})),
                "sample_rows": str(data_context.get("sample", [])),
            })
            return self._sanitize_generated_code(raw, data_context, viz_type)
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_render_spec.py tests/test_chartist_contract.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/agents/chartist_contract.py backend/app/services/agents/chartist.py backend/tests/test_render_spec.py
git commit -m "feat(chartist): draw from a chart plan when the dashboard gives one"
```

### Task 4: The fine-tune repo loads the same contracts

**Files:**
- Modify: `chartist-finetune/contract.py`
- Test: `chartist-finetune/tests/test_planning_sync.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces (re-exported names in `contract`): `render_spec`, `profile_table`, `render_profiles`, `columns_by_table`, `CHART_KINDS`, `KIND_TRACES`, `NO_REQUEST`, `SPEC_RULES`, `ANALYST_SYSTEM_PROMPT`, `ANALYST_USER_TEMPLATE`, `PLANNER_SYSTEM_PROMPT`, `PLANNER_USER_TEMPLATE`, `FIX_PROMPT`, `ANALYST_MAX_TOKENS`, `PLANNER_MAX_TOKENS`, `DIRECTIONS_SCHEMA`, `SPEC_SCHEMA`, `SPECS_SCHEMA`, `extract_json`, `check_directions`, `check_spec`, `check_specs`, `render_directions`.

- [ ] **Step 1: Write the failing test**

```python
# chartist-finetune/tests/test_planning_sync.py
import json
from pathlib import Path

import pandas as pd

import contract


def test_profiles_and_checks_load_from_the_backend():
    frame = pd.read_csv("data/fixtures/s0016.csv")
    profile = contract.profile_table("str_watch_sess", frame)
    assert profile.kinds()["sess_dt"] == "date"
    tables = contract.columns_by_table([profile])
    spec = {"title": "Sessions by country", "question": "q", "chart": "bar", "table": "str_watch_sess",
            "x": "cntry_cd", "y": "sess_cnt", "group": "", "agg": "sum",
            "grain": "", "sort": "", "top_n": 0}
    valid, errors = contract.check_specs({"charts": [spec]}, tables)
    assert errors == [] and contract.render_spec(valid[0]).startswith("q\n\nChart plan:")


def test_every_time_column_in_the_fixtures_is_found_from_values():
    """The rule-based architect missed the date in 57 of these 180 tables."""
    missed = []
    for line in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines():
        schema = json.loads(line)
        kinds = contract.profile_table(schema["table_name"], pd.read_csv(schema["fixture_csv"])).kinds()
        for column in schema["columns"]:
            if column.get("role") == "time" and kinds.get(column["name"]) not in ("date", "year"):
                missed.append((schema["schema_id"], column["name"], kinds.get(column["name"])))
    assert not missed, missed[:10]


def test_prompts_are_the_backend_strings():
    assert "Return JSON" in contract.ANALYST_SYSTEM_PROMPT
    assert contract.SPEC_RULES in contract.PLANNER_SYSTEM_PROMPT
    assert set(contract.KIND_TRACES) == set(contract.CHART_KINDS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_planning_sync.py -v`
Expected: FAIL with `AttributeError: module 'contract' has no attribute 'profile_table'`

- [ ] **Step 3: Load the modules by path**

Append to `chartist-finetune/contract.py`:

```python
render_spec = _backend.render_spec

# The dashboard planner's prompts, checks and table descriptions. Loaded by path
# for the same reason as the chartist contract: a training row and a live call
# must describe a table and ask for a plan with byte-identical text.
_AGENTS = BACKEND_CONTRACT.parent


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(f"backend_{name}", _AGENTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


_profiler = _load_module("profiler")
_planning = _load_module("planning_contract")

profile_table = _profiler.profile_table
render_profiles = _profiler.render_profiles
columns_by_table = _profiler.columns_by_table

for _name in (
    "CHART_KINDS", "KIND_TRACES", "NO_REQUEST", "SPEC_RULES",
    "ANALYST_SYSTEM_PROMPT", "ANALYST_USER_TEMPLATE",
    "PLANNER_SYSTEM_PROMPT", "PLANNER_USER_TEMPLATE", "FIX_PROMPT",
    "ANALYST_MAX_TOKENS", "PLANNER_MAX_TOKENS",
    "DIRECTIONS_SCHEMA", "SPEC_SCHEMA", "SPECS_SCHEMA",
    "extract_json", "check_directions", "check_spec", "check_specs", "render_directions",
):
    globals()[_name] = getattr(_planning, _name)
```

Ensure `import sys` is present at the top of `contract.py` (add it beside `import importlib.util`).

- [ ] **Step 4: Run the fine-tune tests**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_planning_sync.py tests/test_contract_sync.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chartist-finetune/contract.py chartist-finetune/tests/test_planning_sync.py
git commit -m "feat(finetune): load the planning contract and profiler from the backend"
```

### Task 5: Analyst and planner with checked retries

**Files:**
- Create: `backend/app/services/agents/planning.py`
- Test: `backend/tests/test_planning_steps.py`

**Interfaces:**
- Consumes: `planning_contract` (Task 2), `profiler` (Task 1). An `llm` is anything with `.invoke(messages) -> object with .content`.
- Produces: `PlanStep(items: list[dict], errors: list[str], attempts: int, replies: list[str])`; `run_checked(llm, system: str, user: str, check, tables, max_attempts: int = 3) -> PlanStep`; `propose_directions(llm, request: str, profiles: list[TableProfile]) -> PlanStep`; `plan_charts(llm, directions: list[dict], profiles: list[TableProfile]) -> PlanStep`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_planning_steps.py
import json

import pandas as pd

from app.services.agents.planning import plan_charts, propose_directions
from app.services.agents.profiler import profile_table


class Scripted:
    """Replies in order and records every message list it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return type("Reply", (), {"content": reply})()


def _profiles():
    frame = pd.DataFrame({"cntry_cd": ["DE", "US"] * 5, "churn_cnt": range(10)})
    return [profile_table("saas", frame)]


GOOD = json.dumps({"directions": [{"question": "Where is churn highest?", "why": "asked",
                                   "table": "saas", "columns": ["cntry_cd", "churn_cnt"]}]})
BAD = json.dumps({"directions": [{"question": "q", "why": "", "table": "saas", "columns": ["country"]}]})


def test_a_failed_check_goes_back_to_the_model():
    llm = Scripted(BAD, GOOD)
    step = propose_directions(llm, "churn by country", _profiles())
    assert step.attempts == 2 and step.errors == []
    assert step.items[0]["columns"] == ["cntry_cd", "churn_cnt"]
    retry = llm.calls[1][-1].content
    assert "'country' not in table 'saas'" in retry and "Reply again" in retry


def test_the_best_attempt_is_kept_when_none_is_clean():
    llm = Scripted(BAD, BAD, BAD)
    step = propose_directions(llm, "", _profiles())
    assert step.attempts == 3 and step.items == [] and step.errors


def test_a_model_failure_is_an_error_not_a_crash():
    step = propose_directions(Scripted(RuntimeError("server down")), "", _profiles())
    assert step.items == [] and "server down" in step.errors[0]


def test_the_planner_gets_the_directions_and_returns_checked_plans():
    directions = json.loads(GOOD)["directions"]
    charts = json.dumps({"charts": [{"title": "Churn by country", "question": "Where?", "chart": "bar",
                                     "table": "saas", "x": "cntry_cd", "y": "churn_cnt", "group": "",
                                     "agg": "sum", "grain": "", "sort": "desc", "top_n": 0}]})
    llm = Scripted(charts)
    step = plan_charts(llm, directions, _profiles())
    assert step.errors == [] and step.items[0]["title"] == "Churn by country"
    assert "1. Where is churn highest?" in llm.calls[0][1].content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_planning_steps.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.agents.planning'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/agents/planning.py
"""The dashboard's two planning calls, each checked and retried.

`propose_directions` asks what the dashboard should answer; `plan_charts` turns
those answers into chart plans in one call. Both go through `run_checked`: the
reply is parsed, checked against the real tables by planning_contract, and any
problem goes back to the model in plain words, at most twice more. The best
attempt is kept, so a mostly-right plan still ships its good charts.

Messages are built as message objects, never through a prompt template: the
prompts contain JSON braces, which a template would read as variables.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.agents.planning_contract import (
    ANALYST_SYSTEM_PROMPT,
    ANALYST_USER_TEMPLATE,
    FIX_PROMPT,
    NO_REQUEST,
    PLANNER_SYSTEM_PROMPT,
    PLANNER_USER_TEMPLATE,
    check_directions,
    check_specs,
    extract_json,
    render_directions,
)
from app.services.agents.profiler import TableProfile, columns_by_table, render_profiles

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3

Check = Callable[[Any, dict[str, dict[str, str]]], tuple[list[dict], list[str]]]


@dataclass
class PlanStep:
    items: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    attempts: int = 0
    replies: list[str] = field(default_factory=list)


def _text(reply: Any) -> str:
    content = getattr(reply, "content", reply)
    if isinstance(content, list):  # some chat models return content parts
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content or "")


def run_checked(
    llm: Any,
    system: str,
    user: str,
    check: Check,
    tables: dict[str, dict[str, str]],
    max_attempts: int = MAX_ATTEMPTS,
) -> PlanStep:
    messages: list = [SystemMessage(content=system), HumanMessage(content=user)]
    best_items: list[dict] = []
    best_errors: list[str] = ["the model was not called"]
    replies: list[str] = []
    attempts = 0
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        try:
            raw = _text(llm.invoke(messages))
        except Exception as exc:  # noqa: BLE001 - a dead model is an error, not a 500
            logger.warning("[planning] model call failed: %s", exc)
            if not best_items:
                best_errors = [f"the model call failed: {exc}"]
            break
        replies.append(raw)
        items, errors = check(extract_json(raw), tables)
        better = len(items) > len(best_items) or (
            len(items) == len(best_items) and len(errors) < len(best_errors)
        )
        if attempt == 1 or better:
            best_items, best_errors = items, errors
        if items and not errors:
            break
        messages = messages + [
            AIMessage(content=raw),
            HumanMessage(content=FIX_PROMPT.format(errors="\n".join(f"- {e}" for e in errors[:10]))),
        ]
    return PlanStep(best_items, best_errors, attempts, replies)


def propose_directions(llm: Any, request: str, profiles: list[TableProfile]) -> PlanStep:
    user = ANALYST_USER_TEMPLATE.format(
        request=(request or "").strip() or NO_REQUEST, profiles=render_profiles(profiles)
    )
    return run_checked(llm, ANALYST_SYSTEM_PROMPT, user, check_directions, columns_by_table(profiles))


def plan_charts(llm: Any, directions: list[dict], profiles: list[TableProfile]) -> PlanStep:
    user = PLANNER_USER_TEMPLATE.format(
        profiles=render_profiles(profiles), directions=render_directions(directions)
    )
    return run_checked(llm, PLANNER_SYSTEM_PROMPT, user, check_specs, columns_by_table(profiles))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_planning_steps.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/planning.py backend/tests/test_planning_steps.py
git commit -m "feat(agents): analyst and planner calls with checked retries"
```

### Task 6: Layout by chart type and the opening text

**Files:**
- Create: `backend/app/services/agents/layout.py`
- Test: `backend/tests/test_layout.py`

**Interfaces:**
- Consumes: spec dicts; `TableProfile` (Task 1).
- Produces: `INTRO_HEIGHT = 3`; `Placed(spec: dict, x: int, y: int, w: int, h: int)`; `lay_out(specs: list[dict], top: int = 0) -> list[Placed]`; `intro_html(profiles: list[TableProfile], request: str, specs: list[dict]) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_layout.py
import pandas as pd

from app.services.agents.layout import intro_html, lay_out
from app.services.agents.profiler import profile_table


def s(chart, title="t"):
    return {"chart": chart, "title": title}


def test_numbers_first_then_trends_then_pairs():
    placed = lay_out([s("bar", "b1"), s("kpi", "k1"), s("line", "l1"), s("kpi", "k2"), s("pie", "p1")], top=3)
    assert [p.spec["title"] for p in placed] == ["k1", "k2", "l1", "b1", "p1"]
    k1, k2, line, bar, pie = placed
    assert (k1.x, k1.y, k1.w, k1.h) == (0, 3, 4, 4) and (k2.x, k2.w) == (4, 4)
    assert (line.x, line.y, line.w) == (0, 7, 12)
    assert (bar.x, bar.y, bar.w, pie.x, pie.y) == (0, 16, 6, 6, 16)


def test_four_numbers_share_a_row():
    placed = lay_out([s("kpi") for _ in range(4)])
    assert [p.w for p in placed] == [3, 3, 3, 3] and {p.y for p in placed} == {0}


def test_odd_chart_out_takes_the_full_width():
    placed = lay_out([s("bar"), s("pie"), s("box")])
    assert (placed[2].x, placed[2].w) == (0, 12)


def test_intro_is_escaped_and_names_the_charts():
    profile = profile_table("<b>sales</b>", pd.DataFrame({"a": [1, 2, 3]}))
    text = intro_html([profile], "revenue <script>", [s("bar", "Revenue by region")])
    assert "&lt;b&gt;sales&lt;/b&gt;" in text and "&lt;script&gt;" in text
    assert "Revenue by region" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_layout.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.agents.layout'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/agents/layout.py
"""Where each planned chart goes on the 12-column canvas, decided by its type.

Headline numbers along the top, trends at full width, then breakdowns in
pairs: the order a reader scans a dashboard. Only the chart kind is read,
never a column name.
"""
from __future__ import annotations

import html
from dataclasses import dataclass

from app.services.agents.profiler import TableProfile

INTRO_HEIGHT = 3
KPI_HEIGHT = 4
CHART_HEIGHT = 9
WIDE = {"line", "area", "heatmap"}


@dataclass
class Placed:
    spec: dict
    x: int
    y: int
    w: int
    h: int


def lay_out(specs: list[dict], top: int = 0) -> list[Placed]:
    kpis = [spec for spec in specs if spec["chart"] == "kpi"]
    wide = [spec for spec in specs if spec["chart"] in WIDE]
    rest = [spec for spec in specs if spec["chart"] != "kpi" and spec["chart"] not in WIDE]
    placed: list[Placed] = []
    y = top
    for start in range(0, len(kpis), 4):
        row = kpis[start:start + 4]
        width = 3 if len(row) == 4 else 4
        placed.extend(Placed(spec, n * width, y, width, KPI_HEIGHT) for n, spec in enumerate(row))
        y += KPI_HEIGHT
    for spec in wide:
        placed.append(Placed(spec, 0, y, 12, CHART_HEIGHT))
        y += CHART_HEIGHT
    for start in range(0, len(rest), 2):
        pair = rest[start:start + 2]
        width = 12 // len(pair)
        placed.extend(Placed(spec, n * width, y, width, CHART_HEIGHT) for n, spec in enumerate(pair))
        y += CHART_HEIGHT
    return placed


def intro_html(profiles: list[TableProfile], request: str, specs: list[dict]) -> str:
    """The opening text block: composed from facts, so it is never wrong."""
    parts = [
        f"<p><strong>{html.escape(profile.name)}</strong> · {profile.rows:,} rows in sample"
        f" · {len(profile.columns)} fields</p>"
        for profile in profiles
    ]
    if (request or "").strip():
        parts.append(f"<p>Asked for: {html.escape(request.strip())}</p>")
    titles = ", ".join(html.escape(spec["title"]) for spec in specs)
    parts.append(f"<p>This dashboard shows: {titles}.</p>")
    return "".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_layout.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/layout.py backend/tests/test_layout.py
git commit -m "feat(agents): lay dashboards out by chart type"
```

### Task 7: Drawing one chart from its plan

**Files:**
- Modify: `backend/app/services/agents/workflow.py` (`execution_node` body moves into `run_chart_code`)
- Create: `backend/app/services/agents/spec_runner.py`
- Test: `backend/tests/test_spec_runner.py`

**Interfaces:**
- Consumes: `ChartistAgent.generate_code(..., spec=)` (Task 3); `workflow._db_schema(selected)`; `DataDetective(...).get_schema(path)`; `app.utils.executor.SafeExecutor`.
- Produces: `workflow.run_chart_code(data_context: dict, code: str, viz: str, chartist, executor) -> dict` (what `execution_node` returned, now callable without the cached agents, so tests never build model clients); `fallback_kind(chart: str) -> str`; `context_for(source: dict, data_dir: str) -> dict`; `run_spec(spec: dict, source: dict, chartist, data_dir: str, executor=None) -> dict` with keys `code`, `execution_result`, `error`, `data_context`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_spec_runner.py
import pandas as pd

from app.services.agents.chartist import ChartistAgent
from app.services.agents.spec_runner import fallback_kind, run_spec

SPEC = {"title": "Churn by country", "question": "Where is churn highest?", "chart": "bar",
        "table": "saas", "x": "cntry_cd", "y": "churn_cnt", "group": "", "agg": "sum",
        "grain": "", "sort": "desc", "top_n": 0}


class Fixed:
    def __init__(self, code):
        self.code = code

    def invoke(self, variables):
        return self.code


def _csv(tmp_path):
    path = tmp_path / "saas.csv"
    pd.DataFrame({"cntry_cd": ["DE", "US", "DE"], "churn_cnt": [3, 5, 4]}).to_csv(path, index=False)
    return {"type": "file", "name": "saas.csv", "path": str(path)}


GOOD = (
    "import plotly.express as px\n"
    "d = df.groupby('cntry_cd', as_index=False)['churn_cnt'].sum()\n"
    "fig = px.bar(d, x='cntry_cd', y='churn_cnt')\n"
    "print(fig.to_json())\n"
)


def test_a_plan_becomes_a_figure(tmp_path):
    chartist = ChartistAgent(llm=None, generator=Fixed(GOOD), chart_type_hint_style="off")
    result = run_spec(SPEC, _csv(tmp_path), chartist, str(tmp_path))
    assert result["error"] == "" and result["execution_result"]["figure"]["data"][0]["type"] == "bar"


def test_code_that_fails_at_runtime_falls_back(tmp_path):
    broken = "import plotly.express as px\nfig = px.bar(df, x='nope', y='churn_cnt')\nprint(fig.to_json())\n"
    chartist = ChartistAgent(llm=None, generator=Fixed(broken), chart_type_hint_style="off")
    result = run_spec(SPEC, _csv(tmp_path), chartist, str(tmp_path))
    assert result["execution_result"].get("figure") and "fallback" in result["code"]


def test_fallback_kinds():
    assert (fallback_kind("area"), fallback_kind("scatter"), fallback_kind("kpi")) == ("line", "scatter", "bar")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_spec_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.agents.spec_runner'`

- [ ] **Step 3: Split the executor step out of `execution_node`**

In `backend/app/services/agents/workflow.py`, replace the head of `execution_node` (through the `fallback_code = ...` line) so the node only gathers its inputs, and the rest of its body becomes `run_chart_code`, unchanged:

```python
def execution_node(state: AgentState) -> Dict[str, Any]:
    _, _, chartist, executor = _agents()
    return run_chart_code(
        state.get("data_context") or {},
        state.get("code") or "",
        (state.get("plan") or {}).get("visualization_type", "bar"),
        chartist,
        executor,
    )


def run_chart_code(
    data_context: Dict[str, Any],
    code: str,
    viz: str,
    chartist: ChartistAgent,
    executor: SafeExecutor,
) -> Dict[str, Any]:
    """Run chart code against the data it was written for.

    Shared by the question workflow and the dashboard's planned charts, so a
    planned chart gets the same property repair and the same backup chart.
    """
    if not code:
        return {"error": "No chart code was generated."}

    fallback_code = chartist._fallback_plotly_code(data_context, viz)
```

The remaining lines (database load, file load, `_run_executor`) stay exactly as they were, now inside `run_chart_code`.

- [ ] **Step 4: Write the runner**

```python
# backend/app/services/agents/spec_runner.py
"""Draw one chart from its plan: the chartist writes it, the runner runs it.

A plan already names the table and the columns, so the planner and the data
detective, which exist to work those out from a question, are skipped. The
code still goes through the same executor, the same property repair and the
same backup chart as every other chart (`workflow.run_chart_code`).
"""
from __future__ import annotations

from typing import Any

_FALLBACK_KIND = {"line": "line", "area": "line", "scatter": "scatter"}


def fallback_kind(chart: str) -> str:
    """The backup chart's type: the deterministic renderer knows line, scatter and bar."""
    return _FALLBACK_KIND.get(chart, "bar")


def context_for(source: dict, data_dir: str) -> dict:
    """Columns, dtypes and three rows for the chartist, from a file or a table."""
    if source.get("type") == "db":
        from app.services.agents.workflow import _db_schema

        return _db_schema(source)
    from app.services.agents.data_detective import DataDetective

    return DataDetective(data_dir=str(data_dir), llm=None).get_schema(
        str(source.get("path") or source.get("name"))
    )


def run_spec(spec: dict, source: dict, chartist: Any, data_dir: str, executor: Any = None) -> dict[str, Any]:
    from app.services.agents.workflow import run_chart_code
    from app.utils.executor import SafeExecutor

    context = context_for(source, data_dir)
    if "error" in context:
        return {
            "code": "",
            "execution_result": {},
            "error": f"Could not read {source.get('name')}: {context['error']}",
            "data_context": {},
        }
    kind = fallback_kind(spec["chart"])
    code = chartist.generate_code(
        user_query=spec["question"],
        task_plan={"visualization_type": kind},
        data_context=context,
        spec=spec,
    )
    outcome = run_chart_code(context, code, kind, chartist, executor or SafeExecutor())
    return {
        "code": outcome.get("code_run") or code,
        "execution_result": outcome.get("execution_result") or {},
        "error": outcome.get("error") or "",
        "data_context": context,
    }
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_spec_runner.py -v && PYTHONPATH=. .venv/bin/python -c "import app.services.agents.workflow"`
Expected: PASS, 3 tests; the import prints nothing.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/agents/workflow.py backend/app/services/agents/spec_runner.py backend/tests/test_spec_runner.py
git commit -m "feat(agents): draw a chart straight from its plan"
```

### Task 8: The dashboard flow as a pure event generator

**Files:**
- Create: `backend/app/services/agents/dashboard_flow.py`
- Test: `backend/tests/test_dashboard_flow.py`

**Interfaces:**
- Consumes: Tasks 1, 5, 6, 7; `architect.sample_source(source, data_dir, rows)`; `DataDetective._score_candidate(query, candidate)`.
- Produces: `MAX_TABLES = 6`; `SAMPLE_ROWS = 2000`; `TableEntry(label, source, profile)`; `Event(kind: str, data: dict)`; `pick_sources(sources, brief, limit=MAX_TABLES) -> list[dict]`; `profile_sources(sources, data_dir, brief="") -> list[TableEntry]`; `build_dashboard(brief, sources, data_dir, analyst_llm, planner_llm, chartist, top=0) -> Iterator[Event]`. Event kinds and data: `status {label}`, `error {detail}`, `plan {intro: {text, x, y, w, h}, placed: list[Placed], tables: list[TableEntry]}`, `step {index, placed}`, `chart {index, placed, result}`, `skipped {index, placed, reason}`. `index` counts charts from 0.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_dashboard_flow.py
import json

import pandas as pd

from app.services.agents.chartist import ChartistAgent
from app.services.agents.dashboard_flow import build_dashboard, profile_sources


class Scripted:
    def __init__(self, *replies):
        self.replies = list(replies)

    def invoke(self, messages):
        return type("Reply", (), {"content": self.replies.pop(0)})()


class Fixed:
    def invoke(self, variables):
        return (
            "import plotly.express as px\n"
            "d = df.groupby('cntry_cd', as_index=False)['churn_cnt'].sum()\n"
            "fig = px.bar(d, x='cntry_cd', y='churn_cnt')\n"
            "print(fig.to_json())\n"
        )


def _source(tmp_path):
    path = tmp_path / "saas.csv"
    pd.DataFrame({"snap_dt": ["2024-01-09", "2024-02-09"] * 5, "cntry_cd": ["DE", "US"] * 5,
                  "churn_cnt": range(10)}).to_csv(path, index=False)
    return {"type": "file", "name": "saas.csv", "path": str(path)}


DIRECTIONS = json.dumps({"directions": [{"question": "Where is churn highest?", "why": "asked",
                                         "table": "saas.csv", "columns": ["cntry_cd", "churn_cnt"]}]})
CHARTS = json.dumps({"charts": [{"title": "Churn by country", "question": "Where is churn highest?",
                                 "chart": "bar", "table": "saas.csv", "x": "cntry_cd", "y": "churn_cnt",
                                 "group": "", "agg": "sum", "grain": "", "sort": "desc", "top_n": 0}]})


def test_profiles_label_files_by_name(tmp_path):
    entries = profile_sources([_source(tmp_path)], str(tmp_path))
    assert entries[0].label == "saas.csv" and entries[0].profile.kinds()["snap_dt"] == "date"


def test_a_dashboard_is_planned_and_drawn(tmp_path):
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("churn by country", [_source(tmp_path)], str(tmp_path),
                                  Scripted(DIRECTIONS), Scripted(CHARTS), chartist, top=5))
    kinds = [e.kind for e in events]
    assert kinds == ["status", "status", "status", "plan", "step", "chart"]
    plan = events[3].data
    assert plan["intro"]["y"] == 5 and plan["placed"][0].y == 8
    assert events[5].data["result"]["execution_result"]["figure"]


def test_an_unusable_plan_is_an_error_event(tmp_path):
    bad = json.dumps({"directions": [{"question": "q", "why": "", "table": "saas.csv", "columns": ["x"]}]})
    events = list(build_dashboard("", [_source(tmp_path)], str(tmp_path),
                                  Scripted(bad, bad, bad), Scripted(), None))
    assert events[-1].kind == "error" and "what to show" in events[-1].data["detail"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_dashboard_flow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.agents.dashboard_flow'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/agents/dashboard_flow.py
"""Plan and build a dashboard: describe the data, choose directions, plan the
charts in one call, then draw them one by one.

Pure orchestration with no database and no HTTP, so it can be tested with
fake models and real files. The endpoint turns these events into the SSE
stream and the saved blocks.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from app.services.agents.layout import INTRO_HEIGHT, Placed, intro_html, lay_out
from app.services.agents.planning import plan_charts, propose_directions
from app.services.agents.profiler import TableProfile, profile_table
from app.services.agents.spec_runner import run_spec

logger = logging.getLogger(__name__)

MAX_TABLES = 6      # more than this and the description crowds out the request
SAMPLE_ROWS = 2000


@dataclass
class TableEntry:
    label: str
    source: dict
    profile: TableProfile


@dataclass
class Event:
    kind: str
    data: dict


def _label(source: dict, taken: set[str]) -> str:
    base = str(source.get("table") or Path(str(source.get("name") or "table")).name)
    label, n = base, 2
    while label in taken:
        label, n = f"{base}_{n}", n + 1
    return label


def pick_sources(sources: list[dict], brief: str, limit: int = MAX_TABLES) -> list[dict]:
    """All sources when few; otherwise the ones whose words best match the brief."""
    if len(sources) <= limit:
        return list(sources)
    from app.services.agents.data_detective import DataDetective

    detective = DataDetective(llm=None)
    ranked = sorted(
        sources,
        key=lambda s: -detective._score_candidate(
            brief or "", {"name": s.get("name"), "columns": s.get("columns") or []}
        ),
    )
    return ranked[:limit]


def profile_sources(sources: list[dict], data_dir: str, brief: str = "") -> list[TableEntry]:
    from app.services.agents.architect import sample_source

    entries: list[TableEntry] = []
    taken: set[str] = set()
    for source in pick_sources(sources, brief):
        try:
            frame = sample_source(source, data_dir, rows=SAMPLE_ROWS)
        except Exception as exc:  # noqa: BLE001 - one unreadable source must not end the build
            logger.warning("[dashboard] could not read %s: %s", source.get("name"), exc)
            continue
        label = _label(source, taken)
        taken.add(label)
        entries.append(TableEntry(label, source, profile_table(label, frame)))
    return entries


def build_dashboard(
    brief: str,
    sources: list[dict],
    data_dir: str,
    analyst_llm: Any,
    planner_llm: Any,
    chartist: Any,
    top: int = 0,
) -> Iterator[Event]:
    yield Event("status", {"label": "Reading your data"})
    tables = profile_sources(sources, data_dir, brief)
    if not tables:
        yield Event("error", {"detail": "None of this report's sources could be read."})
        return
    profiles = [entry.profile for entry in tables]

    yield Event("status", {"label": "Choosing what to show"})
    directions = propose_directions(analyst_llm, brief, profiles)
    if not directions.items:
        yield Event("error", {"detail": "Could not work out what to show from this data: "
                                        + "; ".join(directions.errors[:3])})
        return

    yield Event("status", {"label": "Planning the charts"})
    charts = plan_charts(planner_llm, directions.items, profiles)
    if not charts.items:
        yield Event("error", {"detail": "Could not plan charts for this data: " + "; ".join(charts.errors[:3])})
        return

    placed = lay_out(charts.items, top=top + INTRO_HEIGHT)
    intro = {"text": intro_html(profiles, brief, charts.items), "x": 0, "y": top, "w": 12, "h": INTRO_HEIGHT}
    yield Event("plan", {"intro": intro, "placed": placed, "tables": tables})

    by_label = {entry.label: entry.source for entry in tables}
    for index, item in enumerate(placed):
        yield Event("step", {"index": index, "placed": item})
        result = run_spec(item.spec, by_label[item.spec["table"]], chartist, data_dir)
        figure = (result.get("execution_result") or {}).get("figure")
        if result.get("error") or not figure:
            yield Event("skipped", {"index": index, "placed": item,
                                    "reason": result.get("error") or "no figure was produced"})
        else:
            yield Event("chart", {"index": index, "placed": item, "result": result})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_dashboard_flow.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/dashboard_flow.py backend/tests/test_dashboard_flow.py
git commit -m "feat(agents): the dashboard flow as a testable event generator"
```

### Task 9: The endpoint, the model roles and the canvas

**Files:**
- Modify: `backend/app/core/config.py` (after `CHARTIST_CHART_TYPE_HINT`)
- Modify: `backend/app/services/llm.py` (`Role`, `_MAX_TOKENS`)
- Modify: `backend/app/api/v1/endpoints/blocks.py` (`generate_whole_dashboard`)
- Create: `backend/scripts/smoke_dashboard_flow.py`
- Modify: `byd-web/lib/blocks.ts` (`DashboardProgress`, `dispatch`)
- Modify: `byd-web/components/report-canvas.tsx` (the `generateDashboard` handlers)

**Interfaces:**
- Consumes: `build_dashboard` and `Event` (Task 8); `ANALYST_MAX_TOKENS`, `PLANNER_MAX_TOKENS` (Task 2).
- Produces: setting `DASHBOARD_PLANNER: str = "ai"`; LLM roles `"analyst"` and `"spec_planner"`; SSE events `status {label}` and `error {detail}` in addition to the existing `plan`, `step`, `block`, `skipped`, `done`.

- [ ] **Step 1: Add the setting**

In `backend/app/core/config.py`, after the `CHARTIST_CHART_TYPE_HINT` line:

```python
    # "ai": the dashboard is planned by the analyst and planner models and checked
    # by code (agents/dashboard_flow.py). "rules": the old name-based architect,
    # kept only as a switch to roll back to.
    DASHBOARD_PLANNER: str = "ai"
```

- [ ] **Step 2: Add the model roles**

In `backend/app/services/llm.py`:

```python
from app.services.agents.planning_contract import ANALYST_MAX_TOKENS, PLANNER_MAX_TOKENS
```

```python
Role = Literal["planner", "chartist", "detective", "narrator", "analyst", "spec_planner"]
```

```python
_MAX_TOKENS = {
    "planner": 256,
    # Shared with the eval and the A/B harness, so they score what the app runs.
    "chartist": CHARTIST_MAX_TOKENS,
    "detective": 512,
    "narrator": 128,
    # The dashboard's planning calls write whole JSON plans; shared with the
    # planning eval through planning_contract.
    "analyst": ANALYST_MAX_TOKENS,
    "spec_planner": PLANNER_MAX_TOKENS,
}
# The dashboard's planning calls answer in JSON with thinking switched off, per
# request (mlx_lm server reads chat_template_kwargs). On base weights with
# thinking on, Qwen3.5 opens with a reasoning essay and never reaches the JSON
# inside the cap (measured for the planner, data/role_measure.json), and the
# adapter was trained on answers that follow a closed think block, which is
# exactly what this prompt ends with. measure_planning.py sends the same flag.
_NO_THINKING = {"analyst", "spec_planner"}
_JSON_ROLES = {"planner", "analyst", "spec_planner"}
```

In `_ollama`, constrain every JSON role:

```python
        format="json" if role in _JSON_ROLES else "",
```

In `_mlx`, pass the flag:

```python
    extra = (
        {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
        if role in _NO_THINKING
        else {}
    )
    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=settings.MLX_API_KEY,
        temperature=_TEMPERATURE,
        max_tokens=_MAX_TOKENS[role],
        timeout=settings.MLX_TIMEOUT_SECONDS,
        **extra,
    )
```

- [ ] **Step 3: Drive the endpoint from the flow**

In `backend/app/api/v1/endpoints/blocks.py`, add imports:

```python
from app.services.agents.dashboard_flow import build_dashboard
from app.services.agents.workflow import _agents
```

Rename the existing function body into a helper that keeps the old behaviour, and make the endpoint choose. Replace `async def generate_whole_dashboard(...)` with:

```python
@router.post("/{dashboard_id}/blocks/dashboard")
async def generate_whole_dashboard(
    dashboard_id: str,
    payload: DashboardBriefRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Plan a dashboard from the data, then build it block by block, streamed."""
    report = _owned_report(db, dashboard_id, current_user)
    sources = _user_sources(db, report)
    if not sources:
        raise HTTPException(
            status_code=400,
            detail="This report has no data to plan from. Add a file or a database first.",
        )
    brief = (payload.brief if payload else "").strip()
    mode = (settings.DASHBOARD_PLANNER or "ai").strip().lower()
    if mode == "rules":
        return await _rules_dashboard(report, sources, brief, current_user, db)
    if mode != "ai":
        raise HTTPException(status_code=500, detail=f"DASHBOARD_PLANNER must be 'ai' or 'rules', got {mode!r}")
    return _ai_dashboard(report, sources, brief, current_user, db)


def _ai_dashboard(report, sources, brief, current_user, db):
    base_row = _next_row(db, report.id)
    flow = build_dashboard(
        brief, sources, settings.UPLOAD_DIR,
        get_llm("analyst"), get_llm("spec_planner"), _agents()[2], top=base_row,
    )

    async def events():
        iterator = iter(flow)
        total = 0
        while True:
            event = await asyncio.to_thread(next, iterator, None)
            if event is None:
                break
            if event.kind == "status":
                yield _sse("status", event.data)
            elif event.kind == "error":
                yield _sse("error", event.data)
                return
            elif event.kind == "plan":
                intro, placed = event.data["intro"], event.data["placed"]
                total = len(placed) + 1
                sections = [{"index": 0, "kind": "text", "label": "About this data",
                             "x": intro["x"], "y": intro["y"], "w": intro["w"], "h": intro["h"]}]
                sections += [
                    {"index": n + 1, "kind": "chart", "label": p.spec["title"],
                     "x": p.x, "y": p.y, "w": p.w, "h": p.h}
                    for n, p in enumerate(placed)
                ]
                names = ", ".join(entry.label for entry in event.data["tables"])
                yield _sse("plan", {"total": total, "source": names, "brief": brief, "sections": sections})
                block = ReportBlock(
                    dashboard_id=report.id, user_id=current_user.id, kind=BlockKind.TEXT,
                    title="About this data", text_body=intro["text"],
                    x=intro["x"], y=intro["y"], w=intro["w"], h=intro["h"],
                )
                db.add(block)
                db.commit()
                db.refresh(block)
                yield _sse("block", _to_response(block).model_dump(mode="json"))
            elif event.kind == "step":
                placed = event.data["placed"]
                yield _sse("step", {"index": event.data["index"] + 1, "total": total, "label": placed.spec["title"]})
            elif event.kind == "skipped":
                placed = event.data["placed"]
                yield _sse("skipped", {"index": event.data["index"] + 1, "label": placed.spec["title"],
                                       "reason": event.data["reason"]})
            elif event.kind == "chart":
                placed, result = event.data["placed"], event.data["result"]
                spec = placed.spec
                try:
                    figure = decode_typed_arrays(result["execution_result"]["figure"])
                    code = result.get("code") or ""
                    context = result.get("data_context") or {}
                    block = ReportBlock(
                        dashboard_id=report.id, user_id=current_user.id,
                        kind=BlockKind.METRIC if _indicator_title(figure) is not None else BlockKind.CHART,
                        title=spec["title"][:255], prompt=spec["question"], code=code,
                        figure_json=json.dumps(figure), source_name=context.get("filename"),
                        chart_type=spec["chart"], used_fallback=FALLBACK_SIGNATURE in code,
                        x=placed.x, y=placed.y, w=placed.w, h=placed.h,
                    )
                    db.add(block)
                    db.commit()
                    db.refresh(block)
                    yield _sse("block", _to_response(block).model_dump(mode="json"))
                except Exception as exc:  # noqa: BLE001 - one bad block must not end the build
                    db.rollback()
                    logger.exception("[dashboard] block %s failed", spec["title"])
                    yield _sse("skipped", {"index": event.data["index"] + 1, "label": spec["title"], "reason": str(exc)})
        yield _sse("done", {"total": total})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

Then turn the old body into `_rules_dashboard`: define `async def _rules_dashboard(report, sources, brief, current_user, db):` and move into it everything the old endpoint did after `sources`/`brief` were known — from `source = sources[0]` through `return StreamingResponse(...)` — unchanged.

- [ ] **Step 4: Compile and run the backend tests**

Run: `cd backend && .venv/bin/python -m py_compile app/api/v1/endpoints/blocks.py app/services/llm.py app/core/config.py && PYTHONPATH=. .venv/bin/python -c "import app.api.v1.endpoints.blocks" && PYTHONPATH=. .venv/bin/python -m pytest tests -v`
Expected: no output from the compile and import; all tests PASS.

- [ ] **Step 5: Show planning progress on the canvas**

In `byd-web/lib/blocks.ts`, add to the `DashboardProgress` interface:

```ts
  onStatus?: (status: { label: string }) => void;
```

and in `dispatch`, before the `plan` branch:

```ts
    if (event === "status") handlers.onStatus?.(payload as never);
    else if (event === "error") {
      // Thrown inside the read loop, so it leaves generateDashboard like an HTTP error.
      throw new Error((payload as { detail?: string }).detail ?? "Could not plan this dashboard.");
    } else if (event === "plan") handlers.onPlan?.(payload as never);
```

(and drop the old leading `if (event === "plan")` so the chain stays one `if / else if`).

In `byd-web/components/report-canvas.tsx`, in the `generateDashboard(token, report.id, brief, { ... })` handlers, add:

```tsx
        onStatus: (status) => setBuilding({ done: 0, total: 0, label: status.label }),
```

- [ ] **Step 6: Lint and type-check the web app**

Run: `cd byd-web && npm run lint && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Write the smoke script**

```python
# backend/scripts/smoke_dashboard_flow.py
"""Run the AI dashboard flow on one file against the real model server.

No database and no web server: it drives agents/dashboard_flow.build_dashboard
with the same LLM roles the endpoint uses and prints what happens.

    cd backend && LLM_BACKEND=mlx MLX_BASE_URL=http://127.0.0.1:8080/v1 \
      PYTHONPATH=. .venv/bin/python scripts/smoke_dashboard_flow.py PATH.csv "brief"
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from app.services.agents.dashboard_flow import build_dashboard
from app.services.agents.workflow import _agents
from app.services.llm import get_llm


def main() -> int:
    path, brief = Path(sys.argv[1]).resolve(), (sys.argv[2] if len(sys.argv) > 2 else "")
    source = {"type": "file", "name": path.name, "path": str(path)}
    started = time.perf_counter()
    rendered = 0
    for event in build_dashboard(brief, [source], str(path.parent),
                                 get_llm("analyst"), get_llm("spec_planner"), _agents()[2]):
        elapsed = time.perf_counter() - started
        if event.kind == "plan":
            print(f"[{elapsed:5.1f}s] plan:")
            for p in event.data["placed"]:
                s = p.spec
                print(f"    {s['chart']:<9} {s['title']!r} x={s['x']!r} y={s['y']!r} group={s['group']!r} "
                      f"agg={s['agg']} grain={s['grain']!r} at ({p.x},{p.y},{p.w}x{p.h})")
        elif event.kind == "chart":
            rendered += 1
            print(f"[{elapsed:5.1f}s] drew {event.data['placed'].spec['title']!r}")
        elif event.kind == "skipped":
            print(f"[{elapsed:5.1f}s] skipped {event.data['placed'].spec['title']!r}: {event.data['reason'][:120]}")
        else:
            print(f"[{elapsed:5.1f}s] {event.kind}: {event.data}")
    print(f"rendered {rendered} charts in {time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 8: Run the smoke against the real adapter**

Start the model server (adapter loaded, localhost only):
`cd chartist-finetune && .venv/bin/python -m mlx_lm server --model models/qwen3.5-9b-4bit --adapter-path runs/adapters-mlx --host 127.0.0.1 --port 8080`

In a second shell:
`cd backend && LLM_BACKEND=mlx MLX_BASE_URL=http://127.0.0.1:8080/v1 PYTHONPATH=. .venv/bin/python scripts/smoke_dashboard_flow.py ../chartist-finetune/data/fixtures/s0016.csv "watch time by country"`
Expected: status lines, a plan whose charts use `sess_dt` for any trend and `cntry_cd` for the country breakdown (neither name says "date" or "country"), and at least one `drew` line. Record the output in the commit message.

- [ ] **Step 9: Commit**

```bash
git add backend/app/core/config.py backend/app/services/llm.py backend/app/api/v1/endpoints/blocks.py backend/scripts/smoke_dashboard_flow.py byd-web/lib/blocks.ts byd-web/components/report-canvas.tsx
git commit -m "feat(dashboard): plan dashboards with the analyst and planner, checked by code"
```

### Task 10: Budget guard and Opus prices in the API client

**Files:**
- Modify: `chartist-finetune/client.py`
- Test: `chartist-finetune/tests/test_budget.py`

**Interfaces:**
- Produces: `OPUS = "claude-opus-5-5"`; `PRICES[OPUS] = (4.00, 20.00, 0.20, 5.00)`; `V2_BUDGET = 35.0`; `phase_spend(phase: str = "v2", ledger: Path = LEDGER) -> float`; `worst_case_cost(model: str, n: int, input_tokens: int, max_tokens: int) -> float`; `guard(label: str, planned_cost: float, cap: float = V2_BUDGET, phase: str = "v2", ledger: Path = LEDGER) -> None` (raises `SystemExit` past the cap). `record_spend` writes to `LEDGER`.

- [ ] **Step 1: Write the failing test**

```python
# chartist-finetune/tests/test_budget.py
import json

import pytest

import client


def _ledger(tmp_path, rows):
    path = tmp_path / "spend.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_phase_spend_counts_only_that_phase(tmp_path):
    path = _ledger(tmp_path, [{"cost_usd": 5.0}, {"cost_usd": 1.25, "phase": "v2"}, {"cost_usd": 0.5, "phase": "v2"}])
    assert client.phase_spend("v2", path) == 1.75


def test_guard_refuses_past_the_cap(tmp_path):
    path = _ledger(tmp_path, [{"cost_usd": 34.0, "phase": "v2"}])
    client.guard("ok", 0.5, cap=35.0, ledger=path)
    with pytest.raises(SystemExit):
        client.guard("too much", 2.0, cap=35.0, ledger=path)


def test_worst_case_is_batched_and_uses_output_price():
    # 10 requests x (1,000 in at $4 + 16,000 out at $20) / 1M x 0.5
    assert client.worst_case_cost(client.OPUS, 10, 1000, 16000) == pytest.approx(1.62)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_budget.py -v`
Expected: FAIL with `AttributeError: module 'client' has no attribute 'phase_spend'`

- [ ] **Step 3: Write the implementation**

In `chartist-finetune/client.py`, add `OPUS` beside the other model ids and its prices:

```python
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"
OPUS = "claude-opus-5-5"

# USD per 1M tokens: (input, output, cache_read, cache_write).
# cache_write is 1.25x base input (5-minute TTL). Haiku's cache_read rate is a
# 0.1x-of-base ESTIMATE, not a published figure from the plan. Opus 5.5 from the
# claude-api pricing table (2026-11-03): $4 / $20, cache reads $0.20.
PRICES = {
    SONNET: (2.00, 10.00, 0.10, 2.50),
    HAIKU: (0.10, 0.50, 0.01, 0.125),
    OPUS: (4.00, 20.00, 0.20, 5.00),
}

LEDGER = Path("runs/spend.jsonl")
# The whole v2 data budget. The account holds about $40; this leaves room.
V2_BUDGET = 35.0
```

Change `record_spend` to write to `LEDGER` (replace `ledger = Path("runs/spend.jsonl")` with `ledger = LEDGER`), and append:

```python
def phase_spend(phase: str = "v2", ledger: Path = LEDGER) -> float:
    """What a phase has cost so far, from the ledger every batch writes to."""
    if not ledger.is_file():
        return 0.0
    total = 0.0
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("phase") == phase:
                total += float(row.get("cost_usd", 0.0))
    return round(total, 6)


def worst_case_cost(model: str, n: int, input_tokens: int, max_tokens: int) -> float:
    """A batch's cost if every reply ran to max_tokens: the guard's default estimate."""
    rate_in, rate_out, _, _ = PRICES[model]
    return round(n * (input_tokens * rate_in + max_tokens * rate_out) / 1_000_000 * 0.5, 4)


def guard(label: str, planned_cost: float, cap: float = V2_BUDGET, phase: str = "v2",
          ledger: Path = LEDGER) -> None:
    """Refuse to start a batch that could take the phase past its cap."""
    spent = phase_spend(phase, ledger)
    if spent + planned_cost > cap:
        raise SystemExit(
            f"[{label}] refusing: {phase} spend ${spent:.2f} + planned ${planned_cost:.2f} "
            f"would pass the ${cap:.2f} cap"
        )
    print(f"[{label}] budget ok: {phase} spent ${spent:.2f}, planned up to ${planned_cost:.2f}, cap ${cap:.2f}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_budget.py tests/test_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chartist-finetune/client.py chartist-finetune/tests/test_budget.py
git commit -m "feat(finetune): Opus prices and a hard v2 budget guard"
```

### Task 11: Dashboard requests, and the frozen planning test set

**Files:**
- Create: `chartist-finetune/gen_requests.py`
- Create: `chartist-finetune/freeze_planning_testset.py`
- Test: `chartist-finetune/tests/test_freeze_planning.py`

**Interfaces:**
- Consumes: `client.json_request`, `client.run_batch`, `client.record_spend`, `client.guard`, `client.worst_case_cost` (Task 10); `contract.profile_table`, `contract.render_profiles` (Task 4).
- Produces: `data/v2/requests.jsonl` rows `{request_id, schema_id, split, request}`; `data/v2/planning_testset.jsonl` (test split only, one model request and one empty request per schema) and `data/v2/planning_testset.sha256`; `freeze_planning_testset.select(rows) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# chartist-finetune/tests/test_freeze_planning.py
import freeze_planning_testset as freeze


def test_keeps_one_written_and_one_empty_request_per_test_schema():
    rows = [
        {"request_id": "a1", "schema_id": "s1", "split": "test", "request": "churn by country"},
        {"request_id": "a2", "schema_id": "s1", "split": "test", "request": "is revenue growing"},
        {"request_id": "a3", "schema_id": "s1", "split": "test", "request": ""},
        {"request_id": "b1", "schema_id": "s2", "split": "train", "request": "x"},
    ]
    kept = freeze.select(rows)
    assert [r["request_id"] for r in kept] == ["a1", "a3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_freeze_planning.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'freeze_planning_testset'`

- [ ] **Step 3: Write `freeze_planning_testset.py`**

```python
#!/usr/bin/env python3
"""Lock the planning test set before any v2 training data exists.

One written request and the empty request for each of the 60 test-split
schemas. Like data/testset.jsonl for the chartist, it has no answers: the
planning eval scores plans by checking them against the real tables and by
drawing them. This script refuses to overwrite an existing set.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SOURCE = Path("data/v2/requests.jsonl")
TESTSET = Path("data/v2/planning_testset.jsonl")
DIGEST = Path("data/v2/planning_testset.sha256")


def select(rows: list[dict]) -> list[dict]:
    kept: list[dict] = []
    written: set[str] = set()
    empty: set[str] = set()
    for row in rows:
        if row["split"] != "test":
            continue
        if row["request"] and row["schema_id"] not in written:
            written.add(row["schema_id"])
            kept.append(row)
        elif not row["request"] and row["schema_id"] not in empty:
            empty.add(row["schema_id"])
            kept.append(row)
    return kept


def main() -> int:
    if TESTSET.exists():
        raise SystemExit(f"refusing to overwrite the frozen planning test set {TESTSET}")
    rows = [json.loads(l) for l in SOURCE.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept = select(rows)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in kept)
    TESTSET.write_text(text, encoding="utf-8")
    DIGEST.write_text(hashlib.sha256(text.encode("utf-8")).hexdigest() + "\n", encoding="utf-8")
    print(f"froze {len(kept)} rows from {len({r['schema_id'] for r in kept})} test schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Write `gen_requests.py`**

```python
#!/usr/bin/env python3
"""Write the dashboard requests the planner is trained and tested on.

For each schema, Haiku writes requests a real user would type into "Generate
dashboard" for that table, in different styles. One empty request per schema
is added without a model, because "just build me a dashboard" is the most
common request of all. Test-split schemas get their own requests, which
freeze_planning_testset.py locks before any training data exists.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import client
from contract import profile_table, render_profiles

SYSTEM = """You write the requests a business user types into a dashboard tool's "Generate dashboard" box, for one table.

Write the requested number of requests, each in a different style:
- a focused brief naming a measure and a breakdown, like "churn by country"
- a goal, like "is revenue growing"
- a comparison, like "compare plans by retention"
- a broad ask, like "an overview for the weekly ops meeting"
Use everyday words, not the column names. Each request under 12 words.
Reply as JSON: {"requests": [...]}"""

SCHEMA = {
    "type": "object",
    "properties": {"requests": {"type": "array", "items": {"type": "string"}}},
    "required": ["requests"],
    "additionalProperties": False,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-per-schema", type=int, default=3)
    ap.add_argument("--test-per-schema", type=int, default=2)
    ap.add_argument("--limit-schemas", type=int, default=None, help="pilot")
    ap.add_argument("--max-spend", type=float, default=1.00)
    ap.add_argument("--out", default="data/v2/requests.jsonl")
    args = ap.parse_args()

    schemas = [json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l]
    if args.limit_schemas:
        schemas = schemas[: args.limit_schemas]
    requests = []
    for schema in schemas:
        n = args.train_per_schema if schema["split"] == "train" else args.test_per_schema
        profile = profile_table(schema["table_name"], pd.read_csv(schema["fixture_csv"]))
        user = f"Domain: {schema['domain']}\nNumber of requests: {n}\n\n{render_profiles([profile])}"
        requests.append(client.json_request(schema["schema_id"], client.HAIKU, SYSTEM, user, SCHEMA,
                                            max_tokens=1500, effort="low"))
    client.guard("requests", min(args.max_spend, client.worst_case_cost(client.HAIKU, len(requests), 1500, 1500)))
    outcome = client.run_batch(requests, label="v2-requests")
    client.record_spend("v2-requests", client.HAIKU, outcome.usage, {"phase": "v2", "requests": len(requests)})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out.open("w", encoding="utf-8") as handle:
        for schema in schemas:
            wanted = args.train_per_schema if schema["split"] == "train" else args.test_per_schema
            got = [r.strip() for r in outcome.payloads.get(schema["schema_id"], {}).get("requests", []) if r.strip()]
            for n, text in enumerate(got[:wanted] + [""]):
                handle.write(json.dumps({"request_id": f"{schema['schema_id']}-r{n}", "schema_id": schema["schema_id"],
                                         "split": schema["split"], "request": text}, ensure_ascii=False) + "\n")
                written += 1
    print(f"wrote {written} requests for {len(schemas)} schemas; refusals {outcome.refusals}, unparsed {outcome.unparsed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the test, then the pilot, then the full run and the freeze**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_freeze_planning.py -v` — Expected: PASS.
Run: `cd chartist-finetune && .venv/bin/python gen_requests.py --limit-schemas 3 --out data/v2/requests_pilot.jsonl` — Expected: about 12 rows; read them and confirm they sound like real requests.
Run: `cd chartist-finetune && .venv/bin/python gen_requests.py` — Expected: `wrote ~660 requests for 180 schemas`.
Run: `cd chartist-finetune && .venv/bin/python freeze_planning_testset.py` — Expected: `froze 120 rows from 60 test schemas`.

- [ ] **Step 6: Commit**

```bash
git add chartist-finetune/gen_requests.py chartist-finetune/freeze_planning_testset.py chartist-finetune/tests/test_freeze_planning.py chartist-finetune/data/v2/requests.jsonl chartist-finetune/data/v2/planning_testset.jsonl chartist-finetune/data/v2/planning_testset.sha256
git commit -m "data(finetune): dashboard requests, and a frozen planning test set"
```

### Task 12: Measure the new flow on today's adapter

**Files:**
- Create: `chartist-finetune/measure_planning.py`
- Test: `chartist-finetune/tests/test_measure_planning.py`

**Interfaces:**
- Consumes: the contract re-exports (Task 4); `chart_types.is_area_figure`; `executor.run_candidates`; `evaluate.SYSTEM_FALLBACK`, `evaluate.strip_fence`, `evaluate.THINK_PREFIX`.
- Produces: `plan_matches(chart: str, figure_type: str | None, code: str) -> bool`; `summarize(rows: list[dict]) -> dict`; report `data/v2/planning_eval_<label>.json` and rows `data/v2/planning_eval_<label>.rows.jsonl`.

- [ ] **Step 1: Write the failing test**

```python
# chartist-finetune/tests/test_measure_planning.py
from measure_planning import plan_matches, summarize


def test_plan_matches_uses_traces_and_the_area_tie_break():
    assert plan_matches("bar", "bar", "")
    assert not plan_matches("pie", "bar", "")
    assert plan_matches("area", "scatter", "fig = px.area(d)")
    assert not plan_matches("line", "scatter", "fig = px.area(d)")
    assert not plan_matches("bar", None, "")


def test_summarize_counts_each_stage():
    rows = [
        {"directions": 5, "direction_errors": 0, "charts": 4, "chart_errors": 1, "analyst_attempts": 1,
         "planner_attempts": 2, "drawn": [{"ok": True, "match": True}, {"ok": False, "match": False}]},
        {"directions": 0, "direction_errors": 2, "charts": 0, "chart_errors": 0, "analyst_attempts": 3,
         "planner_attempts": 0, "drawn": []},
    ]
    s = summarize(rows)
    assert s["analyst_ok_rate"] == 0.5 and s["planner_ok_rate"] == 1.0
    assert s["render_rate"] == 0.5 and s["plan_match_rate"] == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_measure_planning.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'measure_planning'`

- [ ] **Step 3: Write the implementation**

```python
#!/usr/bin/env python3
"""The new dashboard flow, end to end, on the local model.

Same prompts, same checks and the same retry text as the backend
(planning_contract via contract.py), run in-process with mlx so it can batch.
For each frozen planning test row: the analyst proposes directions (checked,
retried twice), the planner writes chart plans (checked, retried twice), and
the chartist draws the first plans, which are executed against the real table.

Reports how often each stage produces something usable, how often a planned
chart renders, and how often the rendered chart is the kind that was planned.
Rows are saved as each one finishes; rerunning resumes.

    .venv/bin/python measure_planning.py --label lora-v1
    .venv/bin/python measure_planning.py --label lora-v2 --adapter-path runs/adapters-mlx-v2
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

import chart_types
from contract import (
    ANALYST_MAX_TOKENS, ANALYST_SYSTEM_PROMPT, ANALYST_USER_TEMPLATE, CHARTIST_MAX_TOKENS,
    CHARTIST_SYSTEM_PROMPT, CHARTIST_USER_TEMPLATE, FIX_PROMPT, KIND_TRACES, NO_REQUEST,
    PLANNER_MAX_TOKENS, PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE, check_directions,
    check_specs, columns_by_table, extract_json, profile_table, render_directions,
    render_profiles, render_spec,
)
from evaluate import THINK_PREFIX, strip_fence
from executor import run_candidates

MAX_ATTEMPTS = 3


def plan_matches(chart: str, figure_type: str | None, code: str) -> bool:
    if figure_type not in KIND_TRACES.get(chart, set()):
        return False
    if chart == "area":
        return chart_types.is_area_figure(code)
    if chart in ("line", "scatter"):
        return not chart_types.is_area_figure(code)
    return True


def summarize(rows: list[dict]) -> dict:
    n = len(rows) or 1
    with_dirs = [r for r in rows if r["directions"]]
    drawn = [d for r in rows for d in r["drawn"]]
    rendered = [d for d in drawn if d["ok"]]
    return {
        "rows": len(rows),
        "analyst_ok_rate": len(with_dirs) / n,
        "mean_directions": sum(r["directions"] for r in rows) / n,
        "planner_ok_rate": (sum(1 for r in with_dirs if r["charts"]) / len(with_dirs)) if with_dirs else 0.0,
        "mean_charts": (sum(r["charts"] for r in with_dirs) / len(with_dirs)) if with_dirs else 0.0,
        "rows_needing_retries": sum(1 for r in rows if r["analyst_attempts"] > 1 or r["planner_attempts"] > 1) / n,
        "charts_drawn": len(drawn),
        "render_rate": (len(rendered) / len(drawn)) if drawn else 0.0,
        "plan_match_rate": (sum(1 for d in rendered if d["match"]) / len(rendered)) if rendered else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--model", default="models/qwen3.5-9b-4bit")
    ap.add_argument("--adapter-path", default="runs/adapters-mlx")
    ap.add_argument("--testset", default="data/v2/planning_testset.jsonl")
    ap.add_argument("--max-charts-per-dashboard", type=int, default=3)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--batch-size", type=int, default=16)
    args = ap.parse_args()

    from mlx_lm import batch_generate, load
    from mlx_lm.sample_utils import make_sampler

    schemas = {r["schema_id"]: r for r in (json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)}
    rows = [json.loads(l) for l in Path(args.testset).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        rows = rows[: args.limit]
    out = Path(f"data/v2/planning_eval_{args.label}.json")
    ckpt = out.with_suffix(".rows.jsonl")
    done = {json.loads(l)["request_id"] for l in ckpt.read_text(encoding="utf-8").splitlines() if l.strip()} if ckpt.exists() else set()
    todo = [r for r in rows if r["request_id"] not in done]
    print(f"{len(rows)} planning rows, {len(todo)} to go")

    adapter = None if args.adapter_path in ("none", "") else args.adapter_path
    model, tokenizer = load(args.model, adapter_path=adapter)
    sampler = make_sampler(temp=0.0)

    def tokens(messages: list[dict], thinking: bool) -> list[int]:
        # The planning roles run with thinking off, as llm.py sends them; the
        # chartist keeps the server default, so its prompt is byte-identical.
        extra = {} if thinking else {"enable_thinking": False}
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, **extra)
        if isinstance(ids, dict):
            ids = ids.get("input_ids", [])
        if ids and isinstance(ids[0], (list, tuple)):
            ids = ids[0]
        return list(ids)

    def generate(conversations: list[list[dict]], max_tokens: int, thinking: bool = False) -> list[str]:
        out_texts: list[str] = []
        for start in range(0, len(conversations), args.batch_size):
            chunk = [tokens(c, thinking) for c in conversations[start:start + args.batch_size]]
            resp = batch_generate(model, tokenizer, chunk, max_tokens=max_tokens, sampler=sampler, verbose=False)
            out_texts.extend(THINK_PREFIX.sub("", t, count=1) if "</think>" in t else t for t in resp.texts)
        return out_texts

    def checked(convs: list[list[dict]], check, tables: list[dict], max_tokens: int):
        """The backend's run_checked, batched across rows."""
        best = [([], ["not run"]) for _ in convs]
        attempts = [0] * len(convs)
        live = list(range(len(convs)))
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if not live:
                break
            replies = generate([convs[i] for i in live], max_tokens)
            still = []
            for i, raw in zip(live, replies):
                attempts[i] = attempt
                items, errors = check(extract_json(raw), tables[i])
                if attempt == 1 or len(items) > len(best[i][0]) or (len(items) == len(best[i][0]) and len(errors) < len(best[i][1])):
                    best[i] = (items, errors)
                if not (items and not errors):
                    convs[i] = convs[i] + [{"role": "assistant", "content": raw},
                                           {"role": "user", "content": FIX_PROMPT.format(errors="\n".join(f"- {e}" for e in errors[:10]))}]
                    still.append(i)
            live = still
        return best, attempts

    started = time.time()
    for start in range(0, len(todo), args.batch_size * 4):
        batch = todo[start:start + args.batch_size * 4]
        profiles, tables = [], []
        for row in batch:
            schema = schemas[row["schema_id"]]
            profile = profile_table(schema["table_name"], pd.read_csv(schema["fixture_csv"]))
            profiles.append(profile)
            tables.append(columns_by_table([profile]))
        analyst_convs = [[{"role": "system", "content": ANALYST_SYSTEM_PROMPT},
                          {"role": "user", "content": ANALYST_USER_TEMPLATE.format(request=row["request"] or NO_REQUEST, profiles=render_profiles([p]))}]
                         for row, p in zip(batch, profiles)]
        dir_best, dir_attempts = checked(analyst_convs, check_directions, tables, ANALYST_MAX_TOKENS)

        plan_idx = [i for i, (items, _) in enumerate(dir_best) if items]
        planner_convs = [[{"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                          {"role": "user", "content": PLANNER_USER_TEMPLATE.format(profiles=render_profiles([profiles[i]]), directions=render_directions(dir_best[i][0]))}]
                         for i in plan_idx]
        spec_best_list, spec_attempts_list = checked(planner_convs, check_specs, [tables[i] for i in plan_idx], PLANNER_MAX_TOKENS)
        spec_best = {i: b for i, b in zip(plan_idx, spec_best_list)}
        spec_attempts = {i: a for i, a in zip(plan_idx, spec_attempts_list)}

        jobs = []  # (row index, spec, prompt)
        for i in plan_idx:
            schema = schemas[batch[i]["schema_id"]]
            for spec in spec_best[i][0][: args.max_charts_per_dashboard]:
                user = CHARTIST_USER_TEMPLATE.format(task=render_spec(spec), columns=schema["pandas_columns"],
                                                     dtypes=schema["pandas_dtypes"], sample_rows=schema["sample_rows"])
                jobs.append((i, spec, [{"role": "system", "content": CHARTIST_SYSTEM_PROMPT}, {"role": "user", "content": user}]))
        codes = [strip_fence(t) for t in generate([j[2] for j in jobs], CHARTIST_MAX_TOKENS, thinking=True)]
        verdicts = run_candidates([(c, schemas[batch[j[0]]["schema_id"]]["fixture_csv"]) for c, j in zip(codes, jobs)], max_workers=8)
        drawn = {i: [] for i in range(len(batch))}
        for (i, spec, _), code, verdict in zip(jobs, codes, verdicts):
            drawn[i].append({"chart": spec["chart"], "ok": bool(verdict.ok),
                             "match": bool(verdict.ok) and plan_matches(spec["chart"], verdict.figure_type, code),
                             "figure_type": verdict.figure_type, "error": (verdict.error or "")[:160]})

        with ckpt.open("a", encoding="utf-8") as handle:
            for i, row in enumerate(batch):
                specs, spec_errors = spec_best.get(i, ([], []))
                handle.write(json.dumps({
                    "request_id": row["request_id"], "schema_id": row["schema_id"], "request": row["request"],
                    "directions": len(dir_best[i][0]), "direction_errors": len(dir_best[i][1]) if not dir_best[i][0] else 0,
                    "analyst_attempts": dir_attempts[i], "charts": len(specs), "chart_errors": len(spec_errors),
                    "planner_attempts": spec_attempts.get(i, 0), "specs": specs, "drawn": drawn[i],
                }, ensure_ascii=False) + "\n")
        print(f"  {min(start + len(batch), len(todo))}/{len(todo)} rows ({(time.time() - started) / 60:.1f} min)", flush=True)

    all_rows = [json.loads(l) for l in ckpt.read_text(encoding="utf-8").splitlines() if l.strip()]
    report = {"label": args.label, "adapter": args.adapter_path, "summary": summarize(all_rows)}
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Also add `CHARTIST_MAX_TOKENS` and `CHARTIST_USER_TEMPLATE` to what `measure_planning` imports from `contract` — both already exist there.

- [ ] **Step 4: Run the tests, a smoke run, then the baseline**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_measure_planning.py -v` — Expected: PASS.
Run: `cd chartist-finetune && .venv/bin/python measure_planning.py --label smoke --limit 4` — Expected: a summary with 4 rows.
Run (background, ~1 hour): `cd chartist-finetune && .venv/bin/python measure_planning.py --label lora-v1` — Expected: the lora-v1 baseline in `data/v2/planning_eval_lora-v1.json`.

- [ ] **Step 5: Commit**

```bash
git add chartist-finetune/measure_planning.py chartist-finetune/tests/test_measure_planning.py chartist-finetune/data/v2/planning_eval_lora-v1.json chartist-finetune/data/v2/planning_eval_lora-v1.rows.jsonl
git commit -m "feat(finetune): measure the AI dashboard flow end to end; lora-v1 baseline"
```

---

## Phase 2 — The v2 dataset (≤ $35)

### Task 13: A plan for each existing answer

**Files:**
- Create: `chartist-finetune/extract_specs.py`
- Test: `chartist-finetune/tests/test_extract_specs.py`

**Interfaces:**
- Consumes: Tasks 4 and 10; `data/targets.jsonl`; `data/schemas.jsonl`.
- Produces: `columns_in_code(spec: dict, code: str) -> bool`; `consistent(spec: dict, figure_type: str | None, code: str) -> bool`; `data/v2/target_specs.jsonl` rows `{question_id, schema_id, spec}`.

- [ ] **Step 1: Write the failing test**

```python
# chartist-finetune/tests/test_extract_specs.py
from extract_specs import columns_in_code, consistent

CODE = "d = df.groupby('cntry_cd')['churn_cnt'].sum()\nfig = px.bar(d, x=\"cntry_cd\", y='churn_cnt')\n"


def spec(**kw):
    base = {"chart": "bar", "x": "cntry_cd", "y": "churn_cnt", "group": ""}
    base.update(kw)
    return base


def test_columns_must_appear_in_the_code():
    assert columns_in_code(spec(), CODE)
    assert not columns_in_code(spec(group="plan_tier"), CODE)


def test_consistent_needs_the_right_trace_and_area_tie_break():
    assert consistent(spec(), "bar", CODE)
    assert not consistent(spec(chart="pie"), "bar", CODE)
    assert not consistent(spec(chart="area"), "scatter", CODE)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_extract_specs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'extract_specs'`

- [ ] **Step 3: Write the implementation**

```python
#!/usr/bin/env python3
"""Write the chart plan each existing answer implements.

The v2 chartist learns to follow plans, so each of the 1,897 verified answers
gets the plan it actually draws. Haiku reads the code and writes the plan;
the plan is kept only if it passes the production check against the real
table, every column it names appears in the code, and the chart kind matches
the trace type the answer produced when it was executed.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

import chart_types
import client
from contract import KIND_TRACES, SPEC_RULES, SPEC_SCHEMA, check_spec, columns_by_table, profile_table, render_profiles

SYSTEM = (
    "You read the Python code of one chart and write the chart plan it implements.\n\n"
    + SPEC_RULES
    + "\n\nDescribe what the code actually draws, not what the question asked. Use the exact "
    "column names the code uses. Reply with the plan as JSON."
)
CHUNK = 200


def columns_in_code(spec: dict, code: str) -> bool:
    for key in ("x", "y", "group"):
        value = spec.get(key) or ""
        if value and not re.search(r"['\"]" + re.escape(value) + r"['\"]", code):
            return False
    return True


def consistent(spec: dict, figure_type: str | None, code: str) -> bool:
    if figure_type not in KIND_TRACES.get(spec["chart"], set()):
        return False
    if spec["chart"] == "area":
        return chart_types.is_area_figure(code)
    if spec["chart"] in ("line", "scatter"):
        return not chart_types.is_area_figure(code)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default="data/targets.jsonl")
    ap.add_argument("--out", default="data/v2/target_specs.jsonl")
    ap.add_argument("--limit", type=int, default=None, help="pilot")
    ap.add_argument("--est-cost", type=float, default=None, help="USD per request, from the pilot")
    ap.add_argument("--max-spend", type=float, default=3.00)
    args = ap.parse_args()

    schemas = {r["schema_id"]: r for r in (json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)}
    targets = [json.loads(l) for l in Path(args.targets).read_text(encoding="utf-8").splitlines() if l.strip()]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["question_id"] for l in out.read_text(encoding="utf-8").splitlines() if l.strip()} if out.exists() else set()
    targets = [t for t in targets if t["question_id"] not in done]
    if args.limit:
        targets = targets[: args.limit]
    print(f"{len(targets)} answers to plan ({len(done)} already done)")

    profiles = {}
    kept = rejected = 0
    spent_here = 0.0
    for start in range(0, len(targets), CHUNK):
        chunk = targets[start:start + CHUNK]
        requests = []
        for t in chunk:
            schema = schemas[t["schema_id"]]
            if t["schema_id"] not in profiles:
                profiles[t["schema_id"]] = profile_table(schema["table_name"], pd.read_csv(schema["fixture_csv"]))
            question = t["messages"][1]["content"].split("\n\nDataFrame `df` schema:")[0][len("Task: "):]
            user = f"Table:\n{render_profiles([profiles[t['schema_id']]])}\n\nQuestion: {question}\n\nCode:\n{t['messages'][2]['content']}"
            requests.append(client.json_request(t["question_id"], client.HAIKU, SYSTEM, user, SPEC_SCHEMA, max_tokens=2000, effort="low"))
        planned = (args.est_cost * len(requests)) if args.est_cost else client.worst_case_cost(client.HAIKU, len(requests), 2500, 2000)
        if spent_here + planned > args.max_spend:
            raise SystemExit(f"stopping: this script's spend ${spent_here:.2f} + ${planned:.2f} would pass --max-spend")
        client.guard("v2-specs", planned)
        outcome = client.run_batch(requests, label="v2-specs")
        spent_here += client.record_spend("v2-specs", client.HAIKU, outcome.usage, {"phase": "v2", "requests": len(requests)})
        with out.open("a", encoding="utf-8") as handle:
            for t in chunk:
                payload = outcome.payloads.get(t["question_id"])
                if not payload:
                    rejected += 1
                    continue
                schema = schemas[t["schema_id"]]
                payload["table"] = schema["table_name"]
                spec, problems = check_spec(payload, columns_by_table([profiles[t["schema_id"]]]))
                code = t["messages"][2]["content"]
                if spec is None or not columns_in_code(spec, code) or not consistent(spec, t.get("figure_type"), code):
                    rejected += 1
                    continue
                spec["question"] = t["messages"][1]["content"].split("\n\nDataFrame `df` schema:")[0][len("Task: "):]
                handle.write(json.dumps({"question_id": t["question_id"], "schema_id": t["schema_id"], "spec": spec}, ensure_ascii=False) + "\n")
                kept += 1
        print(f"  {start + len(chunk)}/{len(targets)}: kept {kept}, rejected {rejected}, spent ${spent_here:.4f}", flush=True)
    print(f"done: kept {kept}, rejected {rejected}; v2 spend so far ${client.phase_spend():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Test, pilot, full run**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_extract_specs.py -v` — Expected: PASS.
Run: `cd chartist-finetune && .venv/bin/python extract_specs.py --limit 20 --out data/v2/target_specs_pilot.jsonl` — Expected: kept ≥ 15 of 20. Read five kept plans against their code. Compute the measured cost per request from the ledger row.
Run: `cd chartist-finetune && .venv/bin/python extract_specs.py --est-cost <pilot cost per request × 1.3>` — Expected: kept ≥ 85% of 1,897; v2 spend ≈ $1.

- [ ] **Step 5: Commit**

```bash
git add chartist-finetune/extract_specs.py chartist-finetune/tests/test_extract_specs.py chartist-finetune/data/v2/target_specs.jsonl
git commit -m "data(finetune): the plan each existing answer implements"
```

### Task 14: The missing chart kinds

**Files:**
- Create: `chartist-finetune/gen_v2_targets.py`
- Test: `chartist-finetune/tests/test_gen_v2_targets.py`

**Interfaces:**
- Consumes: Tasks 4, 10, 13 (`columns_in_code`, `consistent`); `executor.run_candidates`.
- Produces: `KIND_QUOTA = {"funnel": 150, "sunburst": 120, "waterfall": 150, "kpi": 150}`; `BUCKET_OF_KIND`; `assign(kinds, schemas) -> list[tuple[str, dict]]`; `data/v2/new_targets.jsonl` rows in `targets.jsonl` format plus `kind` and `spec`.

- [ ] **Step 1: Write the failing test**

```python
# chartist-finetune/tests/test_gen_v2_targets.py
from gen_v2_targets import BUCKET_OF_KIND, assign


def test_assign_spreads_kinds_over_train_schemas_only():
    schemas = [{"schema_id": f"s{i}", "split": "test" if i % 3 == 0 else "train"} for i in range(9)]
    pairs = assign({"funnel": 4, "kpi": 2}, schemas)
    assert len(pairs) == 6
    assert all(s["split"] == "train" for _, s in pairs)
    assert {s["schema_id"] for k, s in pairs if k == "funnel"} == {"s1", "s2", "s4", "s5"}


def test_new_kinds_map_to_the_old_buckets():
    assert BUCKET_OF_KIND["waterfall"] == "treemap_funnel_waterfall"
    assert BUCKET_OF_KIND["kpi"] == "gauge_or_indicator"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_gen_v2_targets.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gen_v2_targets'`

- [ ] **Step 3: Write the implementation**

```python
#!/usr/bin/env python3
"""Answers for the chart kinds v1 barely saw: funnel 0, sunburst 0, waterfall 2, KPI 39.

Stage 1, Haiku: for each (train schema, kind), one question a user would ask
that this kind answers best, or an empty question when the table cannot support
it. Stage 2, Sonnet: the code and the plan it implements, in one reply. A row is
kept only if the code runs against the real table, the figure is that kind, the
plan passes the production check, and every column the plan names is in the code.

Rows are stored in data/targets.jsonl's format, so the existing exporters and
caps work on them, with `kind` and `spec` added.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import client
from contract import (CHARTIST_SYSTEM_PROMPT, CHARTIST_USER_TEMPLATE, KIND_TRACES, SPEC_RULES, SPEC_SCHEMA,
                      check_spec, columns_by_table, profile_table, render_profiles)
from executor import run_candidates
from extract_specs import columns_in_code, consistent

KIND_QUOTA = {"funnel": 150, "sunburst": 120, "waterfall": 150, "kpi": 150}
BUCKET_OF_KIND = {"funnel": "treemap_funnel_waterfall", "sunburst": "treemap_funnel_waterfall",
                  "waterfall": "treemap_funnel_waterfall", "kpi": "gauge_or_indicator"}
MEANING = {
    "funnel": "a funnel: how a count narrows across ordered stages, like visits to signups to purchases",
    "sunburst": "a sunburst: one total split by two nested categories, like region then product",
    "waterfall": "a waterfall: how separate amounts add up to a total, or how a value changed step by step",
    "kpi": "a single headline number, like total revenue or the average score",
}
Q_SYSTEM = """You write one question a business user would type into a dashboard tool about this table, the kind best answered by the chart described. Use everyday words, under 15 words. If this table cannot honestly support that chart, reply with an empty question.
Reply as JSON: {"question": "..."}"""
Q_SCHEMA = {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"], "additionalProperties": False}
CODE_SCHEMA = {"type": "object", "properties": {"plan": SPEC_SCHEMA, "code": {"type": "string"}},
               "required": ["plan", "code"], "additionalProperties": False}


def assign(kinds: dict[str, int], schemas: list[dict]) -> list[tuple[str, dict]]:
    train = [s for s in schemas if s["split"] == "train"]
    pairs = []
    for kind, count in kinds.items():
        pairs.extend((kind, train[i % len(train)]) for i in range(count))
    return pairs


def _prompt(schema: dict, question: str) -> str:
    return CHARTIST_USER_TEMPLATE.format(task=question, columns=schema["pandas_columns"],
                                         dtypes=schema["pandas_dtypes"], sample_rows=schema["sample_rows"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0, help="0.05 for a pilot")
    ap.add_argument("--out", default="data/v2/new_targets.jsonl")
    ap.add_argument("--max-spend", type=float, default=5.00)
    args = ap.parse_args()

    schemas = [json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l]
    quota = {k: max(1, int(v * args.scale)) for k, v in KIND_QUOTA.items()}
    pairs = assign(quota, schemas)
    profiles = {s["schema_id"]: profile_table(s["table_name"], pd.read_csv(s["fixture_csv"])) for _, s in pairs}

    q_requests = [client.json_request(f"q{i}", client.HAIKU, Q_SYSTEM,
                                      f"Chart: {MEANING[kind]}\n\n{render_profiles([profiles[s['schema_id']]])}",
                                      Q_SCHEMA, max_tokens=800, effort="low")
                  for i, (kind, s) in enumerate(pairs)]
    client.guard("v2-kind-questions", client.worst_case_cost(client.HAIKU, len(q_requests), 1500, 800))
    q_out = client.run_batch(q_requests, label="v2-kind-questions")
    spent = client.record_spend("v2-kind-questions", client.HAIKU, q_out.usage, {"phase": "v2", "requests": len(q_requests)})

    jobs = [(i, kind, s, q_out.payloads[f"q{i}"]["question"].strip()) for i, (kind, s) in enumerate(pairs)
            if q_out.payloads.get(f"q{i}", {}).get("question", "").strip()]
    print(f"{len(jobs)} questions of {len(pairs)} (the rest: table could not support the kind)")
    c_requests = []
    for i, kind, s, question in jobs:
        system = (CHARTIST_SYSTEM_PROMPT + f"\n\nFor this request, produce a {kind} chart. Return the code and the "
                  f"chart plan it implements; the plan is described below.\n\n{SPEC_RULES}")
        c_requests.append(client.json_request(f"c{i}", client.SONNET, system, _prompt(s, question), CODE_SCHEMA,
                                              max_tokens=4000, effort="medium"))
    planned = client.worst_case_cost(client.SONNET, len(c_requests), 2500, 4000)
    if spent + planned > args.max_spend:
        planned = args.max_spend - spent
    client.guard("v2-kind-code", planned)
    c_out = client.run_batch(c_requests, label="v2-kind-code")
    client.record_spend("v2-kind-code", client.SONNET, c_out.usage, {"phase": "v2", "requests": len(c_requests)})

    candidates = [(i, kind, s, q, c_out.payloads[f"c{i}"]) for i, kind, s, q in jobs if c_out.payloads.get(f"c{i}")]
    verdicts = run_candidates([(c[4]["code"], c[2]["fixture_csv"]) for c in candidates], max_workers=8)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    with out.open("w", encoding="utf-8") as handle:
        for (i, kind, s, question, payload), verdict in zip(candidates, verdicts):
            code = payload["code"].strip()
            plan = {**payload["plan"], "table": s["table_name"], "question": question}
            spec, problems = check_spec(plan, columns_by_table([profiles[s["schema_id"]]]))
            if not verdict.ok or verdict.figure_type not in KIND_TRACES[kind] or spec is None \
                    or spec["chart"] != kind or not columns_in_code(spec, code) or not consistent(spec, verdict.figure_type, code):
                continue
            handle.write(json.dumps({
                "schema_id": s["schema_id"], "question_id": f"v2-{kind}-{i}",
                "messages": [{"role": "system", "content": CHARTIST_SYSTEM_PROMPT},
                             {"role": "user", "content": _prompt(s, question)},
                             {"role": "assistant", "content": code}],
                "fixture_csv": s["fixture_csv"], "chart_bucket": BUCKET_OF_KIND[kind], "hard_case": None,
                "figure_type": verdict.figure_type, "attempt": 1, "kind": kind, "spec": spec,
            }, ensure_ascii=False) + "\n")
            kept += 1
    print(f"kept {kept} of {len(candidates)}; v2 spend so far ${client.phase_spend():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Test, pilot, full run**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_gen_v2_targets.py -v` — Expected: PASS.
Run: `cd chartist-finetune && .venv/bin/python gen_v2_targets.py --scale 0.05 --out data/v2/new_targets_pilot.jsonl` — Expected: ~28 pairs, most kept; read the kept funnels and waterfalls.
Run: `cd chartist-finetune && .venv/bin/python gen_v2_targets.py` — Expected: kept ≥ 400 of ~570; v2 spend ≈ $4.

- [ ] **Step 5: Commit**

```bash
git add chartist-finetune/gen_v2_targets.py chartist-finetune/tests/test_gen_v2_targets.py chartist-finetune/data/v2/new_targets.jsonl
git commit -m "data(finetune): funnel, sunburst, waterfall and KPI answers with their plans"
```

### Task 15: Planning examples from Opus

**Files:**
- Create: `chartist-finetune/gen_plans.py`
- Test: `chartist-finetune/tests/test_gen_plans.py`

**Interfaces:**
- Consumes: Tasks 4, 10, 11 (`data/v2/requests.jsonl`, train split only).
- Produces: `keep_directions(items, errors) -> bool`; `keep_charts(items, errors) -> bool`; `data/v2/plans.jsonl` rows `{request_id, schema_id, request, directions, charts}`.

- [ ] **Step 1: Write the failing test**

```python
# chartist-finetune/tests/test_gen_plans.py
from gen_plans import keep_charts, keep_directions


def test_only_clean_and_full_plans_become_training_rows():
    three = [{}, {}, {}]
    assert keep_directions(three, [])
    assert not keep_directions(three, ["direction 4: ..."])
    assert not keep_directions([{}, {}], [])
    assert keep_charts(three, []) and not keep_charts(three, ["chart 2: ..."])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_gen_plans.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gen_plans'`

- [ ] **Step 3: Write the implementation**

```python
#!/usr/bin/env python3
"""Analyst and planner examples written by Claude Opus 5.5.

Planning is the reasoning-heavy step, where a 9B is furthest behind Opus, so
it is where copying Opus pays most. Opus gets the EXACT production prompts
(planning_contract via contract.py): stage A the analyst prompt, stage B the
planner prompt built from Opus's own checked directions. Only replies with zero
check errors and at least three items become training rows. Train-split
schemas only. Refused requests are dropped and counted: Batches reject the
server-side fallback, and an answer from another model would not be Opus's.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import pandas as pd

import client
from contract import (ANALYST_SYSTEM_PROMPT, ANALYST_USER_TEMPLATE, DIRECTIONS_SCHEMA, NO_REQUEST,
                      PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE, SPECS_SCHEMA, check_directions,
                      check_specs, columns_by_table, profile_table, render_directions, render_profiles)

MIN_ITEMS = 3
CHUNK = 60


def keep_directions(items: list, errors: list) -> bool:
    return len(items) >= MIN_ITEMS and not errors


def keep_charts(items: list, errors: list) -> bool:
    return len(items) >= MIN_ITEMS and not errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="20 for the pilot")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--est-cost", type=float, default=None, help="USD per Opus request, from the pilot")
    ap.add_argument("--max-spend", type=float, default=22.00)
    ap.add_argument("--out", default="data/v2/plans.jsonl")
    ap.add_argument("--seed", type=int, default=20261121)
    args = ap.parse_args()

    schemas = {r["schema_id"]: r for r in (json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)}
    rows = [json.loads(l) for l in Path("data/v2/requests.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r["split"] == "train"]
    assert all(schemas[r["schema_id"]]["split"] == "train" for r in rows), "test-split schema leaked"
    random.Random(args.seed).shuffle(rows)
    out = Path(args.out)
    done = {json.loads(l)["request_id"] for l in out.read_text(encoding="utf-8").splitlines() if l.strip()} if out.exists() else set()
    rows = [r for r in rows if r["request_id"] not in done]
    if args.limit:
        rows = rows[: args.limit]

    spent_here = 0.0

    def batch(requests: list, label: str):
        nonlocal spent_here
        planned = (args.est_cost * len(requests)) if args.est_cost else client.worst_case_cost(client.OPUS, len(requests), 3000, 16000)
        if spent_here + planned > args.max_spend:
            raise SystemExit(f"stopping: ${spent_here:.2f} + ${planned:.2f} would pass --max-spend ${args.max_spend:.2f}")
        client.guard(label, planned)
        result = client.run_batch(requests, label=label)
        spent_here += client.record_spend(label, client.OPUS, result.usage, {"phase": "v2", "requests": len(requests)})
        print(f"[{label}] refusals {result.refusals}, unparsed {result.unparsed}, errored {result.errored}")
        return result

    kept = 0
    for start in range(0, len(rows), CHUNK):
        chunk = rows[start:start + CHUNK]
        profiles = {r["request_id"]: profile_table(schemas[r["schema_id"]]["table_name"],
                                                   pd.read_csv(schemas[r["schema_id"]]["fixture_csv"])) for r in chunk}
        analyst = batch([client.json_request(r["request_id"], client.OPUS, ANALYST_SYSTEM_PROMPT,
                                             ANALYST_USER_TEMPLATE.format(request=r["request"] or NO_REQUEST,
                                                                          profiles=render_profiles([profiles[r["request_id"]]])),
                                             DIRECTIONS_SCHEMA, max_tokens=16000, effort=args.effort)
                         for r in chunk], "v2-plans-analyst")
        good = {}
        for r in chunk:
            items, errors = check_directions(analyst.payloads.get(r["request_id"]), columns_by_table([profiles[r["request_id"]]]))
            if keep_directions(items, errors):
                good[r["request_id"]] = items
        planner = batch([client.json_request(rid, client.OPUS, PLANNER_SYSTEM_PROMPT,
                                             PLANNER_USER_TEMPLATE.format(profiles=render_profiles([profiles[rid]]),
                                                                          directions=render_directions(items)),
                                             SPECS_SCHEMA, max_tokens=16000, effort=args.effort)
                         for rid, items in good.items()], "v2-plans-planner") if good else None
        with out.open("a", encoding="utf-8") as handle:
            for r in chunk:
                if r["request_id"] not in good or planner is None:
                    continue
                charts, errors = check_specs(planner.payloads.get(r["request_id"]), columns_by_table([profiles[r["request_id"]]]))
                if not keep_charts(charts, errors):
                    continue
                handle.write(json.dumps({"request_id": r["request_id"], "schema_id": r["schema_id"], "request": r["request"],
                                         "directions": good[r["request_id"]], "charts": charts}, ensure_ascii=False) + "\n")
                kept += 1
        print(f"  {start + len(chunk)}/{len(rows)}: kept {kept}; spent here ${spent_here:.4f}", flush=True)
    print(f"done: {kept} planning examples; v2 spend so far ${client.phase_spend():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Test, pilot, size, full run**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_gen_plans.py -v` — Expected: PASS.
Run: `cd chartist-finetune && .venv/bin/python gen_plans.py --limit 20 --out data/v2/plans_pilot.jsonl` — Expected: ≥ 15 kept. From the two ledger rows compute cost per example = (analyst + planner cost) / 20, and read three kept examples in full.
Size the full run: `examples = floor((22.00 - pilot cost) / (cost per example × 1.2))`, at most the 480 train requests.
Run: `cd chartist-finetune && .venv/bin/python gen_plans.py --limit <examples> --est-cost <max per-request cost × 1.3>` — Expected: kept ≥ 80%; v2 spend stays under $30.

- [ ] **Step 5: Commit**

```bash
git add chartist-finetune/gen_plans.py chartist-finetune/tests/test_gen_plans.py chartist-finetune/data/v2/plans.jsonl
git commit -m "data(finetune): analyst and planner examples distilled from Opus 5.5"
```

### Task 16: Code for Opus's plans (only within budget)

**Files:**
- Create: `chartist-finetune/gen_spec_code.py`

**Interfaces:**
- Consumes: `data/v2/plans.jsonl` (Task 15), Tasks 10 and 13.
- Produces: `data/v2/spec_targets.jsonl` rows in `targets.jsonl` format whose user prompt is the plan prompt, plus `spec` and `"format": "spec"`.

- [ ] **Step 1: Check the budget first**

Run: `cd chartist-finetune && .venv/bin/python -c "import client; print(round(35 - client.phase_spend(), 2))"`
If the remainder is under $2.00, skip this task: write `SKIPPED: budget` in the plan's checkbox and go to Task 17.

- [ ] **Step 2: Write the script**

```python
#!/usr/bin/env python3
"""Sonnet writes the code for the chart plans Opus planned.

The v2 chartist then learns plan -> code on exactly the kind of plans the
planner produces. Each plan becomes one chartist prompt built with render_spec,
the same text the app sends. Kept only if the code runs against the real table,
draws the planned kind, and uses the plan's columns.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import client
from contract import CHARTIST_SYSTEM_PROMPT, CHARTIST_USER_TEMPLATE, KIND_TRACES, render_spec
from executor import run_candidates
from extract_specs import columns_in_code, consistent

CODE_SCHEMA = {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"], "additionalProperties": False}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-charts", type=int, default=1000)
    ap.add_argument("--max-spend", type=float, default=4.00)
    ap.add_argument("--out", default="data/v2/spec_targets.jsonl")
    args = ap.parse_args()

    schemas = {r["schema_id"]: r for r in (json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)}
    plans = [json.loads(l) for l in Path("data/v2/plans.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    jobs = [(p, n, spec) for p in plans for n, spec in enumerate(p["charts"])][: args.max_charts]

    def prompt(p, spec):
        s = schemas[p["schema_id"]]
        return CHARTIST_USER_TEMPLATE.format(task=render_spec(spec), columns=s["pandas_columns"],
                                             dtypes=s["pandas_dtypes"], sample_rows=s["sample_rows"])

    requests = [client.json_request(f"{p['request_id']}-c{n}", client.SONNET,
                                    CHARTIST_SYSTEM_PROMPT + f"\n\nFor this request, produce a {spec['chart']} chart.",
                                    prompt(p, spec), CODE_SCHEMA, max_tokens=3000, effort="low")
                for p, n, spec in jobs]
    planned = min(args.max_spend, client.worst_case_cost(client.SONNET, len(requests), 2500, 3000))
    client.guard("v2-spec-code", planned)
    outcome = client.run_batch(requests, label="v2-spec-code")
    client.record_spend("v2-spec-code", client.SONNET, outcome.usage, {"phase": "v2", "requests": len(requests)})

    candidates = [(p, n, spec, outcome.payloads[f"{p['request_id']}-c{n}"]["code"].strip())
                  for p, n, spec in jobs if outcome.payloads.get(f"{p['request_id']}-c{n}")]
    verdicts = run_candidates([(c[3], schemas[c[0]["schema_id"]]["fixture_csv"]) for c in candidates], max_workers=8)
    kept = 0
    with Path(args.out).open("w", encoding="utf-8") as handle:
        for (p, n, spec, code), verdict in zip(candidates, verdicts):
            if not verdict.ok or not columns_in_code(spec, code) or not consistent(spec, verdict.figure_type, code):
                continue
            handle.write(json.dumps({
                "schema_id": p["schema_id"], "question_id": f"{p['request_id']}-c{n}",
                "messages": [{"role": "system", "content": CHARTIST_SYSTEM_PROMPT},
                             {"role": "user", "content": prompt(p, spec)},
                             {"role": "assistant", "content": code}],
                "fixture_csv": schemas[p["schema_id"]]["fixture_csv"], "chart_bucket": spec["chart"],
                "hard_case": None, "figure_type": verdict.figure_type, "attempt": 1,
                "spec": spec, "format": "spec",
            }, ensure_ascii=False) + "\n")
            kept += 1
    print(f"kept {kept} of {len(candidates)}; v2 spend so far ${client.phase_spend():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run it**

Run: `cd chartist-finetune && .venv/bin/python gen_spec_code.py --max-charts <charts the remaining budget covers at $0.0035 each>`
Expected: kept ≥ 85%; v2 spend under $35.

- [ ] **Step 4: Commit**

```bash
git add chartist-finetune/gen_spec_code.py chartist-finetune/data/v2/spec_targets.jsonl
git commit -m "data(finetune): code for the chart plans Opus planned"
```

### Task 17: Export the multi-task v2 dataset

**Files:**
- Create: `chartist-finetune/export_v2.py`
- Create: `chartist-finetune/verify_v2_rows.py`
- Test: `chartist-finetune/tests/test_export_v2.py`

**Interfaces:**
- Consumes: `data/targets.jsonl`, `data/docs_rows.jsonl`, `data/v2/target_specs.jsonl`, `data/v2/new_targets.jsonl`, `data/v2/spec_targets.jsonl` (optional), `data/v2/plans.jsonl`; contract re-exports.
- Produces: `spec_prompt(question_prompt: str, spec: dict) -> str`; `split_by_schema(rows, valid_ratio, seed) -> dict[str, list]`; `data/mlx_v2/{train,valid}.jsonl`, `{train,valid}_fixtures.jsonl`, `split_manifest.json`; `data/mlx_v2_capped/` from `cap_dataset.py`.

- [ ] **Step 1: Write the failing test**

```python
# chartist-finetune/tests/test_export_v2.py
from export_v2 import spec_prompt, split_by_schema

PROMPT = "Task: Where is churn highest?\n\nDataFrame `df` schema:\ncolumns: ['a']\n\nWrite the Python now."
SPEC = {"title": "Churn", "question": "Where is churn highest?", "chart": "bar", "table": "t", "x": "a",
        "y": "", "group": "", "agg": "count", "grain": "", "sort": "", "top_n": 0}


def test_spec_prompt_swaps_only_the_task():
    text = spec_prompt(PROMPT, SPEC)
    assert text.startswith("Task: Where is churn highest?\n\nChart plan:\n- chart: bar")
    assert text.endswith("DataFrame `df` schema:\ncolumns: ['a']\n\nWrite the Python now.")


def test_split_keeps_schemas_whole_and_disjoint():
    rows = [{"schema_id": f"s{i % 10}"} for i in range(100)]
    splits = split_by_schema(rows, 0.2, 7)
    train = {r["schema_id"] for r in splits["train"]}
    valid = {r["schema_id"] for r in splits["valid"]}
    assert train and valid and not train & valid and len(splits["train"]) + len(splits["valid"]) == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_export_v2.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'export_v2'`

- [ ] **Step 3: Write `export_v2.py`**

```python
#!/usr/bin/env python3
"""Build the v2 dataset: one adapter, three jobs.

- chartist, question form: the v1 prompt, so single blocks keep working
- chartist, plan form: the same answers with render_spec(plan) as the task
- analyst: profile + request -> directions (Opus)
- planner: profile + directions -> chart plans (Opus)

Every chartist answer passes the contract; every analyst and planner answer
passes the production check with zero errors against its real table. Splits
are by schema, and no row may come from a schema in either frozen test set.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from contract import (ANALYST_SYSTEM_PROMPT, ANALYST_USER_TEMPLATE, CHARTIST_SYSTEM_PROMPT, NO_REQUEST,
                      PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE, check_directions, check_specs,
                      columns_by_table, profile_table, render_directions, render_profiles, render_spec,
                      validate_chart_code)

SEP = "\n\nDataFrame `df` schema:"


def spec_prompt(question_prompt: str, spec: dict) -> str:
    head, sep, tail = question_prompt.partition(SEP)
    if not sep:
        raise ValueError("prompt has no schema block")
    return "Task: " + render_spec(spec) + sep + tail


def split_by_schema(rows: list[dict], valid_ratio: float, seed: int) -> dict[str, list]:
    keys = sorted({r["schema_id"] for r in rows})
    random.Random(seed).shuffle(keys)
    valid = set(keys[: max(1, int(len(keys) * valid_ratio))])
    return {"train": [r for r in rows if r["schema_id"] not in valid],
            "valid": [r for r in rows if r["schema_id"] in valid]}


def _jsonl(path: str) -> list[dict]:
    p = Path(path)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="data/mlx_v2")
    ap.add_argument("--valid-ratio", type=float, default=0.12)
    ap.add_argument("--plan-share", type=float, default=0.5, help="share of answers shown in plan form")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    schemas = {r["schema_id"]: r for r in _jsonl("data/schemas.jsonl")}
    frozen = {r["schema_id"] for r in _jsonl("data/testset.jsonl")} | {r["schema_id"] for r in _jsonl("data/v2/planning_testset.jsonl")}
    specs = {r["question_id"]: r["spec"] for r in _jsonl("data/v2/target_specs.jsonl")}
    rng = random.Random(args.seed)
    rows: list[dict] = []

    def chartist(row: dict, prompt: str, form: str) -> None:
        rows.append({"schema_id": row["schema_id"], "row_id": f"{row['question_id']}:{form}", "role": "chartist",
                     "form": form, "fixture_csv": row.get("fixture_csv", ""),
                     "messages": [{"role": "system", "content": CHARTIST_SYSTEM_PROMPT},
                                  {"role": "user", "content": prompt},
                                  {"role": "assistant", "content": row["messages"][2]["content"]}]})

    for row in _jsonl("data/targets.jsonl") + _jsonl("data/v2/new_targets.jsonl"):
        spec = row.get("spec") or specs.get(row["question_id"])
        if spec and rng.random() < args.plan_share:
            chartist(row, spec_prompt(row["messages"][1]["content"], spec), "plan")
        else:
            chartist(row, row["messages"][1]["content"], "question")
    for row in _jsonl("data/docs_rows.jsonl"):
        chartist(row, row["messages"][1]["content"], "question")
    for row in _jsonl("data/v2/spec_targets.jsonl"):
        chartist(row, row["messages"][1]["content"], "plan")

    profiles: dict[str, object] = {}
    for plan in _jsonl("data/v2/plans.jsonl"):
        schema = schemas[plan["schema_id"]]
        if plan["schema_id"] not in profiles:
            profiles[plan["schema_id"]] = profile_table(schema["table_name"], pd.read_csv(schema["fixture_csv"]))
        profile = profiles[plan["schema_id"]]
        tables = columns_by_table([profile])
        directions, d_err = check_directions({"directions": plan["directions"]}, tables)
        charts, c_err = check_specs({"charts": plan["charts"]}, tables)
        if d_err or c_err:
            raise SystemExit(f"plan {plan['request_id']} no longer passes the checks: {d_err or c_err}")
        text = render_profiles([profile])
        rows.append({"schema_id": plan["schema_id"], "row_id": f"{plan['request_id']}:analyst", "role": "analyst",
                     "form": "analyst", "fixture_csv": schema["fixture_csv"],
                     "messages": [{"role": "system", "content": ANALYST_SYSTEM_PROMPT},
                                  {"role": "user", "content": ANALYST_USER_TEMPLATE.format(request=plan["request"] or NO_REQUEST, profiles=text)},
                                  {"role": "assistant", "content": json.dumps({"directions": directions}, ensure_ascii=False)}]})
        rows.append({"schema_id": plan["schema_id"], "row_id": f"{plan['request_id']}:planner", "role": "planner",
                     "form": "planner", "fixture_csv": schema["fixture_csv"],
                     "messages": [{"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                                  {"role": "user", "content": PLANNER_USER_TEMPLATE.format(profiles=text, directions=render_directions(directions))},
                                  {"role": "assistant", "content": json.dumps({"charts": charts}, ensure_ascii=False)}]})

    leaked = {r["schema_id"] for r in rows} & frozen
    if leaked:
        raise SystemExit(f"LEAK: rows from frozen test schemas: {sorted(leaked)[:5]}")
    bad = [r["row_id"] for r in rows if r["role"] == "chartist" and validate_chart_code(r["messages"][2]["content"])]
    if bad:
        raise SystemExit(f"CONTRACT VIOLATION in {len(bad)} chartist rows: {bad[:10]}")

    splits = split_by_schema(rows, args.valid_ratio, args.seed)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"seed": args.seed, "valid_ratio": args.valid_ratio, "plan_share": args.plan_share, "counts": {}}
    for split, split_rows in splits.items():
        random.Random(args.seed).shuffle(split_rows)
        with (out / f"{split}.jsonl").open("w", encoding="utf-8") as handle:
            for r in split_rows:
                handle.write(json.dumps({"messages": r["messages"]}, ensure_ascii=False) + "\n")
        with (out / f"{split}_fixtures.jsonl").open("w", encoding="utf-8") as handle:
            for r in split_rows:
                handle.write(json.dumps({"schema_id": r["schema_id"], "question_id": r["row_id"], "fixture_csv": r["fixture_csv"]}) + "\n")
        manifest["counts"][split] = dict(Counter(r["form"] for r in split_rows), total=len(split_rows))
    (out / "split_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Write `verify_v2_rows.py`**

```python
#!/usr/bin/env python3
"""Check every v2 row the way the trainer will see it, before renting a GPU.

cloud/train_lora.py masks the prompt by splitting the rendered chat on TEXT and
skips any row whose full render does not start with its prompt render. This
runs the same check with the real tokenizer and reports token lengths, so a
row the trainer would silently skip is found here instead of on a pod.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from check_token_lengths import load_tokenizer


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/mlx_v2")
    ap.add_argument("--model", default="models/qwen3.5-9b-4bit")
    args = ap.parse_args()
    tokenizer, route = load_tokenizer(args.model)
    print(f"tokenizer: {route}")
    for split in ("train", "valid"):
        lengths, mismatched = [], 0
        for line in (Path(args.data) / f"{split}.jsonl").read_text(encoding="utf-8").splitlines():
            messages = json.loads(line)["messages"]
            full = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
            prompt = tokenizer.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True)
            if not full.startswith(prompt):
                mismatched += 1
            lengths.append(len(tokenizer(full, add_special_tokens=False)["input_ids"]))
        lengths.sort()
        pick = lambda q: lengths[min(len(lengths) - 1, int(q * len(lengths)))]
        print(f"{split}: {len(lengths)} rows, prefix mismatches {mismatched}, tokens p50 {pick(0.5)} "
              f"p95 {pick(0.95)} p99 {pick(0.99)} max {lengths[-1]}, over 1536: {sum(l > 1536 for l in lengths)}, "
              f"over 2048: {sum(l > 2048 for l in lengths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Test, export, verify, cap**

Run: `cd chartist-finetune && .venv/bin/python -m pytest tests/test_export_v2.py -v` — Expected: PASS.
Run: `cd chartist-finetune && .venv/bin/python export_v2.py` — Expected: counts by form for train and valid; no LEAK, no CONTRACT VIOLATION.
Run: `cd chartist-finetune && .venv/bin/python verify_v2_rows.py` — Expected: prefix mismatches 0 in both splits. Choose `MAXLEN` = 2048 if fewer than 1% of rows exceed it, otherwise 3072; record the choice.
Run: `cd chartist-finetune && .venv/bin/python cap_dataset.py --data data/mlx_v2 --out data/mlx_v2_capped --limit <MAXLEN>` — Expected: drops under 1%.

- [ ] **Step 6: Commit**

```bash
git add chartist-finetune/export_v2.py chartist-finetune/verify_v2_rows.py chartist-finetune/tests/test_export_v2.py chartist-finetune/data/mlx_v2 chartist-finetune/data/mlx_v2_capped
git commit -m "data(finetune): the multi-task v2 dataset, checked and capped"
```

---

## Phase 3 — The v2 adapter on Runpod

### Task 18: Runbook and pod-side fixes

**Files:**
- Create: `chartist-finetune/cloud/RUNBOOK_v2.md`
- Modify: `chartist-finetune/cloud/evaluate_cuda.py` (pyarrow preflight)

**Interfaces:**
- Consumes: `data/mlx_v2_capped` (Task 17), `cloud/train_lora.py` (unchanged; driven by `DATA`, `OUT`, `MAXLEN`, `EPOCHS`).

- [ ] **Step 1: Add the pyarrow preflight to the cloud eval**

In `chartist-finetune/cloud/evaluate_cuda.py`, at the start of `main()`:

```python
    # lora-v1's cloud eval lost 16 treemap rows to pyarrow failing to import
    # (pyarrow._fs._init_ca_paths -> ssl.py). Fail here, before generation, not
    # inside 16 candidates where it reads as a model error.
    try:
        import pyarrow.fs  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"pyarrow does not import on this machine ({exc!r}); "
                         "fix it first: pip install -U pyarrow certifi && export SSL_CERT_FILE=$(python -m certifi)")
```

- [ ] **Step 2: Write the runbook**

`chartist-finetune/cloud/RUNBOOK_v2.md` with these sections, filled in with the values from Task 17:
1. *Gate.* Do not start until the user has approved this run in chat.
2. *Cost read.* Read the A100 80GB price and stock with the Runpod MCP `list-gpu-types` (`include: ["AVAILABILITY"]`, `product: ["POD"]`) and state the hourly price before creating anything. Expected ~2–2.5 hours of pod time.
3. *Create.* A 40 GB HIGH_PERFORMANCE network volume in a data center with A100 stock, then a Secure Cloud pod on image `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`, `gpu.minCudaVersion: "12.8"`, volume mounted at `/workspace`, SSH off.
4. *Upload.* `data/mlx_v2_capped`, `data/testset.jsonl`, `data/schemas.jsonl`, `data/fixtures`, `cloud/train_lora.py`, `cloud/evaluate_cuda.py`, `executor.py`, `_candidate_runner.py`, `chart_types.py`, `contract.py` and the backend contract files it loads, with `runpodctl send`.
5. *Install.* `pip install transformers==5.23.0 peft==0.22.0 accelerate datasets pyarrow certifi plotly pandas` then `python -c "import pyarrow.fs"`.
6. *Train.* `DATA=/workspace/chartist/data/mlx_v2_capped OUT=/workspace/outputs/lora-v2 MAXLEN=<MAXLEN> EPOCHS=2 python cloud/train_lora.py`, with the same assertion that zero linear-attention modules matched.
7. *Evaluate.* `python cloud/evaluate_cuda.py --label lora-v2 --adapter-path /workspace/outputs/lora-v2 --out /workspace/eval_report_v2.json` (frozen 300, question form).
8. *Download and delete.* `runpodctl receive` the adapter and report; delete the pod, then the volume; confirm both are gone with `list-pods` and `list-network-volumes`; read the settled bill the next day with `list-pod-billing`.

- [ ] **Step 3: Commit**

```bash
git add chartist-finetune/cloud/RUNBOOK_v2.md chartist-finetune/cloud/evaluate_cuda.py
git commit -m "docs(finetune): v2 Runpod runbook; fail fast when pyarrow cannot import"
```

### Task 19: [GATED — wait for the user's approval] Train and evaluate on Runpod

- [ ] **Step 1: Ask, with the price read from the catalog, and wait for an explicit yes**
- [ ] **Step 2: Follow `cloud/RUNBOOK_v2.md` sections 2–8**
- [ ] **Step 3: Commit `cloud/eval_report_v2.json`, the adapter config and the settled cost**

### Task 20: Bring v2 home and compare

- [ ] **Step 1: Convert** — `cd chartist-finetune && .venv/bin/python cloud/peft_to_mlx.py --peft cloud/artifacts/out-v2 --out runs/adapters-mlx-v2`, and confirm 128 trained modules have non-zero `lora_b` and every linear-attention adapter is exactly zero.
- [ ] **Step 2: Evaluate locally against v1, same harness** — `evaluate.py --adapter-path runs/adapters-mlx-v2` on the frozen 300 (question form); `measure_planning.py --label lora-v2 --adapter-path runs/adapters-mlx-v2` on the frozen planning set; `measure_roles.py --adapter-path runs/adapters-mlx-v2` for planner and narrator.
- [ ] **Step 3: Switch the server only if v2 is at least as good on the frozen 300 and better on the planning set** — point `ADAPTER` in the Makefile at `runs/adapters-mlx-v2`.
- [ ] **Step 4: Update `AGENTS.md` and `cloud/README.md` with the measured numbers, and commit.**
