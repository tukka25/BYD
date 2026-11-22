# Planner Data Tools and Report Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the planner check facts about the real data with four bounded tools before it plans, hand those facts to the analyst and planner as a short note, check every final chart plan against the real data, and tell the analyst what is already on the report.

**Architecture:** A new `data_tools` module answers four questions over pandas DataFrames with hard output caps. A `discovery` step asks the model, in a call of its own, to call up to 3 of them; the adapter calls tools only when asked (measured 2026-11-23). The results are condensed into a facts note of at most 800 characters. The analyst and planner prompts get that note as an appended section, and the analyst also gets the report memory; the system prompts lora-v2 was trained on stay byte-identical. `preview` also runs on every final chart plan as an objective data check inside the existing retry loop. Report memory is rebuilt from the database on every run, from `report_blocks` and a new `report_requests` table.

**Tech Stack:** Python 3.11 (api container) and 3.13 (host venv), FastAPI, SQLAlchemy 2, pandas 2, LangChain (`bind_tools`, `ToolMessage`), mlx_lm server 0.32.2 (OpenAI-compatible `tool_calls`, `qwen3_coder` parser), pytest.

## Global Constraints

- Never hardcode charts: no code-built figures and no column-picking rules. Every chart is the model's own code; tools return facts about data, never charts.
- Tool results: at most 20 items per list, text values cut to 40 characters, every list states its total, each result at most 1,200 characters of compact JSON. Any cut is marked with `"truncated": true` and an `"omitted"` count, and JSON is never cut mid-structure.
- Discovery budget: at most 3 tool calls per dashboard build; the facts note is at most 800 characters.
- Prompt budget: lora-v2 was trained at MAXLEN 2048 tokens, and today's planner prompts are already 957-1,421 tokens. So the planner gets the facts note only, while the analyst gets the facts note and the report memory (at most 1,000 characters).
- `ANALYST_SYSTEM_PROMPT`, `PLANNER_SYSTEM_PROMPT` and `SPEC_RULES` stay byte-identical; new context goes in appended user-message sections.
- Temperature stays 0.0, and analyst, planner and explorer run with thinking off.
- A tool or discovery failure never fails a build: log it and plan without facts.
- `PLANNER_TOOLS` is "on" or "off". It ships "off" until Task 8's measurement, and the decision rule is in Task 8.
- Backend tests: `cd backend && .venv/bin/python -m pytest -q tests`. Three failures in `tests/test_chartist_contract.py` predate this plan, and no new failure is allowed.
- Commit after every task, with messages ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Measure on the frozen planning set (`chartist-finetune/data/v2/planning_testset.jsonl`, sha256 in `planning_testset.sha256`) and never train on it.

## File Structure

- Create `backend/app/services/agents/data_tools.py`: the four tools as pure functions over DataFrames, the result bounder, tool specs, and `ToolBox` (per-run frames, call budget, the data check for a chart plan).
- Create `backend/app/services/agents/discovery.py`: the explicit tool step, returning `Findings` with the facts note.
- Create `backend/app/services/agents/report_memory.py`: a compact description of a report's charts and past requests.
- Create `backend/app/models/report_request.py`: the `ReportRequest` model. Its new table is created by `create_all` at startup, so no migration is needed.
- Modify `backend/app/models/__init__.py`: register `ReportRequest`.
- Modify `backend/app/services/agents/architect.py`: extract `load_frame()` from `sample_source()`.
- Modify `backend/app/services/agents/planning_contract.py`: problem messages that say what to change, `EXPLORER_*` prompts, `with_context()`, and `check_specs(..., validate=None)`.
- Modify `backend/app/services/agents/planning.py`: `facts`, `memory` and `validate` parameters.
- Modify `backend/app/services/agents/dashboard_flow.py`: the discovery step, its status lines, and memory.
- Modify `backend/app/services/llm.py`: the `explorer` role.
- Modify `backend/app/core/config.py`: `PLANNER_TOOLS`.
- Modify `backend/app/api/v1/endpoints/blocks.py`: record requests, build memory, pass the explorer.
- Create `backend/scripts/smoke_planner_tools.py`: one live dashboard plan with tools, printed.
- Create `chartist-finetune/measure_planning_tools.py`: tools on against tools off on the frozen set.
- Tests: create `backend/tests/test_data_tools.py`, `backend/tests/test_discovery.py` and `backend/tests/test_report_memory.py`; modify `backend/tests/test_planning_contract.py` and `backend/tests/test_dashboard_flow.py`.

---

### Task 1: Check messages that say what to change

The gapminder run on 2026-11-23 lost all three "over time" charts. The model kept `grain: year` on a year column for three tries, because "grain is only for a date column on x" never told it to remove the grain. This task makes every kind problem name the column, its kind, and the fix.

**Files:**
- Modify: `backend/app/services/agents/planning_contract.py` (inside `check_spec`, plus a new `_categories` helper above it)
- Test: `backend/tests/test_planning_contract.py`

**Interfaces:**
- Consumes: `check_spec(item, tables)` and `check_specs(payload, tables)` (existing).
- Produces: the same functions with new message text. No signature changes.

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/test_planning_contract.py`)

```python
SONGS = {"tracks": {"track_name": "text", "playlist_name": "text", "playlist_genre": "category",
                    "playlist_subgenre": "category", "track_popularity": "number", "year": "year",
                    "released": "date"}}


def test_grain_on_a_year_column_says_to_remove_it():
    # gapminder lost all three trend charts to this: grain=year on a year column, three tries
    case = spec(table="tracks", chart="line", x="year", y="track_popularity", agg="mean",
                grain="year", sort="", top_n=0)
    valid, errors = check_specs({"charts": [case]}, SONGS)
    assert valid == [] and "already a year column" in errors[0] and 'grain to ""' in errors[0]


def test_a_treemap_over_free_text_names_the_category_columns():
    case = spec(table="tracks", chart="treemap", x="playlist_genre", group="playlist_name",
                y="track_popularity", agg="sum", sort="", top_n=0)
    valid, errors = check_specs({"charts": [case]}, SONGS)
    assert valid == [] and "'playlist_name' is text" in errors[0] and "playlist_subgenre" in errors[0]


def test_a_bar_without_aggregation_says_which_to_use():
    case = spec(table="tracks", x="playlist_genre", y="track_popularity", agg="none")
    valid, errors = check_specs({"charts": [case]}, SONGS)
    assert valid == [] and "sum, mean or count" in errors[0]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_planning_contract.py -k "year_column or free_text or without_aggregation"`
Expected: 3 failed. The messages lack "already a year column", "'playlist_name' is text" and "sum, mean or count".

- [ ] **Step 3: Implement**

Add above `def check_spec` in `planning_contract.py`:

```python
def _categories(kinds: dict[str, str]) -> str:
    """Where to look instead: the table's category columns, by name."""
    names = [name for name, kind in kinds.items() if kind == "category"]
    if not names:
        return "this table has no category column"
    more = f" (and {len(names) - 6} more)" if len(names) > 6 else ""
    return f"use a category column: {', '.join(names[:6])}{more}"
```

In `check_spec`, replace these `need(...)` lines (keep every other line as it is):

```python
    elif chart == "bar":
        if kx == "text":
            # A name column ("top 10 tracks") works once top_n keeps it short.
            need(0 < top_n <= MAX_TOP_N, f"a bar chart over the text column '{x}' needs top_n between 1 and {MAX_TOP_N}")
        else:
            need(kx in _DIMENSION, "a bar chart needs a category, date or year column on x")
        need(measure, "a bar chart needs a number column as y, or agg count")
        need(agg != "none", f"a bar chart needs agg: sum, mean or count (one bar per '{x}' value)")
    elif chart == "pie":
        need(kx == "category", f"a pie needs a category column on x for the slices; '{x}' is {kx or 'missing'}: {_categories(kinds)}")
        need(measure, "a pie needs a number column as y, or agg count")
        need(agg != "none", "a pie needs agg: sum, mean or count")
```

```python
    elif chart == "box":
        need(ky in _NUMBER, "a box plot needs a number column on y")
        need(not x or kx == "category", f"a box plot's x, if any, must be a category; '{x}' is {kx}: {_categories(kinds)}")
        need(agg == "none", "a box plot shows raw values: agg none")
```

```python
    elif chart in ("treemap", "sunburst"):
        need(kx == "category", f"a {chart} needs a category column on x; '{x}' is {kx or 'missing'}: {_categories(kinds)}")
        need(not group or kg == "category", f"a {chart}'s inner level (group) must be a category; '{group}' is {kg}: {_categories(kinds)}")
        need(measure, f"a {chart} needs a number column as y, or agg count")
        need(agg != "none", f"a {chart} needs agg: sum, mean or count")
    elif chart == "funnel":
        need(kx == "category", f"a funnel needs the stage category on x; '{x}' is {kx or 'missing'}: {_categories(kinds)}")
        need(measure, "a funnel needs a number column as y, or agg count")
        need(agg != "none", "a funnel needs agg: sum, mean or count")
```

Replace the grain check after the kind rules:

```python
    if grain and kx != "date":
        if kx == "year":
            problems.append(f"x '{x}' is already a year column: set grain to \"\"")
        else:
            problems.append(f"grain is only for a date column on x; '{x}' is {kx or 'missing'}: set grain to \"\"")
```

- [ ] **Step 4: Run the whole suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests`
Expected: the 3 new tests pass. The only failures are the 3 known ones in `test_chartist_contract.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/planning_contract.py backend/tests/test_planning_contract.py
git commit -m "fix(planning): check messages that name the column and the fix

gapminder lost its three trend charts: grain=year on a year column failed
'grain is only for a date column on x' three times and the model never
removed it. Kind problems now name the column, its kind, and what to do
(set grain to \"\", or which category columns exist).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `load_frame`, the result bounder, `find_columns`, `inspect_column`

**Files:**
- Modify: `backend/app/services/agents/architect.py` (`sample_source`)
- Create: `backend/app/services/agents/data_tools.py`
- Test: `backend/tests/test_data_tools.py`

**Interfaces:**
- Consumes: `profiler.profile_column(name, series) -> ColumnProfile` and `architect.spread_sample(frame, rows) -> DataFrame` (existing).
- Produces:
  - `architect.load_frame(source: dict, data_dir) -> pd.DataFrame` reads the whole source.
  - `data_tools.bounded(result: dict, limit: int = RESULT_CHARS) -> str`.
  - `data_tools.find_columns(tables: dict[str, pd.DataFrame], query: str, limit: int = 10) -> dict` returns keys `fact`, `matches`, `total`.
  - `data_tools.inspect_column(frame, table: str, column: str, detail: str = "concise") -> dict` returns key `fact`, plus `kind`, `rows`, `nulls`, `distinct`, and kind-specific keys.
  - Constants `MAX_ITEMS = 20`, `TEXT_CHARS = 40`, `RESULT_CHARS = 1200`, `KIND_SAMPLE = 2000`.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_data_tools.py`)

```python
"""The planner's data tools: facts about the real data, always bounded."""
import json

import pandas as pd

from app.services.agents.data_tools import RESULT_CHARS, bounded, find_columns, inspect_column

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TRACKS = pd.DataFrame({
    "track_name": ["Poison"] * 3 + [f"Song {i}" for i in range(37)],
    "playlist_genre": ["pop", "rap", "rock", "edm"] * 10,
    "track_popularity": [10, 20, 30, 40] * 10,
    "released": ["2019-01-01"] * 10 + [f"2019-{1 + i % 9:02d}-{10 + i % 9}" for i in range(30)],
    "weekday": (DAYS * 6)[:40],
})


def test_find_columns_matches_names_and_values():
    by_name = find_columns({"tracks": TRACKS}, "genre")
    by_value = find_columns({"tracks": TRACKS}, "pop")
    assert by_name["matches"][0]["column"] == "playlist_genre"
    assert by_value["matches"][0]["column"] == "playlist_genre"


def test_find_columns_says_when_nothing_matches_and_offers_the_measures():
    found = find_columns({"tracks": TRACKS}, "listens")
    assert found["matches"] == [] and "No column matches 'listens'" in found["fact"]
    assert "tracks.track_popularity" in found["fact"]


def test_find_columns_caps_a_wide_table():
    wide = pd.DataFrame({f"metric_{i}": [1.0, 2.0] for i in range(400)})
    found = find_columns({"wide": wide}, "metric")
    assert len(found["matches"]) == 10 and found["total"] == 400
    assert len(bounded(found)) <= RESULT_CHARS


def test_inspect_reports_values_that_repeat():
    facts = inspect_column(TRACKS, "tracks", "track_name")
    assert facts["values_on_more_than_one_row"] == 1 and "up to 3 rows" in facts["fact"]


def test_inspect_flags_year_only_dates():
    facts = inspect_column(TRACKS, "tracks", "released")
    assert facts["on_1_january"] == 0.25 and "1 January" in facts["fact"]


def test_inspect_finds_a_natural_order():
    assert inspect_column(TRACKS, "tracks", "weekday")["natural_order"] == "Monday to Sunday"


def test_inspect_gives_quartiles_for_numbers():
    facts = inspect_column(TRACKS, "tracks", "track_popularity")
    assert (facts["median"], facts["p25"], facts["p75"]) == (25.0, 17.5, 32.5)


def test_bounded_marks_what_it_cut():
    text = bounded({"fact": "x", "values": ["v" * 30] * 1000})
    parsed = json.loads(text)
    assert len(text) <= RESULT_CHARS and parsed["truncated"] is True
    assert len(parsed["values"]) + parsed["omitted"]["values"] == 1000
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_data_tools.py`
Expected: an ImportError on `app.services.agents.data_tools`.

- [ ] **Step 3: Implement**

In `architect.py`, replace `sample_source` with:

```python
def load_frame(source: Dict[str, Any], data_dir: Any) -> pd.DataFrame:
    """The whole of a source as a DataFrame: a database table, or a file read in full."""
    if source.get("type") == "db":
        from app.services import db_sources

        return db_sources.load_table_by_id(str(source["source_id"]), str(source["table"]))

    from pathlib import Path

    path = Path(str(source.get("path") or source.get("name")))
    if not path.exists():
        path = Path(str(data_dir)) / str(source.get("name"))
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    return pd.read_csv(path)


def sample_source(source: Dict[str, Any], data_dir: Any, rows: int = SAMPLE_ROWS) -> pd.DataFrame:
    """A bounded sample of whichever kind of source this is, drawn from all of it.

    Files are read whole to draw from: a chart reads the whole file anyway.
    """
    return spread_sample(load_frame(source, data_dir), rows)
```

Create `backend/app/services/agents/data_tools.py`:

```python
"""Facts about the real data, for the planner to check before it plans.

Four tools, each a pure function over pandas DataFrames, each with a hard cap
on what it returns. A model that asks about a 400-column table gets 10 matches
and a count, never the table. Tools answer questions about data; they never
draw or choose a chart, and every chart stays the model's own code.
"""
from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

from app.services.agents.profiler import profile_column

MAX_ITEMS = 20         # the longest list any tool returns
TEXT_CHARS = 40        # a longer text value is cut, with an ellipsis
RESULT_CHARS = 1200    # about 300 tokens: the most one result may cost
KIND_SAMPLE = 2000     # same as the profile's sample, so a tool and the checks agree on a kind
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december")


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _short(value: Any) -> str:
    text = str(value)
    return text if len(text) <= TEXT_CHARS else text[: TEXT_CHARS - 1] + "…"


def _num(value: Any) -> float:
    """Three significant figures: enough to compare, cheap to read."""
    return float(f"{float(value):.3g}")


def _tokens(text: Any) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))
    words = re.split(r"[^A-Za-z0-9]+", spaced.lower())
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if len(w) >= 2]


def _kind(series: pd.Series) -> str:
    """The kind the planner's profile gives this column, from the same-size sample."""
    from app.services.agents.architect import spread_sample

    sample = spread_sample(series.to_frame(), KIND_SAMPLE)[series.name]
    return profile_column(str(series.name), sample).kind


def bounded(result: dict[str, Any], limit: int = RESULT_CHARS) -> str:
    """Compact JSON no longer than `limit`. Lists are halved until it fits, and
    every cut is reported (`truncated`, `omitted`) rather than hidden."""
    out = dict(result)
    omitted: dict[str, int] = {}

    def render() -> str:
        return _dump({**out, "truncated": True, "omitted": omitted} if omitted else out)

    text = render()
    while len(text) > limit:
        lists = [key for key, value in out.items() if isinstance(value, list) and len(value) > 1]
        if not lists:
            return _dump({"fact": str(out.get("fact", ""))[: limit // 2], "truncated": True})
        key = max(lists, key=lambda k: len(_dump(out[k])))
        keep = len(out[key]) // 2
        omitted[key] = omitted.get(key, 0) + len(out[key]) - keep
        out[key] = out[key][:keep]
        text = render()
    return text


def find_columns(tables: dict[str, pd.DataFrame], query: str, limit: int = 10) -> dict[str, Any]:
    """Columns whose name or common values match the query, across every table."""
    wanted = _tokens(query)
    if not wanted:
        return {"fact": "Give a word to search for, such as 'country' or 'revenue'.", "matches": [], "total": 0}
    found = []
    for table, frame in tables.items():
        for column in frame.columns:
            names = _tokens(column)
            score = sum(1 for w in wanted if any(n.startswith(w) or w.startswith(n) for n in names))
            top = set(frame[column].dropna().astype(str).str.lower().value_counts().head(MAX_ITEMS).index)
            score += sum(1 for w in wanted if w in top)
            if score:
                found.append((score, table, str(column)))
    found.sort(key=lambda item: (-item[0], item[1], item[2]))
    shown = []
    for _, table, column in found[: min(limit, MAX_ITEMS)]:
        series = tables[table][column]
        shown.append({"table": table, "column": column, "kind": _kind(series),
                      "distinct": int(series.nunique()),
                      "examples": [_short(v) for v in series.dropna().unique()[:3]]})
    if shown:
        names = ", ".join(f"{m['table']}.{m['column']}" for m in shown[:5])
        more = f" ({len(found)} in all)" if len(found) > len(shown) else ""
        fact = f"Columns matching '{query}': {names}{more}"
    else:
        measures = [f"{t}.{c}" for t, f in tables.items() for c in f.columns if _kind(f[c]) == "number"][:6]
        fact = f"No column matches '{query}'." + (f" Number columns: {', '.join(measures)}." if measures else "")
    return {"fact": fact, "matches": shown, "total": len(found)}


def _natural_order(values: Any) -> str:
    lowered = {str(v).strip().lower() for v in values}
    for names, label in ((WEEKDAYS, "Monday to Sunday"), (MONTHS, "January to December")):
        if lowered and (lowered <= set(names) or lowered <= {n[:3] for n in names}):
            return label
    return ""


def inspect_column(frame: pd.DataFrame, table: str, column: str, detail: str = "concise") -> dict[str, Any]:
    """Facts about one column on the full table."""
    series = frame[column]
    values = series.dropna()
    kind = _kind(series)
    out: dict[str, Any] = {"table": table, "column": column, "kind": kind, "rows": int(len(series)),
                           "nulls": int(series.isna().sum()), "distinct": int(values.nunique())}
    facts = [f"{table}.{column}: {kind}, {out['distinct']:,} distinct in {out['rows']:,} rows"]
    if out["nulls"]:
        facts.append(f"{out['nulls']:,} empty")
    if kind in ("number", "year") and pd.api.types.is_numeric_dtype(values):
        q = values.quantile([0, 0.25, 0.5, 0.75, 1.0]).tolist()
        out.update(min=_num(q[0]), p25=_num(q[1]), median=_num(q[2]), p75=_num(q[3]), max=_num(q[4]),
                   mean=_num(values.mean()))
        facts.append(f"median {out['median']}, middle half {out['p25']} to {out['p75']}, "
                     f"range {out['min']} to {out['max']}")
    elif kind == "date":
        dates = pd.to_datetime(values, errors="coerce", format="mixed").dropna()
        if len(dates):
            jan1 = float(((dates.dt.month == 1) & (dates.dt.day == 1)).mean())
            first = float((dates.dt.day == 1).mean())
            out.update(first=str(dates.min().date()), last=str(dates.max().date()),
                       on_1_january=round(jan1, 3), on_1st_of_month=round(first, 3))
            facts.append(f"{out['first']} to {out['last']}")
            if jan1 > 0.05:
                facts.append(f"{jan1:.0%} fall on 1 January (likely year-only dates)")
            elif first > 0.5:
                facts.append(f"{first:.0%} fall on the 1st (likely month-only dates)")
    else:
        counts = values.astype(str).value_counts()
        out["top"] = [{"value": _short(v), "rows": int(c)}
                      for v, c in counts.head(MAX_ITEMS if detail == "detailed" else 5).items()]
        repeats = int((counts > 1).sum())
        if kind in ("text", "id") and repeats:
            out["values_on_more_than_one_row"] = repeats
            facts.append(f"{repeats:,} values appear on more than one row (up to {int(counts.max())} rows)")
        order = _natural_order(counts.index)
        if order:
            out["natural_order"] = order
            facts.append(f"values have a natural order: {order}")
    out["fact"] = "; ".join(facts)
    return out
```

- [ ] **Step 4: Run the tests and the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_data_tools.py tests/test_sample_source.py && .venv/bin/python -m pytest -q tests`
Expected: `test_data_tools.py` gives 8 passed and `test_sample_source.py` 6 passed. The suite shows only the 3 known failures.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/architect.py backend/app/services/agents/data_tools.py backend/tests/test_data_tools.py
git commit -m "feat(tools): find_columns and inspect_column, bounded

Facts about the real data for the planner: columns matching a word (10
matches and a total, never a full listing), and one column's kind, spread,
repeats, date precision and natural order. Every result is compact JSON of
at most 1,200 characters with explicit truncation markers. load_frame
reads a whole source; sample_source now draws from it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `relationship`, `preview`, and the `ToolBox`

**Files:**
- Modify: `backend/app/services/agents/data_tools.py` (append)
- Test: `backend/tests/test_data_tools.py` (append)

**Interfaces:**
- Consumes: Task 2's `bounded`, `_kind`, `_short`, `_num`, `_tokens` and `find_columns`/`inspect_column`; `architect.load_frame`.
- Produces:
  - `relationship(frame, table, a, b) -> dict` returns key `fact`.
  - `preview(frame, table, x, y="", agg="sum", group="", top_n=0, grain="") -> dict` returns keys `fact`, `rows_used`, `groups` (or `points`), `shown`, `first`, and optionally `rows_per_x`.
  - `ToolCall(name: str, args: dict, result: str, fact: str)` dataclass.
  - `ToolBox(sources: dict[str, dict], data_dir: str, max_calls: int = MAX_CALLS, loader=None)` with `.specs -> list[dict]` (OpenAI tool format), `.call(name, args) -> str`, `.exhausted -> bool`, `.facts() -> list[str]`, `.calls: list[ToolCall]` and `.validate_spec(spec: dict) -> list[str]`.
  - Constants `MAX_CALLS = 3`, `LINE_POINTS = 1000`, and `CAPS = {"bar": 50, "waterfall": 50, "pie": 12, "funnel": 12, "treemap": 200, "sunburst": 200, "heatmap": 2500}`.

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/test_data_tools.py`)

```python
from app.services.agents.data_tools import ToolBox, preview, relationship


def toolbox(**frames):
    return ToolBox({name: {"type": "file", "name": name} for name in frames}, "",
                   loader=lambda source, data_dir: frames[source["name"]])


def test_relationship_between_two_numbers_is_a_correlation():
    frame = pd.DataFrame({"a": [1, 2, 3, 4, 5, 6], "b": [2, 4, 6, 8, 10, 13]})
    facts = relationship(frame, "t", "a", "b")
    assert facts["correlation"] > 0.99 and "strong correlation" in facts["fact"]


def test_relationship_between_a_category_and_a_number_is_a_mean_per_group():
    facts = relationship(TRACKS, "tracks", "playlist_genre", "track_popularity")
    assert facts["groups"] == 4 and len(facts["means"]) == 4


def test_preview_says_a_sum_adds_up_repeated_names():
    facts = preview(TRACKS, "tracks", "track_name", "track_popularity", "sum", top_n=5)
    assert facts["groups"] == 38 and facts["shown"] == 5
    assert facts["rows_per_x"] == {"min": 1, "max": 3} and "sums 1 to 3 rows" in facts["fact"]


def test_the_toolbox_teaches_when_a_column_is_wrong():
    box = toolbox(tracks=TRACKS)
    reply = json.loads(box.call("inspect_column", {"table": "tracks", "column": "genre"}))
    assert "not a column of 'tracks'" in reply["error"] and "playlist_genre" in reply["error"]


def test_the_toolbox_stops_at_its_budget():
    box = toolbox(tracks=TRACKS)
    for _ in range(3):
        box.call("find_columns", {"query": "genre"})
    reply = json.loads(box.call("find_columns", {"query": "genre"}))
    assert box.exhausted and "budget" in reply["error"] and len(box.calls) == 3


def test_validate_refuses_a_bar_per_row_and_accepts_it_cut_to_top_n():
    names = pd.DataFrame({"name": [f"n{i}" for i in range(60)], "v": range(60)})
    box = toolbox(t=names)
    bar = {"chart": "bar", "table": "t", "x": "name", "y": "v", "agg": "sum", "group": "", "top_n": 0, "grain": ""}
    assert "60 bars" in box.validate_spec(bar)[0]
    assert box.validate_spec({**bar, "top_n": 20}) == []


def test_validate_refuses_a_line_through_every_raw_row():
    rows = pd.DataFrame({"t": range(1500), "v": range(1500)})
    line = {"chart": "line", "table": "r", "x": "t", "y": "v", "agg": "none", "group": "", "top_n": 0, "grain": ""}
    assert "1,500 points" in toolbox(r=rows).validate_spec(line)[0]
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_data_tools.py`
Expected: an ImportError on `ToolBox`, `preview` or `relationship`.

- [ ] **Step 3: Implement** (append to `data_tools.py`; add `from dataclasses import dataclass` and `from typing import Callable` to its imports)

```python
MAX_CALLS = 3          # tool calls per dashboard build
LINE_POINTS = 1000     # more points than this on one line chart is unreadable
CAPS = {"bar": 50, "waterfall": 50, "pie": 12, "funnel": 12, "treemap": 200, "sunburst": 200, "heatmap": 2500}
GRAIN_FREQ = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}
AGGS = ("sum", "mean", "median", "count", "min", "max", "none")
TOOL_NAMES = ("find_columns", "inspect_column", "relationship", "preview")


def relationship(frame: pd.DataFrame, table: str, a: str, b: str) -> dict[str, Any]:
    """How two columns relate: a correlation, a mean per group, or the combinations present."""
    ka, kb = _kind(frame[a]), _kind(frame[b])
    pair = frame[[a, b]].dropna()
    out: dict[str, Any] = {"table": table, "a": a, "b": b, "kinds": [ka, kb], "rows": int(len(pair))}
    if ka == "number" and kb == "number":
        r = pair[a].corr(pair[b])
        if pd.isna(r):
            out["fact"] = f"{a} vs {b}: no correlation can be measured (a column is constant)"
            return out
        out["correlation"] = round(float(r), 2)
        strength = "strong" if abs(r) >= 0.6 else "moderate" if abs(r) >= 0.3 else "weak"
        out["fact"] = f"{a} vs {b}: {strength} correlation {r:.2f} over {len(pair):,} rows"
    elif "number" in (ka, kb):
        group, measure = (a, b) if kb == "number" else (b, a)
        means = pair.groupby(group)[measure].agg(["mean", "size"]).sort_values("size", ascending=False)
        out["groups"] = int(len(means))
        out["means"] = [{"value": _short(key), "mean": _num(row["mean"]), "rows": int(row["size"])}
                        for key, row in means.head(10).iterrows()]
        out["fact"] = (f"mean {measure} by {group}: {_num(means['mean'].min())} to "
                       f"{_num(means['mean'].max())} across {len(means):,} groups")
    else:
        combos = pair.groupby([a, b]).size().sort_values(ascending=False)
        out["combinations"] = int(len(combos))
        out["top_pairs"] = [{"pair": [_short(x), _short(y)], "rows": int(n)} for (x, y), n in combos.head(10).items()]
        out["fact"] = f"{a} x {b}: {len(combos):,} combinations present"
    return out


def preview(frame: pd.DataFrame, table: str, x: str, y: str = "", agg: str = "sum", group: str = "",
            top_n: int = 0, grain: str = "") -> dict[str, Any]:
    """What a chart over these columns would show on the real data. Facts, not a chart."""
    columns = [c for c in (x, y, group) if c]
    data = frame[columns].dropna()
    out: dict[str, Any] = {"table": table, "rows_used": int(len(data)),
                           "rows_dropped_empty": int(len(frame) - len(data))}
    if agg == "none" or not x:
        out["points"] = out["shown"] = int(len(data))
        dropped = f"; {out['rows_dropped_empty']:,} rows with empty values left out" if out["rows_dropped_empty"] else ""
        out["fact"] = f"{len(data):,} raw points{dropped}"
        return out
    if grain in GRAIN_FREQ:
        stamps = pd.to_datetime(data[x], errors="coerce", format="mixed")
        data = data.assign(**{x: stamps.dt.to_period(GRAIN_FREQ[grain]).astype(str)})
    keys = [x] + ([group] if group else [])
    grouped = data.groupby(keys)
    values = grouped.size() if (agg == "count" or not y) else getattr(grouped[y], agg)()
    out["groups"] = int(len(values))
    if top_n:
        values = values.sort_values(ascending=False).head(top_n)
    out["shown"] = int(len(values))
    out["first"] = [{"key": [_short(k) for k in (key if isinstance(key, tuple) else (key,))], "value": _num(v)}
                    for key, v in values.head(10).items()]
    fact = f"{out['groups']:,} groups" + (f", top {out['shown']} shown" if top_n else "")
    if y and agg == "sum" and _kind(frame[x]) in ("text", "id"):
        per_x = data.groupby(x).size()
        if int(per_x.max()) > 1:
            out["rows_per_x"] = {"min": int(per_x.min()), "max": int(per_x.max())}
            fact += f"; each {x} value sums {out['rows_per_x']['min']} to {out['rows_per_x']['max']} rows"
    out["fact"] = fact
    return out


def tool_specs(tables: list[str]) -> list[dict[str, Any]]:
    """The four tools in the OpenAI format mlx_lm server forwards to the chat template."""
    table = {"type": "string", "enum": tables}
    def spec(name: str, description: str, properties: dict, required: list[str]) -> dict:
        return {"type": "function", "function": {"name": name, "description": description, "parameters": {
            "type": "object", "properties": properties, "required": required}}}
    return [
        spec("find_columns", "Search every table for columns whose name or common values match a word. "
             "Use it instead of listing columns; returns at most 10 matches and a total.",
             {"query": {"type": "string"}}, ["query"]),
        spec("inspect_column", "Facts about one column on the full table: kind, distinct values, empties, "
             "quartiles, top values, whether values repeat, date precision, natural order.",
             {"table": table, "column": {"type": "string"},
              "detail": {"type": "string", "enum": ["concise", "detailed"]}}, ["table", "column"]),
        spec("relationship", "How two columns of a table relate: correlation for two numbers, the mean per "
             "group for a category and a number, the combinations present for two categories.",
             {"table": table, "a": {"type": "string"}, "b": {"type": "string"}}, ["table", "a", "b"]),
        spec("preview", "What a chart over these columns would show on the real data: rows used, groups, "
             "the first values, and whether a sum adds up repeated rows.",
             {"table": table, "x": {"type": "string"}, "y": {"type": "string"},
              "agg": {"type": "string", "enum": list(AGGS)}, "group": {"type": "string"},
              "top_n": {"type": "integer"},
              "grain": {"type": "string", "enum": ["", *GRAIN_FREQ]}}, ["table", "x"]),
    ]


@dataclass
class ToolCall:
    name: str
    args: dict
    result: str
    fact: str


class ToolBox:
    """One run's tools: the tables it may read (loaded once, on first use), its
    call budget, and the facts found so far."""

    def __init__(self, sources: dict[str, dict], data_dir: str, max_calls: int = MAX_CALLS,
                 loader: Callable[[dict, str], pd.DataFrame] | None = None):
        self.sources = sources
        self.data_dir = data_dir
        self.max_calls = max_calls
        self._loader = loader
        self._frames: dict[str, pd.DataFrame] = {}
        self.calls: list[ToolCall] = []

    @property
    def specs(self) -> list[dict[str, Any]]:
        return tool_specs(list(self.sources))

    @property
    def exhausted(self) -> bool:
        return len(self.calls) >= self.max_calls

    def frame(self, table: str) -> pd.DataFrame:
        if table not in self.sources:
            raise KeyError(f"no table '{table}'; tables are: {', '.join(self.sources)}")
        if table not in self._frames:
            load = self._loader
            if load is None:
                from app.services.agents.architect import load_frame as load
            self._frames[table] = load(self.sources[table], self.data_dir)
        return self._frames[table]

    def _with(self, table: str, *columns: str) -> pd.DataFrame:
        frame = self.frame(table)
        for column in columns:
            if column and column not in frame.columns:
                near = [str(c) for c in frame.columns if set(_tokens(c)) & set(_tokens(column))][:5]
                hint = (f"; columns like it: {', '.join(near)}" if near
                        else f"; use find_columns to search its {len(frame.columns)} columns")
                raise KeyError(f"'{column}' is not a column of '{table}'{hint}")
        return frame

    def call(self, name: str, args: dict | None) -> str:
        if self.exhausted:
            return bounded({"error": f"the tool budget ({self.max_calls} calls) is used up: answer now"})
        args = dict(args or {})
        try:
            result = self._run(name, args)
        except (KeyError, ValueError, TypeError) as exc:
            # args[0], not str(exc): str() of a KeyError wraps the message in quotes.
            result = {"error": str(exc.args[0]) if exc.args else str(exc)}
        text = bounded(result)
        self.calls.append(ToolCall(name, args, text, str(result.get("fact", ""))))
        return text

    def _run(self, name: str, args: dict) -> dict[str, Any]:
        if name == "find_columns":
            return find_columns({t: self.frame(t) for t in self.sources}, str(args.get("query", "")))
        table = str(args.get("table", ""))
        if name == "inspect_column":
            column = str(args.get("column", ""))
            return inspect_column(self._with(table, column), table, column, str(args.get("detail") or "concise"))
        if name == "relationship":
            a, b = str(args.get("a", "")), str(args.get("b", ""))
            return relationship(self._with(table, a, b), table, a, b)
        if name == "preview":
            x, y, group = str(args.get("x", "")), str(args.get("y") or ""), str(args.get("group") or "")
            agg = str(args.get("agg") or "sum")
            if agg not in AGGS:
                raise ValueError(f"agg '{agg}' is not one of: {', '.join(AGGS)}")
            frame = self._with(table, x, y, group)
            return preview(frame, table, x, y, agg, group, int(args.get("top_n") or 0), str(args.get("grain") or ""))
        raise ValueError(f"no tool '{name}'; tools are: {', '.join(TOOL_NAMES)}")

    def facts(self) -> list[str]:
        return [call.fact for call in self.calls if call.fact]

    def validate_spec(self, spec: dict) -> list[str]:
        """Objective problems a planned chart would have on the real data. Not a
        judgement of taste: only what cannot be drawn readably."""
        chart = spec.get("chart")
        if chart in ("kpi", "scatter", "histogram", "box"):
            return []
        try:
            shown = preview(self.frame(spec["table"]), spec["table"], spec.get("x", ""), spec.get("y", ""),
                            spec.get("agg", "sum"), spec.get("group", ""), int(spec.get("top_n") or 0),
                            spec.get("grain", ""))
        except Exception:  # noqa: BLE001 - a check that cannot run is not a problem with the plan
            return []
        if shown.get("rows_used") == 0:
            return [f"'{spec.get('y') or spec.get('x')}' has no values to plot: every row is empty"]
        n = int(shown.get("shown", 0))
        if chart in ("line", "area") and n > LINE_POINTS:
            return [f"would draw {n:,} points on a line: aggregate it (agg, or a grain for dates)"]
        cap = CAPS.get(chart)
        if cap and n > cap:
            unit = "cells" if chart == "heatmap" else "bars" if chart in ("bar", "waterfall") else "pieces"
            return [f"would draw {n:,} {unit}, more than {cap}: set top_n or use a coarser column"]
        return []
```

- [ ] **Step 4: Run the tests and the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_data_tools.py && .venv/bin/python -m pytest -q tests`
Expected: 15 passed in `test_data_tools.py`, and only the 3 known failures in the suite.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/data_tools.py backend/tests/test_data_tools.py
git commit -m "feat(tools): relationship, preview and a budgeted ToolBox

relationship measures how two columns relate; preview says what a chart
over given columns would show on the real data, including when a sum adds
up repeated names. ToolBox loads each table once, caps a run at 3 calls,
teaches on a wrong column, and validates a chart plan against the real
data (more bars, slices or line points than can be read).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The discovery step, the explorer role, the `PLANNER_TOOLS` setting

**Files:**
- Create: `backend/app/services/agents/discovery.py`
- Modify: `backend/app/services/agents/planning_contract.py` (add `EXPLORER_SYSTEM_PROMPT` and `EXPLORER_USER_TEMPLATE` after `FIX_PROMPT`)
- Modify: `backend/app/services/llm.py` (`explorer` role)
- Modify: `backend/app/core/config.py` (`PLANNER_TOOLS`)
- Test: `backend/tests/test_discovery.py`

**Interfaces:**
- Consumes: `ToolBox` (`.specs`, `.call`, `.exhausted`, `.facts()`, `.calls`) and `ToolCall` from Task 3; `profiler.render_profiles`; `planning_contract.NO_REQUEST`.
- Produces:
  - `discovery.Probe(name: str, args: dict)`.
  - `discovery.Findings(facts: list[str], calls: list[ToolCall])`, whose `.note -> str` holds bullet lines of at most `FACTS_CHARS = 800`.
  - `discovery.discover(llm, request: str, profiles: list[TableProfile], toolbox: ToolBox) -> Generator[Probe, None, Findings]`.
  - `get_llm("explorer")`.
  - `Settings.PLANNER_TOOLS: str = "off"`.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_discovery.py`)

```python
"""The tool step: the model checks facts before planning, within a budget."""
import pandas as pd
from langchain_core.messages import AIMessage, ToolMessage

from app.services.agents.data_tools import ToolBox
from app.services.agents.discovery import FACTS_CHARS, Findings, Probe, discover
from app.services.agents.profiler import profile_table

TRACKS = pd.DataFrame({"track_name": ["Poison"] * 3 + [f"Song {i}" for i in range(37)],
                       "track_popularity": [10, 20, 30, 40] * 10})
PROFILES = [profile_table("tracks", TRACKS)]


class ToolScripted:
    """A stand-in tool-calling model: replies in order, records what it was sent."""

    def __init__(self, *replies):
        self.replies, self.seen, self.tools = list(replies), [], None

    def bind_tools(self, specs):
        self.tools = specs
        return self

    def invoke(self, messages):
        self.seen.append(list(messages))
        return self.replies.pop(0)


def calls(*items):
    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"c{i}"} for i, (n, a) in enumerate(items)])


def box():
    return ToolBox({"tracks": {"type": "file", "name": "tracks"}}, "", loader=lambda source, data_dir: TRACKS)


def run(gen):
    probes = []
    while True:
        try:
            probes.append(next(gen))
        except StopIteration as done:
            return probes, done.value


def test_the_models_tool_calls_run_and_their_facts_are_kept():
    model = ToolScripted(calls(("inspect_column", {"table": "tracks", "column": "track_name"})), AIMessage(content="DONE"))
    probes, findings = run(discover(model, "most listened songs", PROFILES, box()))
    assert probes == [Probe("inspect_column", {"table": "tracks", "column": "track_name"})]
    assert len(findings.facts) == 1 and "more than one row" in findings.facts[0]
    tool_reply = model.seen[1][-1]
    assert isinstance(tool_reply, ToolMessage) and tool_reply.tool_call_id == "c0"
    assert [t["function"]["name"] for t in model.tools] == ["find_columns", "inspect_column", "relationship", "preview"]


def test_the_step_stops_at_the_budget():
    five = calls(*[("find_columns", {"query": "track"})] * 5)
    model = ToolScripted(five)
    _, findings = run(discover(model, "", PROFILES, box()))
    assert len(findings.calls) == 3 and len(model.seen) == 1
    assert sum(isinstance(m, ToolMessage) for m in model.seen[0]) == 0  # results go after the reply, not before


def test_a_model_without_tool_support_gives_no_facts():
    probes, findings = run(discover(object(), "", PROFILES, box()))
    assert probes == [] and findings.facts == []


def test_a_model_that_answers_without_tools_gives_no_facts():
    _, findings = run(discover(ToolScripted(AIMessage(content="DONE")), "", PROFILES, box()))
    assert findings.facts == [] and findings.note == ""


def test_the_note_is_cut_whole_at_the_limit():
    note = Findings(facts=["x" * 300] * 5).note
    assert len(note) <= FACTS_CHARS and all(line == "- " + "x" * 300 for line in note.splitlines())
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_discovery.py`
Expected: an ImportError on `app.services.agents.discovery`.

- [ ] **Step 3: Implement**

Append after `FIX_PROMPT` in `planning_contract.py`:

```python
# The tool step's own call: the adapter calls tools only when asked to (measured
# 2026-11-23), so this asks. Its transcript never reaches the planning calls;
# only the facts found do, as a short note.
EXPLORER_SYSTEM_PROMPT = """You check facts about the user's tables before a dashboard is planned. You see only a short description of the data, so call the tools to check what would change the plan:
- whether a column the request needs exists (find_columns),
- whether names repeat, how dates are recorded, how a measure is spread (inspect_column),
- whether two columns relate (relationship),
- whether a question has a real answer (preview).
Call at most 3 tools, one at a time. When you have checked what matters, reply DONE."""

EXPLORER_USER_TEMPLATE = """Request: {request}

Tables:
{profiles}

Check the facts this request depends on before anyone plans charts."""
```

Create `backend/app/services/agents/discovery.py`:

```python
"""The planner's tool step: the model checks facts about the data before it plans.

The adapter calls tools when it is asked to and not otherwise (measured
2026-11-23: offered tools with the real analyst prompt, it called none). So this
step asks explicitly, in a call of its own, and hands the planning calls only
what it found, condensed to a few lines. The tool transcript never reaches them,
and they stay in the format lora-v2 was trained on.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Generator

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.services.agents.data_tools import ToolBox, ToolCall
from app.services.agents.planning_contract import EXPLORER_SYSTEM_PROMPT, EXPLORER_USER_TEMPLATE, NO_REQUEST
from app.services.agents.profiler import TableProfile, render_profiles

logger = logging.getLogger(__name__)

FACTS_CHARS = 800  # about 200 tokens: what the facts note may add to each planning call


@dataclass
class Probe:
    """A tool call about to run, for the progress line."""

    name: str
    args: dict


@dataclass
class Findings:
    facts: list[str] = field(default_factory=list)
    calls: list[ToolCall] = field(default_factory=list)

    @property
    def note(self) -> str:
        """The facts as bullet lines, whole lines only, at most FACTS_CHARS."""
        lines: list[str] = []
        used = 0
        for fact in self.facts:
            line = f"- {fact}"
            if used + len(line) + (1 if lines else 0) > FACTS_CHARS:
                break
            used += len(line) + (1 if lines else 0)
            lines.append(line)
        return "\n".join(lines)


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
    while not toolbox.exhausted:
        try:
            reply = bound.invoke(messages)
        except Exception as exc:  # noqa: BLE001 - a failed step never fails the build
            logger.warning("[discovery] model call failed: %s", exc)
            break
        requested = list(getattr(reply, "tool_calls", None) or [])
        if not requested:
            break
        messages.append(reply)
        for call in requested:
            name, args, call_id = str(call.get("name", "")), dict(call.get("args") or {}), call.get("id") or ""
            if toolbox.exhausted:
                messages.append(ToolMessage(content='{"error":"tool budget used up"}', tool_call_id=call_id))
                continue
            yield Probe(name, args)
            messages.append(ToolMessage(content=toolbox.call(name, args), tool_call_id=call_id))
    findings = Findings(facts=toolbox.facts(), calls=list(toolbox.calls))
    logger.info("[discovery] %d tool call(s): %s", len(findings.calls),
                "; ".join(f"{c.name}({c.args})" for c in findings.calls))
    return findings
```

In `backend/app/services/llm.py`:

```python
Role = Literal["planner", "chartist", "detective", "narrator", "analyst", "spec_planner", "explorer"]
```

Add `"explorer": 256,` to `_MAX_TOKENS` (a tool call is short), and set `_NO_THINKING = {"analyst", "spec_planner", "explorer"}`.

In `backend/app/core/config.py`, after `DASHBOARD_PLANNER`:

```python
    # "on": before a dashboard is planned, the model checks facts about the data
    # with bounded tools (agents/data_tools.py, agents/discovery.py) and every
    # final chart plan is checked against the real data. "off" until measured
    # on the frozen planning set (chartist-finetune/measure_planning_tools.py).
    PLANNER_TOOLS: str = "off"
```

- [ ] **Step 4: Run the tests and the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_discovery.py && .venv/bin/python -m pytest -q tests`
Expected: 5 passed, and only the 3 known failures in the suite.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/discovery.py backend/app/services/agents/planning_contract.py backend/app/services/llm.py backend/app/core/config.py backend/tests/test_discovery.py
git commit -m "feat(planning): an explicit tool step that hands back a facts note

The adapter calls tools only when asked, so a separate explorer call asks
it to check up to 3 facts with the data tools. Only the facts reach the
planning calls (at most 800 characters), never the transcript. A backend
without tool support, or a failed call, gives no facts and no error.
PLANNER_TOOLS ships off until measured.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Facts, memory and data checks in the planning calls and the dashboard flow

**Files:**
- Modify: `backend/app/services/agents/planning_contract.py` (`with_context`, `check_specs(..., validate=None)`, import `Callable`)
- Modify: `backend/app/services/agents/planning.py`
- Modify: `backend/app/services/agents/dashboard_flow.py`
- Test: `backend/tests/test_dashboard_flow.py` (append)

**Interfaces:**
- Consumes: `discover`, `Findings` and `Probe` (Task 4); `ToolBox.validate_spec` (Task 3).
- Produces:
  - `planning_contract.with_context(text: str, facts: str = "", memory: str = "") -> str`.
  - `planning_contract.check_specs(payload, tables, validate: Callable[[dict], list[str]] | None = None)`.
  - `planning.propose_directions_steps(llm, request, profiles, facts: str = "", memory: str = "")` and `propose_directions(...)` with the same parameters.
  - `planning.plan_charts_steps(llm, directions, profiles, facts: str = "", validate=None)` and `plan_charts(...)` with the same parameters.
  - `dashboard_flow.build_dashboard(brief, sources, data_dir, analyst_llm, planner_llm, chartist, top=0, explorer_llm=None, memory="")`. The `plan` event gains `"facts": list[str]`.

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/test_dashboard_flow.py`)

```python
from langchain_core.messages import AIMessage


class Recorder(Scripted):
    """Scripted, and keeps every message list it was sent."""

    def __init__(self, *replies):
        super().__init__(*replies)
        self.seen = []

    def invoke(self, messages):
        self.seen.append(list(messages))
        return super().invoke(messages)


class Explorer:
    def __init__(self, *replies):
        self.replies = list(replies)

    def bind_tools(self, specs):
        return self

    def invoke(self, messages):
        return self.replies.pop(0)


INSPECT = AIMessage(content="", tool_calls=[{"name": "inspect_column",
                                             "args": {"table": "saas.csv", "column": "cntry_cd"}, "id": "c0"}])


def test_with_tools_the_facts_reach_the_analyst_and_the_planner(tmp_path):
    analyst, planner = Recorder(DIRECTIONS), Recorder(CHARTS)
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("churn by country", [_source(tmp_path)], str(tmp_path), analyst, planner,
                                  chartist, top=5, explorer_llm=Explorer(INSPECT, AIMessage(content="DONE"))))
    labels = [e.data["label"] for e in events if e.kind == "status"]
    assert "Checking the data" in labels and any(label.startswith("Checking the data: ") for label in labels)
    assert "Facts checked on the full data:" in analyst.seen[0][-1].content
    assert "Facts checked on the full data:" in planner.seen[0][-1].content
    plan = next(e for e in events if e.kind == "plan").data
    assert plan["facts"] and "cntry_cd" in plan["facts"][0]


def test_memory_reaches_the_analyst_and_not_the_planner(tmp_path):
    analyst, planner = Recorder(DIRECTIONS), Recorder(CHARTS)
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    memory = "Already on this report (do not repeat these; add what is missing):\n1. bar · Churn by country"
    list(build_dashboard("", [_source(tmp_path)], str(tmp_path), analyst, planner, chartist, memory=memory))
    assert memory in analyst.seen[0][-1].content and memory not in planner.seen[0][-1].content


def test_a_plan_that_breaks_on_the_real_data_goes_back_to_the_planner(tmp_path):
    # 60 names x 25 rows: the profile calls `name` a category (60 values, under 5% of
    # 1,500 rows), so the bar passes the rules and only the data check can catch it.
    path = tmp_path / "names.csv"
    pd.DataFrame({"name": [f"n{i}" for i in range(60)] * 25, "v": [i % 7 for i in range(1500)]}).to_csv(path, index=False)
    source = {"type": "file", "name": "names.csv", "path": str(path)}
    directions = json.dumps({"directions": [{"question": "Which names score most?", "why": "asked",
                                             "table": "names.csv", "columns": ["name", "v"]}]})
    bar = {"title": "Top names", "question": "Which names score most?", "chart": "bar", "table": "names.csv",
           "x": "name", "y": "v", "group": "", "agg": "sum", "grain": "", "sort": "desc", "top_n": 0}
    planner = Recorder(json.dumps({"charts": [bar]}), json.dumps({"charts": [{**bar, "top_n": 20}]}))
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("", [source], str(tmp_path), Scripted(directions), planner, chartist,
                                  explorer_llm=Explorer(AIMessage(content="DONE"))))
    plan = next(e for e in events if e.kind == "plan").data
    assert plan["attempts"]["planner"] == 2 and plan["placed"][0].spec["top_n"] == 20
    assert "60 bars" in planner.seen[1][-1].content
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_dashboard_flow.py`
Expected: the 3 new tests fail on the unexpected keyword arguments `explorer_llm` and `memory`.

- [ ] **Step 3: Implement**

In `planning_contract.py`, change `from typing import Any` to `from typing import Any, Callable`. Add after `EXPLORER_USER_TEMPLATE`:

```python
FACTS_HEADER = "Facts checked on the full data:"


def with_context(text: str, facts: str = "", memory: str = "") -> str:
    """A planning user message, with optional sections after the trained part."""
    parts = [text]
    if facts:
        parts.append(f"{FACTS_HEADER}\n{facts}")
    if memory:
        parts.append(memory)
    return "\n\n".join(parts)
```

Change `check_specs` to:

```python
def check_specs(
    payload: Any,
    tables: dict[str, dict[str, str]],
    validate: Callable[[dict], list[str]] | None = None,
) -> tuple[list[dict], list[str]]:
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
        data_problems = validate(spec) if validate is not None else []
        if data_problems:
            errors.extend(f"chart {n}: {problem}" for problem in data_problems)
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
```

In `planning.py`, import `with_context` from `planning_contract` and replace the four public functions:

```python
def propose_directions_steps(
    llm: Any, request: str, profiles: list[TableProfile], facts: str = "", memory: str = ""
) -> Generator[Retry, None, PlanStep]:
    user = with_context(
        ANALYST_USER_TEMPLATE.format(request=(request or "").strip() or NO_REQUEST, profiles=render_profiles(profiles)),
        facts,
        memory,
    )
    return run_checked(llm, ANALYST_SYSTEM_PROMPT, user, check_directions, columns_by_table(profiles), "analyst")


def propose_directions(
    llm: Any, request: str, profiles: list[TableProfile], facts: str = "", memory: str = ""
) -> PlanStep:
    return finish(propose_directions_steps(llm, request, profiles, facts, memory))


def plan_charts_steps(
    llm: Any,
    directions: list[dict],
    profiles: list[TableProfile],
    facts: str = "",
    validate: Callable[[dict], list[str]] | None = None,
) -> Generator[Retry, None, PlanStep]:
    user = with_context(
        PLANNER_USER_TEMPLATE.format(profiles=render_profiles(profiles), directions=render_directions(directions)),
        facts,
    )
    check = check_specs if validate is None else (lambda payload, tables: check_specs(payload, tables, validate))
    return run_checked(llm, PLANNER_SYSTEM_PROMPT, user, check, columns_by_table(profiles), "planner")


def plan_charts(
    llm: Any,
    directions: list[dict],
    profiles: list[TableProfile],
    facts: str = "",
    validate: Callable[[dict], list[str]] | None = None,
) -> PlanStep:
    return finish(plan_charts_steps(llm, directions, profiles, facts, validate))
```

In `dashboard_flow.py`, import `ToolBox` from `data_tools` and `Findings`, `Probe`, `discover` from `discovery`, then add above `build_dashboard`:

```python
def _probe_words(probe: Probe) -> str:
    args = probe.args
    if probe.name == "find_columns":
        return f"looking for '{args.get('query', '')}'"
    if probe.name == "relationship":
        return f"{args.get('a', '')} and {args.get('b', '')}"
    return str(args.get("column") or args.get("x") or probe.name)


def _with_probe_status(steps: Generator[Probe, None, Findings]) -> Generator[Event, None, Findings]:
    """Run the tool step, turning each tool call into a status line; returns its Findings."""
    while True:
        try:
            probe = next(steps)
        except StopIteration as done:
            return done.value
        yield Event("status", {"label": f"Checking the data: {_probe_words(probe)}"})
```

Change `build_dashboard`'s signature and its planning part to:

```python
def build_dashboard(
    brief: str,
    sources: list[dict],
    data_dir: str,
    analyst_llm: Any,
    planner_llm: Any,
    chartist: Any,
    top: int = 0,
    explorer_llm: Any = None,
    memory: str = "",
) -> Iterator[Event]:
    yield Event("status", {"label": "Reading your data"})
    tables = profile_sources(sources, data_dir, brief)
    if not tables:
        yield Event("error", {"detail": "None of this report's sources could be read."})
        return
    profiles = [entry.profile for entry in tables]

    facts, validate = "", None
    if explorer_llm is not None:
        toolbox = ToolBox({entry.label: entry.source for entry in tables}, data_dir)
        yield Event("status", {"label": "Checking the data"})
        findings = yield from _with_probe_status(discover(explorer_llm, brief, profiles, toolbox))
        facts, validate = findings.note, toolbox.validate_spec

    choosing = "Choosing what to show"
    yield Event("status", {"label": choosing})
    directions = yield from _with_retry_status(
        propose_directions_steps(analyst_llm, brief, profiles, facts, memory), choosing
    )
    if not directions.items:
        yield Event("error", {"detail": "Could not work out what to show from this data: "
                                        + "; ".join(directions.errors[:3])})
        return

    planning = "Planning the charts"
    yield Event("status", {"label": planning})
    charts = yield from _with_retry_status(
        plan_charts_steps(planner_llm, directions.items, profiles, facts, validate), planning
    )
```

Add `"facts": facts.splitlines() if facts else [],` to the `Event("plan", {...})` payload. The rest of the function is unchanged.

- [ ] **Step 4: Run the tests and the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_dashboard_flow.py tests/test_planning_steps.py && .venv/bin/python -m pytest -q tests`
Expected: all of `test_dashboard_flow.py` passes (the existing tests are unchanged, since no explorer means no new events), and only the 3 known failures in the suite.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/planning_contract.py backend/app/services/agents/planning.py backend/app/services/agents/dashboard_flow.py backend/tests/test_dashboard_flow.py
git commit -m "feat(dashboard): facts and memory in the planning calls, plans checked on data

With an explorer model the build runs the tool step first ('Checking the
data: track_name'), appends the facts to the analyst and planner messages,
and sends any final chart plan that cannot be drawn readably on the real
data back to the planner. Memory goes to the analyst only, to keep the
planner near the 2,048 tokens it was trained on. System prompts unchanged.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Report memory, rebuilt from the database each run

**Files:**
- Create: `backend/app/models/report_request.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/services/agents/report_memory.py`
- Modify: `backend/app/api/v1/endpoints/blocks.py` (`generate_block`, `generate_whole_dashboard`, `_ai_dashboard`)
- Test: `backend/tests/test_report_memory.py`

**Interfaces:**
- Consumes: `build_dashboard(..., explorer_llm=None, memory="")` (Task 5); `get_llm("explorer")` and `Settings.PLANNER_TOOLS` (Task 4).
- Produces:
  - The `ReportRequest` model, table `report_requests`, with `id`, `dashboard_id`, `user_id`, `kind` ("dashboard" or "chart"), `text` and `created_at`.
  - `report_memory.describe_report(blocks: list[dict], requests: list[dict]) -> str`. Block dicts carry `kind`, `title`, `chart_type` and `prompt`; request dicts carry `kind` and `text`.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_report_memory.py`)

```python
"""What is already on a report, in a few lines: descriptions, never data."""
from app.services.agents.report_memory import MAX_CHARTS, MEMORY_CHARS, describe_report


def test_charts_and_requests_are_described_and_notes_left_out():
    blocks = [
        {"kind": "chart", "title": "Top tracks", "chart_type": "bar", "prompt": "Which tracks are listened to most?"},
        {"kind": "metric", "title": "Total tracks", "chart_type": "kpi", "prompt": "How many tracks?"},
        {"kind": "text", "title": "Note", "chart_type": None, "prompt": None},
    ]
    requests = [{"kind": "dashboard", "text": "most listened songs"}, {"kind": "chart", "text": "now by genre"}]
    text = describe_report(blocks, requests)
    assert "1. bar · Top tracks — Which tracks are listened to most?" in text
    assert "2. kpi · Total tracks" in text and "Note" not in text
    assert '"most listened songs" (dashboard)' in text and '"now by genre" (chart)' in text


def test_an_empty_report_has_no_memory():
    assert describe_report([], []) == ""


def test_memory_keeps_the_latest_charts_and_stays_short():
    blocks = [{"kind": "chart", "title": f"Chart {i} " + "x" * 80, "chart_type": "bar", "prompt": ""} for i in range(30)]
    text = describe_report(blocks, [])
    assert len(text) <= MEMORY_CHARS and "Chart 29" in text and "Chart 17 " not in text
    assert len([line for line in text.splitlines() if line[:1].isdigit()]) <= MAX_CHARTS
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_report_memory.py`
Expected: an ImportError on `app.services.agents.report_memory`.

- [ ] **Step 3: Implement**

`backend/app/models/report_request.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReportRequest(Base):
    """What the user asked of a report, in their own words: a dashboard brief or a
    chart question. Read back as the report's memory on the next request."""

    __tablename__ = "report_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dashboard_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # "dashboard" | "chart"
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

In `backend/app/models/__init__.py`, add `from app.models.report_request import ReportRequest` and add `"ReportRequest"` to `__all__`.

`backend/app/services/agents/report_memory.py`:

```python
"""What is already on a report, in a few lines, rebuilt from the database each run.

Runs are stateless: every build is a fresh conversation. This gives the analyst
the report's charts (kind, title, the question each answers) and what the user
asked before, so a second build extends the report instead of repeating it.
Descriptions only: no figure data ever goes into a prompt.
"""
from __future__ import annotations

MAX_CHARTS = 12
MAX_REQUESTS = 5
MEMORY_CHARS = 1000  # about 250 tokens, analyst only


def describe_report(blocks: list[dict], requests: list[dict]) -> str:
    charts = [b for b in blocks if b.get("kind") in ("chart", "metric")][-MAX_CHARTS:]
    asked = [r for r in requests if str(r.get("text") or "").strip()][-MAX_REQUESTS:]

    def render(entries: list[dict]) -> str:
        lines: list[str] = []
        if entries:
            lines.append("Already on this report (do not repeat these; add what is missing):")
            for n, block in enumerate(entries, 1):
                kind = block.get("chart_type") or ("kpi" if block.get("kind") == "metric" else "chart")
                title = str(block.get("title") or "Untitled")
                question = str(block.get("prompt") or "").strip()
                line = f"{n}. {kind} · {title}"
                if question and question != title:
                    line += f" — {question[:120]}"
                lines.append(line)
        if asked:
            lines.append("Asked before: " + "; ".join(
                f"\"{str(r['text']).strip()[:120]}\" ({r.get('kind', 'chart')})" for r in asked))
        return "\n".join(lines)

    text = render(charts)
    while len(text) > MEMORY_CHARS and charts:
        charts = charts[1:]  # the oldest chart goes first
        text = render(charts)
    return text[:MEMORY_CHARS]
```

In `blocks.py`, add these imports: `from app.models.report_request import ReportRequest`, `from app.services.agents.report_memory import describe_report` and `from app.services.llm import get_llm` (if `get_llm` is not imported already). Then add after `_next_row`:

```python
def _record_request(db: Session, report: Dashboard, user: User, kind: str, text: str) -> None:
    """Keep what the user asked, in their words, for the report's memory."""
    db.add(ReportRequest(dashboard_id=report.id, user_id=user.id, kind=kind, text=(text or "").strip()[:2000]))
    db.commit()


def _report_memory(db: Session, report_id: str) -> str:
    blocks = db.query(ReportBlock).filter(ReportBlock.dashboard_id == report_id).order_by(ReportBlock.created_at).all()
    requests = (
        db.query(ReportRequest).filter(ReportRequest.dashboard_id == report_id).order_by(ReportRequest.created_at).all()
    )
    return describe_report(
        [{"kind": b.kind.value if hasattr(b.kind, "value") else str(b.kind), "title": b.title,
          "chart_type": b.chart_type, "prompt": b.prompt} for b in blocks],
        [{"kind": r.kind, "text": r.text} for r in requests],
    )
```

In `generate_block`, right after `report = _owned_report(...)`:

```python
    _record_request(db, report, current_user, "chart", payload.prompt)
```

In `generate_whole_dashboard`, replace the last line (`return _ai_dashboard(report, sources, brief, current_user, db)`) with:

```python
    memory = _report_memory(db, report.id)  # before this request is recorded: it is the brief, not history
    _record_request(db, report, current_user, "dashboard", brief)
    return _ai_dashboard(report, sources, brief, current_user, db, memory)
```

Change `_ai_dashboard`'s signature to `def _ai_dashboard(report, sources, brief, current_user, db, memory: str = ""):`, and its `build_dashboard(...)` call to:

```python
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
    )
```

In `_ai_dashboard`'s `plan` branch, replace the existing log call with:

```python
                logger.info(
                    "[dashboard] planned %d charts from %s (tries: %s; dropped: %s; facts: %s)",
                    len(placed), names, event.data["attempts"], event.data["dropped"], event.data.get("facts"),
                )
```

- [ ] **Step 4: Run the tests, the suite, and the live api**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_report_memory.py && .venv/bin/python -m pytest -q tests`
Expected: 3 passed, and only the 3 known failures in the suite.

Run: `cd .. && docker compose logs api --since 2m --no-log-prefix | grep -E "startup complete|Error|Traceback" | tail -3`
Expected: `Application startup complete.` with no traceback. The reload ran `create_all`, which creates `report_requests`.

Run: `docker exec promptdash-postgres psql -U promptdash -d promptdash -c '\d report_requests'`
Expected: the table, with columns id, dashboard_id, user_id, kind, text and created_at.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/report_request.py backend/app/models/__init__.py backend/app/services/agents/report_memory.py backend/app/api/v1/endpoints/blocks.py backend/tests/test_report_memory.py
git commit -m "feat(memory): tell the analyst what is already on the report

Each run rebuilds a short description from the database: the report's
charts (kind, title, question) and the user's last requests, kept in a
new report_requests table. At most 12 charts and 5 requests, under 1,000
characters, analyst only; no figure data. A second build now knows what
the first made. The explorer is passed when PLANNER_TOOLS is on.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: A live check of one tool-assisted plan

**Files:**
- Create: `backend/scripts/smoke_planner_tools.py`

**Interfaces:**
- Consumes: `build_dashboard(..., explorer_llm, memory)` (Task 5); `blocks._user_sources`, `blocks._report_memory` and `blocks._agents` (via the workflow import in `blocks.py`); `get_llm`.
- Produces: a script, run in the api container, that prints status lines, tool calls, facts and the plan, and saves nothing.

- [ ] **Step 1: Write the script**

```python
"""One dashboard plan with the tool step, against the live model. Saves nothing.

    docker exec -i promptdash-api python /app/scripts/smoke_planner_tools.py <report id> "<brief>"
"""
import sys
import time

sys.path.insert(0, "/app")
from app.api.v1.endpoints.blocks import _agents, _report_memory, _user_sources  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.dashboard import Dashboard  # noqa: E402
from app.services.agents.dashboard_flow import build_dashboard  # noqa: E402
from app.services.llm import get_llm  # noqa: E402

report_id, brief = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")
db = SessionLocal()
report = db.get(Dashboard, report_id)
flow = build_dashboard(brief, _user_sources(db, report), get_settings().UPLOAD_DIR, get_llm("analyst"),
                       get_llm("spec_planner"), _agents()[2], explorer_llm=get_llm("explorer"),
                       memory=_report_memory(db, report_id))
started = time.perf_counter()
for event in flow:
    t = time.perf_counter() - started
    if event.kind == "status":
        print(f"[{t:6.1f}s] {event.data['label']}", flush=True)
    elif event.kind == "plan":
        print(f"[{t:6.1f}s] facts: {event.data['facts']}", flush=True)
        print(f"          tries {event.data['attempts']}, dropped {event.data['dropped']}", flush=True)
        for item in event.data["placed"]:
            s = item.spec
            print(f"          {s['chart']:9s} {s['title']!r} x={s['x']} y={s['y']} agg={s['agg']} top_n={s['top_n']}", flush=True)
        break  # planning is what this checks; drawing is make smoke's job
    elif event.kind == "error":
        print(f"[{t:6.1f}s] ERROR {event.data['detail']}", flush=True)
        break
```

- [ ] **Step 2: Run it on the Spotify report**

Run: `docker exec -i promptdash-api python /app/scripts/smoke_planner_tools.py 08793fa3-c793-4669-9028-66aca3d02b55 "can you make for my spotify analysis for the most listened musics"`
Expected:
- at least one `Checking the data: ...` line
- a non-empty `facts:` list (for example a repeat count for `track_name`)
- a plan of 4-7 charts
- no traceback

If the model makes no tool call, record that. It is a finding for Task 8, not a bug.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/smoke_planner_tools.py
git commit -m "chore(scripts): live check of one tool-assisted dashboard plan

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Measure tools on against tools off on the frozen planning set, then decide

**Files:**
- Create: `chartist-finetune/measure_planning_tools.py`
- Modify: `backend/app/core/config.py` (only if the decision rule says on)
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: `discover` (Task 4); `propose_directions`, `plan_charts` and `finish` (Task 5); `ToolBox` (Task 3); `architect.spread_sample`; `profiler.profile_table`; `get_llm`.
- Produces: `chartist-finetune/data/v2/planning_tools_tools-on.json` and `planning_tools_tools-off.json`, each with a `.rows.jsonl`.

- [ ] **Step 1: Write the harness**

```python
#!/usr/bin/env python3
"""Does the planner plan better when it may check the data first?

Runs the backend's own planning code (tool step, analyst, planner, checks) on
the frozen planning test set, over HTTP against the running model server, with
and without the tool step on the same rows. Nothing is drawn; measure_planning.py
covers drawing. Rows are saved as they finish; rerunning resumes.

    cd chartist-finetune
    ../backend/.venv/bin/python measure_planning_tools.py --tools off --limit 40
    ../backend/.venv/bin/python measure_planning_tools.py --tools on --limit 40
"""
from __future__ import annotations

import argparse
import json
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
from app.services.agents.data_tools import ToolBox  # noqa: E402
from app.services.agents.discovery import discover  # noqa: E402
from app.services.agents.planning import finish, plan_charts, propose_directions  # noqa: E402
from app.services.agents.profiler import profile_table  # noqa: E402
from app.services.llm import get_llm  # noqa: E402

SAMPLE_ROWS = 2000


def summarize(rows: list[dict]) -> dict:
    planned = [r for r in rows if r["charts"]]
    return {
        "rows": len(rows),
        "analyst_usable_rate": sum(1 for r in rows if r["directions"]) / len(rows),
        "analyst_retry_rate": sum(1 for r in rows if r["analyst_attempts"] > 1) / len(rows),
        "planner_first_try_rate": sum(1 for r in planned if r["planner_attempts"] == 1) / len(planned) if planned else 0.0,
        "mean_charts": statistics.mean(r["charts"] for r in planned) if planned else 0.0,
        "dropped_per_dashboard": statistics.mean(r["dropped"] for r in planned) if planned else 0.0,
        "tool_calls_per_dashboard": statistics.mean(len(r["tool_calls"]) for r in rows),
        "median_seconds": statistics.median(r["seconds"] for r in rows),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", choices=["on", "off"], required=True)
    ap.add_argument("--testset", default="data/v2/planning_testset.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    label = f"tools-{args.tools}"

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

    for row in rows:
        if row["request_id"] in done:
            continue
        schema = schemas[row["schema_id"]]
        frame = pd.read_csv(ROOT / schema["fixture_csv"])
        table = schema["table_name"]
        profiles = [profile_table(table, spread_sample(frame, SAMPLE_ROWS))]
        started = time.perf_counter()
        facts, validate, calls = "", None, []
        if explorer is not None:
            toolbox = ToolBox({table: {"type": "file", "name": table}}, str(ROOT), loader=lambda s, d: frame)
            findings = finish(discover(explorer, row["request"], profiles, toolbox))
            facts, validate, calls = findings.note, toolbox.validate_spec, [c.name for c in findings.calls]
        directions = propose_directions(analyst, row["request"], profiles, facts)
        charts = plan_charts(planner, directions.items, profiles, facts, validate) if directions.items else None
        record = {
            "request_id": row["request_id"], "request": row["request"], "tools": args.tools,
            "tool_calls": calls, "facts_chars": len(facts),
            "directions": len(directions.items), "analyst_attempts": directions.attempts,
            "charts": len(charts.items) if charts else 0, "planner_attempts": charts.attempts if charts else 0,
            "dropped": sum(1 for e in (charts.errors if charts else []) if e.startswith("chart ")),
            "seconds": round(time.perf_counter() - started, 1),
        }
        with ckpt.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        print(f"{row['request_id']}: tools {calls} -> {record['charts']} charts, "
              f"planner tries {record['planner_attempts']}, {record['seconds']}s", flush=True)

    all_rows = [json.loads(l) for l in ckpt.read_text(encoding="utf-8").splitlines() if l.strip()]
    summary = {"label": label, **summarize(all_rows)}
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Check the frozen set is untouched, then smoke-test the harness on 2 rows**

Run: `cd chartist-finetune && shasum -a 256 data/v2/planning_testset.jsonl && cat data/v2/planning_testset.sha256`
Expected: the two hashes match (`8af1473a...`).

Run: `../backend/.venv/bin/python measure_planning_tools.py --tools on --limit 2 && rm data/v2/planning_tools_tools-on.json data/v2/planning_tools_tools-on.rows.jsonl`
Expected: two row lines and a summary, with no traceback. The model server must be running (`make serve-model MLX_HOST=127.0.0.1`).

- [ ] **Step 3: Run both modes on the same 40 rows**

Run (in the background, about an hour each): `../backend/.venv/bin/python measure_planning_tools.py --tools off --limit 40`, then `../backend/.venv/bin/python measure_planning_tools.py --tools on --limit 40`
Expected: two summary JSON files.

- [ ] **Step 4: Apply the decision rule**

Turn tools on by default (set `PLANNER_TOOLS: str = "on"` in `config.py`) only if all of these hold on the same 40 rows, tools on against tools off:
- `planner_first_try_rate` is not lower;
- `dropped_per_dashboard` is not higher;
- `analyst_usable_rate` is not lower;
- `median_seconds` rises by less than 30.

Otherwise keep `"off"`, and write down which metric failed.

- [ ] **Step 5: Record the result in AGENTS.md**

Add one bullet under "Frontend integration details", after the dashboard-flow bullets. Replace each `<...>` with the measured values from the two summary files and the decision from Step 4; nothing in angle brackets may remain. Use this form:

```markdown
- Planner tools (`agents/data_tools.py`, `agents/discovery.py`, `PLANNER_TOOLS`): an explorer call asks the model to check up to 3 facts (find_columns, inspect_column, relationship, preview; results capped at 1,200 characters, 20 items, with truncation markers), and the analyst and planner get only a facts note of at most 800 characters; final plans are also checked on the real data (more than 50 bars, 12 slices or 1,000 line points goes back to the planner). Measured on the first 40 frozen planning rows (`chartist-finetune/measure_planning_tools.py`): tools off <numbers>, tools on <numbers>; default <on|off> because <reason>. Report memory (`agents/report_memory.py`, table `report_requests`) gives the analyst the report's charts and the last 5 requests.
```

- [ ] **Step 6: Commit**

```bash
git add chartist-finetune/measure_planning_tools.py chartist-finetune/data/v2/planning_tools_tools-on.json chartist-finetune/data/v2/planning_tools_tools-on.rows.jsonl chartist-finetune/data/v2/planning_tools_tools-off.json chartist-finetune/data/v2/planning_tools_tools-off.rows.jsonl backend/app/core/config.py AGENTS.md
git commit -m "data(planning): tools on vs off on 40 frozen planning rows

analyst usable: off X% -> on Y%; planner first try: off X% -> on Y%;
dropped per dashboard: off X -> on Y; median seconds: off X -> on Y.
Default: on|off, because <the failing or passing metrics>.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
# Before running: put the measured numbers in place of every X and Y, and the
# decision and its reason in the last line.
```
