"""Facts about the real data, for the planner to check before it plans.

Four tools, each a pure function over pandas DataFrames, each with a hard cap
on what it returns. A model that asks about a 400-column table gets 10 matches
and a count, never the table. Tools answer questions about data; they never
draw or choose a chart, and every chart stays the model's own code.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from app.services.agents.planning_contract import check_spec
from app.services.agents.profiler import profile_column

logger = logging.getLogger(__name__)

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


def _fmt(value: Any) -> str:
    """A number inside a one-line fact: three significant figures, thousands separated."""
    number = _num(value)
    return f"{number:,.0f}" if abs(number) >= 1000 else f"{number:g}"


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


def find_columns(tables: dict[str, pd.DataFrame], query: str, limit: int = 10) -> dict[str, Any]:
    """Columns whose name or common values match the query, across every table.

    Values are matched on the same 2,000-row sample the planner's profile reads, so a call stays fast on large tables.
    """
    from itertools import islice

    from app.services.agents.architect import spread_sample

    wanted = _tokens(query)
    if not wanted:
        return {"fact": "Give a word to search for, such as 'country' or 'revenue'.", "matches": [], "total": 0}
    kinds: dict[tuple[str, str], str] = {}

    def kind_of(table: str, column: Any) -> str:
        key = (table, str(column))
        if key not in kinds:
            kinds[key] = _kind(tables[table][column])
        return kinds[key]

    found = []
    for table, frame in tables.items():
        sample = spread_sample(frame, KIND_SAMPLE)
        for column in frame.columns:
            names = _tokens(column)
            score = sum(1 for w in wanted if any(n.startswith(w) or w.startswith(n) for n in names))
            top = set(sample[column].dropna().astype(str).str.lower().value_counts().head(MAX_ITEMS).index)
            score += sum(1 for w in wanted if w in top)
            if score:
                found.append((score, table, str(column)))
    found.sort(key=lambda item: (-item[0], item[1], item[2]))
    shown = []
    for _, table, column in found[: min(limit, MAX_ITEMS)]:
        series = tables[table][column]
        shown.append({"table": table, "column": column, "kind": kind_of(table, column),
                      "distinct": int(series.nunique()),
                      "examples": [_short(v) for v in series.dropna().unique()[:3]]})
    if shown:
        names = ", ".join(f"{m['table']}.{m['column']}" for m in shown[:5])
        more = f" ({len(found)} in all)" if len(found) > len(shown) else ""
        fact = f"Columns matching '{query}': {names}{more}"
    else:
        measures = list(islice(
            (f"{t}.{c}" for t, f in tables.items() for c in f.columns if kind_of(t, c) == "number"), 6))
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
    if out["distinct"] and len(values) > out["distinct"]:
        per_value = len(values) / out["distinct"]
        out["rows_per_value"] = round(per_value, 1)
        if per_value >= 1.5:
            facts.append(f"each value appears about {per_value:.0f} times")
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


MAX_CALLS = 3          # tool calls per dashboard build
LINE_POINTS = 1000     # more points than this on one line chart is unreadable
CAPS = {"bar": 50, "waterfall": 50, "pie": 12, "funnel": 12, "treemap": 200, "sunburst": 200, "heatmap": 2500}
UNITS = {"bar": "bars", "waterfall": "bars", "pie": "slices", "funnel": "stages", "treemap": "pieces",
         "sunburst": "pieces", "heatmap": "cells"}
GRAIN_FREQ = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}
AGGS = ("sum", "mean", "median", "count", "min", "max", "none")
EXPLORER_TOOL_NAMES = ("find_columns", "inspect_column", "relationship", "preview")
GRAIN_COLUMNS = 8      # the label columns with the fewest values tried as parts of a key
GRAIN_SIZE = 3         # the most columns a key may have
GRAIN_CONFIRMS = 3     # candidate keys checked on the full table, one pass each
MAX_PREVIEW_PLANS = 7  # draft plans one preview_chart call may hold
PLANNER_TOOL_NAMES = ("preview_chart", "row_grain", "inspect_column", "find_columns", "relationship")


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
        out["per_series"] = int(data.groupby(group).size().max()) if group and len(data) else int(len(data))
        out["series"] = int(data[group].nunique()) if group else 1
        measure = y or x
        if measure and len(data) and pd.api.types.is_numeric_dtype(data[measure]):
            out["low"], out["high"] = _num(data[measure].min()), _num(data[measure].max())
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
    out["per_series"] = int(values.groupby(level=1).size().max()) if group and len(values) else int(len(values))
    out["series"] = int(values.index.get_level_values(1).nunique()) if group and len(values) else 1
    if len(values) and pd.api.types.is_numeric_dtype(values):
        out["low"], out["high"] = _num(values.min()), _num(values.max())
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
    agg = str(spec.get("agg") or "none")
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
    agg = str(spec.get("agg") or "none")
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


def tool_specs(tables: list[str], names: tuple[str, ...] = EXPLORER_TOOL_NAMES) -> list[dict[str, Any]]:
    """The named tools, in that order, in the OpenAI format mlx_lm server forwards to the chat template."""
    table = {"type": "string", "enum": tables}
    def spec(name: str, description: str, properties: dict, required: list[str]) -> dict:
        return {"type": "function", "function": {"name": name, "description": description, "parameters": {
            "type": "object", "properties": properties, "required": required}}}
    every = [
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
    by_name = {tool["function"]["name"]: tool for tool in every}
    return [by_name[name] for name in names]


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
                 loader: Callable[[dict, str], pd.DataFrame] | None = None,
                 tools: tuple[str, ...] = EXPLORER_TOOL_NAMES,
                 kinds: dict[str, dict[str, str]] | None = None):
        self.sources = sources
        self.data_dir = data_dir
        self.max_calls = max_calls
        self.tools = tools
        self.kinds = kinds  # the profile's column kinds by table, so preview_chart runs the plan rules too
        self._loader = loader
        self._frames: dict[str, pd.DataFrame] = {}
        self.calls: list[ToolCall] = []

    @property
    def specs(self) -> list[dict[str, Any]]:
        return tool_specs(list(self.sources), self.tools)

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

    def call(self, name: str, args: dict | None, compact: bool = False) -> str:
        """Run one tool and record it. The reply is the result as compact JSON or,
        with `compact`, its fact line(s) alone: what the planner reads inside its
        own prompt. An error is always the JSON."""
        if self.exhausted:
            return bounded({"error": f"the tool budget ({self.max_calls} calls) is used up: answer now"})
        args = dict(args or {})
        try:
            result = self._run(name, args)
        except (KeyError, ValueError, TypeError) as exc:
            # args[0], not str(exc): str() of a KeyError wraps the message in quotes.
            result = {"error": str(exc.args[0]) if exc.args else str(exc)}
        except Exception as exc:  # noqa: BLE001 - a failed tool is an error for the model, never a failed build
            logger.warning("[tools] %s(%s) failed: %s", name, args, exc)
            result = {"error": f"{name} could not run: {exc}"}
        text = bounded(result)
        call = ToolCall(name, args, text, str(result.get("fact", "")))
        self.calls.append(call)
        return _capped(call.fact) if compact and call.fact else text

    def _run(self, name: str, args: dict) -> dict[str, Any]:
        if name not in self.tools:
            raise ValueError(f"no tool '{name}'; tools are: {', '.join(self.tools)}")
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
        if name == "row_grain":
            return row_grain(self.frame(table), table)
        if name == "preview_chart":
            return self._preview_chart(args.get("plans"))
        raise ValueError(f"no tool '{name}'; tools are: {', '.join(self.tools)}")

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

    def facts(self) -> list[str]:
        return [call.fact for call in self.calls if call.fact]

    def validate_spec(self, spec: dict) -> list[str]:
        """Objective problems a planned chart would have on the real data. Not a
        judgement of taste: only what cannot be drawn readably (chart_shape)."""
        try:
            return chart_shape(self.frame(spec["table"]), spec)[1]
        except Exception as exc:  # noqa: BLE001 - a check that cannot run is not a problem with the plan
            logger.warning("[tools] could not check chart plan %s: %s", spec.get("title"), exc)
            return []
