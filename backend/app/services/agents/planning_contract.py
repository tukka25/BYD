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
# A text column cut to its top N bars reads like a category, so the same cap as
# the profiler's MAX_CATEGORIES.
MAX_TOP_N = 30
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
    if agg == "count" and y and y == x:
        y = ""  # "count of the x column" is a row count per x value
    if x and y and x == y:
        problems.append("x and y must be different columns")
    if group and group in (x, y):
        problems.append("group must be a different column from x and y")
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
        if kx == "text":
            # A name column ("top 10 tracks") works once top_n keeps it short.
            need(0 < top_n <= MAX_TOP_N, f"a bar chart over the text column '{x}' needs top_n between 1 and {MAX_TOP_N}")
        else:
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
