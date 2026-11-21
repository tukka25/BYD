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
