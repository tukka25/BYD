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
