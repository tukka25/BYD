"""The chart mix we choose, rather than the one the Plotly docs happened to have."""
from __future__ import annotations

import re

QUOTA: dict[str, float] = {
    "bar": 0.15,
    "line": 0.15,
    "grouped_or_stacked_bar": 0.10,
    "scatter": 0.10,
    "pie_or_donut": 0.08,
    "area": 0.08,
    "histogram": 0.07,
    "box": 0.07,
    "heatmap": 0.07,
    "time_series": 0.06,
    "treemap_funnel_waterfall": 0.05,
    "gauge_or_indicator": 0.02,
}

# Plotly trace types each bucket may legitimately produce, for the eval's
# chart-type match check.
TRACE_TYPES: dict[str, set[str]] = {
    "bar": {"bar"},
    "line": {"scatter", "scattergl"},
    "grouped_or_stacked_bar": {"bar"},
    "scatter": {"scatter", "scattergl"},
    "pie_or_donut": {"pie"},
    "area": {"scatter", "scattergl"},
    "histogram": {"histogram", "bar"},
    "box": {"box"},
    "heatmap": {"heatmap", "histogram2d"},
    "time_series": {"scatter", "scattergl", "bar"},
    "treemap_funnel_waterfall": {"treemap", "funnel", "waterfall", "sunburst"},
    "gauge_or_indicator": {"indicator"},
}

HARD_CASE_KINDS: list[str] = [
    "multi_column_aggregation",
    "date_parsing_and_resampling",
    "grouped_or_faceted",
    "missing_field",
    "ambiguous_question",
]

HARD_CASE_SHARE = 0.40


def allocate(total: int) -> dict[str, int]:
    """Split a row budget across the quota, preserving the total exactly."""
    counts = {k: int(total * v) for k, v in QUOTA.items()}
    shortfall = total - sum(counts.values())
    for key in sorted(QUOTA, key=lambda k: -QUOTA[k])[:shortfall]:
        counts[key] += 1
    return counts


# TRACE_TYPES maps line, scatter, area and time_series all to {scatter, scattergl},
# so the trace type alone cannot tell an area chart from a line chart. The
# discriminator is in the code: every area target uses px.area, fill= or
# stackgroup, and no line/scatter/time_series target does.
_AREA_MARKERS = re.compile(r"\bpx\s*\.\s*area\s*\(|\bfill\s*=|\bstackgroup\s*=")


def is_area_figure(code: str) -> bool:
    """True if the code builds an area chart (px.area, a fill= or a stackgroup=)."""
    return bool(_AREA_MARKERS.search(code or ""))
