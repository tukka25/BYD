"""The label of each chart kind the model can draw.

Keyed by planning_contract.CHART_KINDS, the list the planner's checks use. The
labels are how the analyst and planner are told which kind the user picked.
The "/" menu and the chart kinds panel read the fixed list in
byd-web/lib/chart-kinds.ts, which also holds what each kind is best for, what
it needs and its aliases; tests/test_chart_kinds_frontend.py keeps that list's
ids, order and labels equal to these, so the UI can never offer a kind the
planner rejects.
"""
from __future__ import annotations

from app.services.agents.planning_contract import CHART_KINDS

KIND_INFO: dict[str, dict] = {
    "kpi": {"label": "KPI card"},
    "bar": {"label": "Bar chart"},
    "line": {"label": "Line chart"},
    "area": {"label": "Area chart"},
    "scatter": {"label": "Scatter plot"},
    "pie": {"label": "Pie chart"},
    "histogram": {"label": "Histogram"},
    "box": {"label": "Box plot"},
    "heatmap": {"label": "Heatmap"},
    "treemap": {"label": "Treemap"},
    "sunburst": {"label": "Sunburst"},
    "funnel": {"label": "Funnel"},
    "waterfall": {"label": "Waterfall"},
}


def chart_kinds() -> list[dict]:
    return [{"kind": kind, **KIND_INFO[kind]} for kind in CHART_KINDS]
