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
