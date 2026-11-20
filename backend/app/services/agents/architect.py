"""Plans a whole dashboard from one data source.

Why the structure is deterministic and only the language is the model's:

A small model asked for a six-block JSON plan in one call has to hold six
simultaneous obligations AND name columns exactly — and it will cheerfully
reference a column that does not exist, which produces six questions that
cannot be answered. Everything downstream then fails in a way the user reads
as "the product is broken".

So the shape of the dashboard is derived from the data itself: the columns are
profiled (what is a date, what is a measure, what is a category worth grouping
by), and the sections are composed from that profile in the order a reader
wants them — the headline first, then the trend, then the breakdown, then the
detail. That order is the "story", and it is the one part of this that is
genuinely a best practice rather than a preference.

The model still writes every title, through the narrator, and the questions it
is handed are guaranteed answerable because they are built from real column
names.
"""
from __future__ import annotations

import logging
import re
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

logger = logging.getLogger(__name__)

# A column with this many distinct values is a label, not an identifier.
MAX_GROUP_CARDINALITY = 25
MIN_GROUP_CARDINALITY = 2
SAMPLE_ROWS = 2000

_ID_NAME = re.compile(
    r"(^|_)(id|uuid|guid|key|hash|index|code)($|_)|_id$|_num$|_code$|^id$", re.IGNORECASE
)
_YEAR_NAME = re.compile(r"(^|_)year($|_)|^yr$", re.IGNORECASE)
_TIME_NAME = re.compile(
    r"date|time|month|week|day|year|quarter|period|_at$|^created|^updated", re.IGNORECASE
)


@dataclass
class Profile:
    """What the data actually contains, measured rather than guessed."""

    name: str
    rows: int
    columns: List[str] = field(default_factory=list)
    time_columns: List[str] = field(default_factory=list)
    measures: List[str] = field(default_factory=list)
    groups: List[str] = field(default_factory=list)
    period: Optional[str] = None
    span_days: Optional[int] = None

    @property
    def can_plan(self) -> bool:
        return bool(self.measures or self.groups)


@dataclass
class Section:
    """One planned block. `prompt` is what the chartist will be asked."""

    kind: str  # "chart" | "text"
    prompt: str = ""
    text_body: str = ""
    title: str = ""
    w: int = 6
    h: int = 9
    x: int = 0
    y: int = 0


def _to_datetime(series: pd.Series) -> pd.Series:
    """Parse dates without the per-element format warning in the hot path."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return pd.to_datetime(series, errors="coerce")


def _is_texty(series: pd.Series) -> bool:
    """Text, whichever dtype this pandas uses for it.

    Not `dtype == object`: current pandas gives string columns a `str` dtype,
    and that one comparison silently classified every label column as
    unusable — no groupings, no dates, and a dashboard of two blocks.
    """
    return pd.api.types.is_string_dtype(series) and not pd.api.types.is_numeric_dtype(series)


def _is_identifier(name: str, series: pd.Series) -> bool:
    """A key, not a measure.

    Uniqueness alone does not say so, in either dtype: a float measure is
    naturally almost all-unique, and so is population. Both got thrown away by
    a uniqueness test, which is how a dashboard loses the column it was about.
    The name is the reliable signal; the only shape worth catching on top of it
    is a row counter that climbs by one.
    """
    if _ID_NAME.search(name):
        return True
    if not pd.api.types.is_integer_dtype(series):
        return False
    values = series.dropna()
    if len(values) < 20:
        return False
    steps = values.diff().dropna()
    return bool(len(steps)) and float((steps == 1).mean()) > 0.98


def profile_frame(name: str, frame: pd.DataFrame) -> Profile:
    """Classify a sample of the data into dates, measures and groupings."""
    profile = Profile(name=name, rows=int(len(frame)), columns=[str(c) for c in frame.columns])

    for column in frame.columns:
        label = str(column)
        series = frame[column]

        if pd.api.types.is_datetime64_any_dtype(series):
            profile.time_columns.append(label)
            continue
        if _is_texty(series) and _TIME_NAME.search(label):
            parsed = _to_datetime(series)
            if parsed.notna().mean() > 0.8:
                profile.time_columns.append(label)
                continue

        # A year is a time axis even when it is stored as an integer. Without
        # this, a dataset keyed by year has no trend chart and `year` turns up
        # as a measure to be summed, which is nonsense.
        if pd.api.types.is_numeric_dtype(series) and _YEAR_NAME.search(label):
            values = series.dropna()
            if not values.empty and values.between(1800, 2200).mean() > 0.95:
                profile.time_columns.append(label)
                continue

        if pd.api.types.is_numeric_dtype(series):
            if not _is_identifier(label, series):
                profile.measures.append(label)
            continue

        if _is_texty(series) or isinstance(series.dtype, pd.CategoricalDtype):
            distinct = series.nunique(dropna=True)
            if MIN_GROUP_CARDINALITY <= distinct <= MAX_GROUP_CARDINALITY and not _ID_NAME.search(
                label
            ):
                profile.groups.append(label)

    # The most varied measure first: it is the one a reader cares about.
    profile.measures.sort(key=lambda c: -float(frame[c].std(skipna=True) or 0))
    # The smallest grouping first: fewer bars read better than more.
    profile.groups.sort(key=lambda c: frame[c].nunique(dropna=True))

    if profile.time_columns:
        profile.period = _period_of(frame, profile.time_columns[0])
        profile.span_days = _span_days(frame, profile.time_columns[0])
    return profile


def _span_days(frame: pd.DataFrame, column: str) -> Optional[int]:
    try:
        values = frame[column]
        if pd.api.types.is_numeric_dtype(values) and _YEAR_NAME.search(column):
            years = values.dropna().astype(int)
            return int((years.max() - years.min()) * 365) if not years.empty else None
        parsed = _to_datetime(values).dropna()
        return int((parsed.max() - parsed.min()).days) if not parsed.empty else None
    except Exception:  # noqa: BLE001
        return None


# A measure you average rather than add. Summing a score, a rate or a
# percentage produces a number with no meaning -- 1,394,650 "total popularity"
# is not a fact about anything.
_RATE_LIKE = re.compile(
    r"pct|percent|rate|ratio|score|rating|popularity|index|avg|average|mean|"
    r"danceability|energy|valence|tempo|loudness|speechiness|acousticness|"
    r"liveness|instrumentalness|age|temperature|margin|share",
    re.IGNORECASE,
)


def _aggregation(measure: str) -> str:
    return "Average" if _RATE_LIKE.search(measure) else "Total"


def _grain(span_days: Optional[int]) -> Optional[str]:
    """How finely a trend should be grouped, from how long the data runs.

    Without this the chartist is asked for a value "over" a date and plots one
    point per row -- 32,833 of them on a line, which is a shape, not a trend.
    """
    if span_days is None:
        return None
    if span_days > 5 * 365:
        return "year"
    if span_days > 180:
        return "month"
    return "day"


def _period_of(frame: pd.DataFrame, column: str) -> Optional[str]:
    """A human span for the intro text — real dates, not an invented range."""
    try:
        column_values = frame[column]
        if pd.api.types.is_numeric_dtype(column_values) and _YEAR_NAME.search(column):
            years = column_values.dropna().astype(int)
            if years.empty:
                return None
            return f"{years.min()} to {years.max()}" if years.min() != years.max() else str(years.min())
        values = _to_datetime(column_values).dropna()
        if values.empty:
            return None
        first, last = values.min(), values.max()
        if first.year == last.year and first.month == last.month:
            return first.strftime("%B %Y")
        return f"{first.strftime('%b %Y')} to {last.strftime('%b %Y')}"
    except Exception:  # noqa: BLE001 - the intro is cosmetic
        return None


def _headline(brief: str) -> str:
    """The brief, as the opening block's title — it is what was asked for."""
    cleaned = " ".join((brief or "").split())[:70].strip().rstrip(".")
    if not cleaned:
        return "About this data"
    return cleaned[:1].upper() + cleaned[1:]


def _intro(profile: Profile, brief: str = "") -> str:
    """An opening paragraph of facts, not of adjectives.

    Everything in it was measured from the sample, so none of it can be wrong
    in the way a generated summary can be.
    """
    bits = [f"<strong>{profile.name}</strong>"]
    counted = f"{profile.rows:,} rows" if profile.rows else ""
    if profile.rows >= SAMPLE_ROWS:
        counted = f"{SAMPLE_ROWS:,}+ rows"
    if counted:
        bits.append(counted)
    bits.append(f"{len(profile.columns)} fields")
    if profile.period:
        bits.append(profile.period)

    headline = " · ".join(bits)
    asked = (
        f"<p>Asked for: {_escape(brief.strip())}</p>" if brief and brief.strip() else ""
    )
    follows = []
    if profile.measures:
        follows.append(f"measures {_join(profile.measures[:3])}")
    if profile.groups:
        follows.append(f"grouped by {_join(profile.groups[:3])}")
    tail = (
        f"<p>This dashboard {', '.join(follows)}.</p>"
        if follows
        else "<p>Generated from the fields found in this source.</p>"
    )
    return f"<p>{headline}</p>{asked}{tail}"


def _escape(text: str) -> str:
    """The brief is the user's own text and is rendered as markup downstream."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _join(items: Sequence[str]) -> str:
    items = list(items)
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


_WORDS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")

# Said in nearly every brief, so they separate nothing.
_BRIEF_STOPWORDS = frozenset(
    """a an and are as at by for from how in into is it of on or over per show me
    the their this to us with what which dashboard report chart graph about make
    build create focus""".split()
)


def _tokens(text: str) -> set[str]:
    """camelCase-aware, so `mrrUsd` matches a brief that says "MRR"."""
    out: set[str] = set()
    for part in _WORDS.findall(text or ""):
        word = part.lower()
        if len(word) < 2:
            continue
        out.add(word)
        # Enough stemming that a brief saying "churn" finds `churnedSeats`
        # and "sales" finds `salePrice`. Not a stemmer, deliberately: the
        # cost of a wrong match here is only a differently ordered dashboard.
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            out.add(word[:-1])
        for suffix in ("ed", "ing"):
            if len(word) > len(suffix) + 2 and word.endswith(suffix):
                out.add(word[: -len(suffix)])
    return out


def _steer(columns: List[str], brief_tokens: set[str]) -> List[str]:
    """Move the columns the brief actually names to the front.

    Deterministic overlap rather than asking the model which columns matter:
    the answer has to be a real column name, and this cannot return one that
    is not. The brief changes what leads; it cannot invent a field.
    """
    if not brief_tokens:
        return columns
    scored = sorted(
        columns,
        key=lambda column: -len(brief_tokens & _tokens(column)),
    )
    return scored


def plan(profile: Profile, max_charts: int = 5, brief: str = "") -> List[Section]:
    """Compose the dashboard in reading order.

    Headline, then change over time, then the breakdown that explains it, then
    the detail. Sections whose data is not present are simply not planned —
    a dashboard with four real blocks beats six with two that cannot be drawn.

    A brief does not rewrite that order; it decides which columns lead it.
    """
    if not profile.can_plan:
        return []

    brief_tokens = {t for t in _tokens(brief) if t not in _BRIEF_STOPWORDS}
    measures = _steer(profile.measures, brief_tokens)
    groups = _steer(profile.groups, brief_tokens)

    measure = measures[0] if measures else None
    second = measures[1] if len(measures) > 1 else None
    group = groups[0] if groups else None
    other = groups[1] if len(groups) > 1 else None
    time = profile.time_columns[0] if profile.time_columns else None

    charts: List[Section] = []
    # The planner profiled the data, so it knows what the chartist cannot see
    # from three sample rows: how many rows share an x value, and whether this
    # measure is added or averaged. Both go into the question.
    agg = _aggregation(measure) if measure else "Total"
    second_agg = "Average" if agg == "Total" else "Highest"
    grain = _grain(profile.span_days)

    if measure:
        charts.append(
            Section(kind="chart", prompt=f"{agg} {measure} as a single big KPI number", w=4, h=4)
        )
    if measure:
        charts.append(
            Section(
                kind="chart",
                prompt=f"{second_agg} {measure} as a single big KPI number",
                w=4,
                h=4,
            )
        )
    if time and measure:
        # "by year of year" is what you get when the date column is itself
        # called year; say it once.
        if grain and grain.lower() not in time.lower():
            by = f"by {grain} of {time}"
        else:
            by = f"by {time}"
        charts.append(
            Section(kind="chart", prompt=f"{agg} {measure} {by} as a line chart", w=12, h=9)
        )
    if group and measure:
        charts.append(
            Section(kind="chart", prompt=f"{agg} {measure} by {group} as a bar chart", w=6, h=9)
        )
    if other and measure:
        charts.append(
            Section(kind="chart", prompt=f"Share of {measure} by {other} as a pie chart", w=6, h=9)
        )
    elif measure:
        charts.append(
            Section(kind="chart", prompt=f"Distribution of {measure} as a histogram", w=6, h=9)
        )
    if second and group:
        charts.append(
            Section(
                kind="chart",
                prompt=f"{_aggregation(second)} {second} by {group} as a bar chart",
                w=6,
                h=9,
            )
        )

    charts = charts[:max_charts]

    sections: List[Section] = [
        Section(
            kind="text",
            title=_headline(brief),
            text_body=_intro(profile, brief),
            w=12,
            h=3,
        )
    ]
    sections.extend(charts)
    return _lay_out(sections)


def _lay_out(sections: List[Section]) -> List[Section]:
    """Pack the sections into the 12-column grid, left to right, top down."""
    x = 0
    y = 0
    row_height = 0
    for section in sections:
        if x + section.w > 12:
            x = 0
            y += row_height
            row_height = 0
        section.x = x
        section.y = y
        x += section.w
        row_height = max(row_height, section.h)
    return sections


def sample_source(source: Dict[str, Any], data_dir: Any, rows: int = SAMPLE_ROWS) -> pd.DataFrame:
    """A bounded sample of whichever kind of source this is."""
    if source.get("type") == "db":
        from app.services import db_sources

        frame = db_sources.load_table_by_id(str(source["source_id"]), str(source["table"]))
        return frame.head(rows)

    from pathlib import Path

    path = Path(str(source.get("path") or source.get("name")))
    if not path.exists():
        path = Path(str(data_dir)) / str(source.get("name"))
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, nrows=rows)
    return pd.read_csv(path, nrows=rows)
