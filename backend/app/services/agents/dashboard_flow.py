"""Plan and build a dashboard: describe the data, choose directions, plan the
charts in one call, then draw them one by one.

Pure orchestration with no database and no HTTP, so it can be tested with
fake models and real files. The endpoint turns these events into the SSE
stream and the saved blocks.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator, Iterator

from app.services.agents.chart_kinds import include_kinds
from app.services.agents.data_tools import PLANNER_TOOL_NAMES, ToolBox
from app.services.agents.discovery import Findings, Probe, discover
from app.services.agents.layout import INTRO_HEIGHT, intro_html, lay_out
from app.services.agents.links import render_links
from app.services.agents.planning import PlanStep, Retry, plan_charts_steps, propose_directions_steps
from app.services.agents.profiler import TableProfile, columns_by_table, profile_table
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


def _with_retry_status(steps: Generator[Retry | Probe, None, PlanStep], label: str) -> Generator[Event, None, PlanStep]:
    """Run one checked planning call, turning each retry, and each tool call the
    planner makes, into a status line; returns its PlanStep."""
    while True:
        try:
            step = next(steps)
        except StopIteration as done:
            return done.value
        if isinstance(step, Probe):
            yield Event("status", {"label": f"Checking the data: {_probe_words(step)}"})
        else:
            yield Event("status", {"label": f"{label}, try {step.attempt} of {step.of}"})


def _probe_words(probe: Probe) -> str:
    args = probe.args
    if probe.name == "find_columns":
        return f"looking for '{args.get('query', '')}'"
    if probe.name == "relationship":
        return f"{args.get('a', '')} and {args.get('b', '')}"
    if probe.name == "row_grain":
        return f"what one row of {args.get('table', 'the table')} is"
    if probe.name == "preview_chart":
        plans = args.get("plans")
        count = len(plans) if isinstance(plans, list) else 0
        return f"previewing {count} draft plan{'' if count == 1 else 's'}"
    return str(args.get("column") or args.get("x") or probe.name)


def _with_probe_status(steps: Generator[Probe, None, Findings]) -> Generator[Event, None, Findings]:
    """Run the tool step, turning each tool call into a status line; returns its Findings."""
    while True:
        try:
            probe = next(steps)
        except StopIteration as done:
            return done.value
        yield Event("status", {"label": f"Checking the data: {_probe_words(probe)}"})


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
    required_kinds: tuple[str, ...] = (),
    planner_tools: bool = False,
) -> Iterator[Event]:
    yield Event("status", {"label": "Reading your data"})
    tables = profile_sources(sources, data_dir, brief)
    if not tables:
        yield Event("error", {"detail": "None of this report's sources could be read."})
        return
    profiles = [entry.profile for entry in tables]
    links = render_links([entry.source["join"] for entry in tables if entry.source.get("join")])
    request = f"{brief}\n{include_kinds(required_kinds)}".strip() if required_kinds else brief

    facts, validate, planner_box = "", None, None
    if planner_tools:
        # PLANNER_TOOLS=planner: the planner holds the tools itself, so there is no explorer step.
        planner_box = ToolBox({entry.label: entry.source for entry in tables}, data_dir,
                              tools=PLANNER_TOOL_NAMES, kinds=columns_by_table(profiles))
        validate = planner_box.validate_spec
    elif explorer_llm is not None:
        toolbox = ToolBox({entry.label: entry.source for entry in tables}, data_dir)
        yield Event("status", {"label": "Checking the data"})
        findings = yield from _with_probe_status(discover(explorer_llm, request, profiles, toolbox))
        facts, validate = findings.note, toolbox.validate_spec

    choosing = "Choosing what to show"
    yield Event("status", {"label": choosing})
    directions = yield from _with_retry_status(
        propose_directions_steps(analyst_llm, request, profiles, facts, memory, links=links), choosing
    )
    if not directions.items:
        yield Event("error", {"detail": "Could not work out what to show from this data: "
                                        + "; ".join(directions.errors[:3])})
        return

    planning = "Planning the charts"
    yield Event("status", {"label": planning})
    charts = yield from _with_retry_status(
        plan_charts_steps(planner_llm, directions.items, profiles, facts, validate, links=links,
                           required_kinds=required_kinds, toolbox=planner_box), planning
    )
    if planner_box is not None:
        logger.info("[dashboard] planner tool calls (%d): %s", len(planner_box.calls),
                    "; ".join(f"{call.name}({call.args})" for call in planner_box.calls))
    if not charts.items:
        yield Event("error", {"detail": "Could not plan charts for this data: " + "; ".join(charts.errors[:3])})
        return

    placed = lay_out(charts.items, top=top + INTRO_HEIGHT)
    for n, item in enumerate(placed, 1):
        # Every field, so a bad chart can be traced to its plan or to the code drawn from it.
        logger.info("[dashboard] chart plan %d of %d: %s", n, len(placed), json.dumps(item.spec, ensure_ascii=False))
    intro = {"text": intro_html(profiles, brief, charts.items), "x": 0, "y": top, "w": 12, "h": INTRO_HEIGHT}
    # A kind the user picked that is still not in the plan after every try: said, never dropped silently.
    missing = [kind for kind in required_kinds if not any(spec["chart"] == kind for spec in charts.items)]
    if missing:
        logger.info("[dashboard] the plan has no %s, which the user asked for", ", ".join(missing))
    yield Event("plan", {
        "intro": intro, "placed": placed, "tables": tables,
        # How hard planning was: tries per call, and what the checks dropped.
        "attempts": {"analyst": directions.attempts, "planner": charts.attempts},
        "dropped": directions.errors[:5] + charts.errors[:5],
        "facts": facts.splitlines() if facts else [],
        "missing_kinds": missing,
    })

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
