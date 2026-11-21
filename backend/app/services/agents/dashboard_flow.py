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

from app.services.agents.layout import INTRO_HEIGHT, intro_html, lay_out
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
