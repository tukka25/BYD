"""Blocks on a report canvas: create from a question, move, resize, delete."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from functools import lru_cache
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.dashboard import Dashboard
from app.models.data_source import DataSource, DataSourceStatus, DataSourceType
from app.models.report_block import BlockKind, ReportBlock
from app.models.report_request import ReportRequest
from app.models.user import User
from app.services import db_sources
from app.services.agents import architect
from app.services.agents.narrator import Narrator
from app.services.agents.report_memory import describe_report
from app.services.llm import get_llm
from app.services.agents.dashboard_flow import build_dashboard
from app.services.agents.kind_request import run_kind_request
from app.services.agents.planning_contract import CHART_KINDS
from app.services.agents.workflow import _agents, run_agent_workflow
from app.utils.figure_json import decode_typed_arrays

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()



@lru_cache(maxsize=1)
def _narrator() -> Narrator:
    """Lazy, so importing this module does not reach for a model server."""
    return Narrator(llm=get_llm("narrator"))

# Grid units. The canvas is 12 columns wide; a chart wants half the width and
# enough height to be read, a metric is small, a note is wide and short.
DEFAULT_SIZE: Dict[str, tuple[int, int]] = {
    "chart": (6, 9),
    "metric": (4, 4),
    "text": (12, 3),
}


def _indicator_title(figure: Dict[str, Any]) -> Optional[str]:
    """The label on an all-`indicator` figure, or None if it is not one.

    A Plotly `indicator` trace IS a KPI card: one big number, no axes. The
    chartist writes them, so a question like "total revenue as one number"
    comes back as a figure rather than a chart, and is stored as a metric
    block sized like a tile. The trace carries its own label, which is a
    better block title than the sentence the user typed.
    """
    traces = figure.get("data") or []
    if not traces or not all(
        isinstance(t, dict) and t.get("type") == "indicator" for t in traces
    ):
        return None
    title = traces[0].get("title")
    if isinstance(title, dict):
        title = title.get("text")
    return title.strip() if isinstance(title, str) and title.strip() else ""


class BlockResponse(BaseModel):
    id: str
    kind: str
    title: str
    prompt: str | None = None
    code: str | None = None
    figure: Dict[str, Any] | None = None
    text_body: str | None = None
    source_name: str | None = None
    chart_type: str | None = None
    used_fallback: bool = False
    x: int
    y: int
    w: int
    h: int


class GenerateBlockRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    data_source: Optional[str] = None
    # A kind picked with "/" in the ask bar arrives as this field, never as text in the prompt.
    chart_kind: Optional[str] = None

    @field_validator("chart_kind")
    @classmethod
    def _known_kind(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in CHART_KINDS:
            raise ValueError(f"chart_kind must be one of: {', '.join(CHART_KINDS)}")
        return value


class CreateBlockRequest(BaseModel):
    kind: Literal["text", "metric"] = "text"
    title: str = ""
    text_body: str = ""


class UpdateBlockRequest(BaseModel):
    title: Optional[str] = None
    text_body: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    w: Optional[int] = None
    h: Optional[int] = None


class LayoutItem(BaseModel):
    id: str
    x: int
    y: int
    w: int
    h: int


def _to_response(block: ReportBlock) -> BlockResponse:
    figure = None
    if block.figure_json:
        try:
            figure = json.loads(block.figure_json)
        except json.JSONDecodeError:
            # A stored figure that will not parse is reported as absent rather
            # than taking the whole report down.
            logger.warning("[blocks] figure_json unparseable on block %s", block.id)
    return BlockResponse(
        id=block.id,
        kind=block.kind.value if hasattr(block.kind, "value") else str(block.kind),
        title=block.title or "",
        prompt=block.prompt,
        code=block.code,
        figure=figure,
        text_body=block.text_body,
        source_name=block.source_name,
        chart_type=block.chart_type,
        used_fallback=bool(block.used_fallback),
        x=block.x,
        y=block.y,
        w=block.w,
        h=block.h,
    )


def _owned_report(db: Session, dashboard_id: str, user: User) -> Dashboard:
    report = (
        db.query(Dashboard)
        .filter(Dashboard.id == dashboard_id, Dashboard.user_id == user.id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


def _next_row(db: Session, dashboard_id: str) -> int:
    """Place a new block below everything already on the canvas."""
    rows = db.query(ReportBlock).filter(ReportBlock.dashboard_id == dashboard_id).all()
    return max((b.y + b.h for b in rows), default=0)


def _record_request(db: Session, report: Dashboard, user: User, kind: str, text: str) -> None:
    """Keep what the user asked, in their words, for the report's memory."""
    db.add(ReportRequest(dashboard_id=report.id, user_id=user.id, kind=kind, text=(text or "").strip()[:2000]))
    db.commit()


def _report_memory(db: Session, report_id: str) -> str:
    blocks = db.query(ReportBlock).filter(ReportBlock.dashboard_id == report_id).order_by(ReportBlock.created_at).all()
    requests = (
        db.query(ReportRequest).filter(ReportRequest.dashboard_id == report_id).order_by(ReportRequest.created_at).all()
    )
    return describe_report(
        [{"kind": b.kind.value if hasattr(b.kind, "value") else str(b.kind), "title": b.title,
          "chart_type": b.chart_type, "prompt": b.prompt} for b in blocks],
        [{"kind": r.kind, "text": r.text} for r in requests],
    )


# A connection can hold many tables; enumerating them costs a metadata query
# each, so the per-question list is kept shorter than the one the UI shows.
_CANDIDATE_TABLES = 20


def _user_sources(db: Session, report: Dashboard) -> list[Dict[str, Any]]:
    """What this report is allowed to read: its own sources, else everything.

    A report that names its sources is answered only from those. Before this
    the picker recorded a choice and generation ignored it, which made the
    "Data for this report" step decorative.
    """
    chosen = list(report.data_sources or [])
    if chosen:
        rows = [row for row in chosen if row.status == DataSourceStatus.ACTIVE]
    else:
        rows = (
            db.query(DataSource)
            .filter(
                DataSource.user_id == report.user_id,
                DataSource.status == DataSourceStatus.ACTIVE,
            )
            .all()
        )

    sources: list[Dict[str, Any]] = []
    for row in rows:
        if row.source_type == DataSourceType.FILE:
            path = row.file_path or row.original_filename or row.display_name
            if path:
                sources.append(
                    {
                        "id": row.id,
                        "name": row.original_filename or row.display_name,
                        "type": "file",
                        "path": path,
                    }
                )
        elif row.source_type == DataSourceType.DB:
            # A table is the candidate, not the connection: a chart is built
            # from one table. An unreachable database contributes nothing
            # rather than failing the whole question.
            sources.extend(db_sources.candidates_for(row, max_tables=_CANDIDATE_TABLES))
    return sources


@router.get("/{dashboard_id}/blocks", response_model=list[BlockResponse])
def list_blocks(
    dashboard_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _owned_report(db, dashboard_id, current_user)
    blocks = (
        db.query(ReportBlock)
        .filter(ReportBlock.dashboard_id == dashboard_id)
        .order_by(ReportBlock.y, ReportBlock.x)
        .all()
    )
    return [_to_response(b) for b in blocks]


@router.post(
    "/{dashboard_id}/blocks/generate",
    response_model=BlockResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_block(
    dashboard_id: str,
    payload: GenerateBlockRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run the agent workflow for one question and keep the result as a block."""
    report = _owned_report(db, dashboard_id, current_user)
    _record_request(db, report, current_user, "chart", payload.prompt)

    started = time.perf_counter()
    logger.info(
        "[blocks] generate report=%s user=%s chart_kind=%s prompt=%s",
        dashboard_id,
        current_user.id,
        payload.chart_kind or "-",
        payload.prompt[:150],
    )
    sources = _user_sources(db, report)
    if payload.chart_kind:
        result = await asyncio.to_thread(
            run_kind_request, payload.prompt, payload.chart_kind, sources, payload.data_source or "",
            get_llm("spec_planner"), _agents()[2], settings.UPLOAD_DIR,
        )
    else:
        result = await asyncio.to_thread(run_agent_workflow, payload.prompt, payload.data_source or "", sources)

    if result.get("error"):
        logger.warning("[blocks] workflow error: %s", result["error"])
        raise HTTPException(status_code=400, detail=result["error"])

    figure = (result.get("execution_result") or {}).get("figure")
    if not figure:
        raise HTTPException(
            status_code=400,
            detail="The code ran but produced no figure. Try rephrasing the question.",
        )

    code = result.get("code") or ""
    data_context = result.get("data_context") or {}
    plan = result.get("plan") or {}

    figure = decode_typed_arrays(figure)
    metric_label = _indicator_title(figure)
    is_metric = metric_label is not None
    kind = BlockKind.METRIC if is_metric else BlockKind.CHART
    width, height = DEFAULT_SIZE["metric" if is_metric else "chart"]

    # The block is titled by the model, not by the sentence the user typed. A
    # KPI already carries the label its own figure declares, so that one wins.
    title = metric_label or (result.get("spec") or {}).get("title") or await asyncio.to_thread(
        _narrator().title_for,
        payload.prompt,
        data_context.get("columns") or [],
    )

    block = ReportBlock(
        dashboard_id=report.id,
        user_id=current_user.id,
        kind=kind,
        title=(title or payload.prompt.strip())[:255],
        prompt=payload.prompt.strip(),
        code=code,
        # Decoded above, not in the browser: plotly serialises numeric columns
        # as base64 typed arrays, and storing them decoded keeps the stored
        # figure readable by any Plotly version.
        figure_json=json.dumps(figure),
        source_name=data_context.get("filename"),
        chart_type=plan.get("visualization_type"),
        x=0,
        y=_next_row(db, report.id),
        w=width,
        h=height,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    logger.info("[blocks] created %s in %.2fs", block.id, time.perf_counter() - started)
    return _to_response(block)


@router.post("/{dashboard_id}/blocks", response_model=BlockResponse, status_code=status.HTTP_201_CREATED)
def create_block(
    dashboard_id: str,
    payload: CreateBlockRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = _owned_report(db, dashboard_id, current_user)
    width, height = DEFAULT_SIZE.get(payload.kind, DEFAULT_SIZE["text"])
    block = ReportBlock(
        dashboard_id=report.id,
        user_id=current_user.id,
        kind=BlockKind(payload.kind),
        title=payload.title[:255],
        text_body=payload.text_body,
        x=0,
        y=_next_row(db, report.id),
        w=width,
        h=height,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return _to_response(block)


@router.patch("/{dashboard_id}/blocks/{block_id}", response_model=BlockResponse)
def update_block(
    dashboard_id: str,
    block_id: str,
    payload: UpdateBlockRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _owned_report(db, dashboard_id, current_user)
    block = (
        db.query(ReportBlock)
        .filter(ReportBlock.id == block_id, ReportBlock.dashboard_id == dashboard_id)
        .first()
    )
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")

    for field in ("title", "text_body", "x", "y", "w", "h"):
        value = getattr(payload, field)
        if value is not None:
            setattr(block, field, value)
    db.commit()
    db.refresh(block)
    return _to_response(block)


@router.put("/{dashboard_id}/blocks/layout", response_model=list[BlockResponse])
def save_layout(
    dashboard_id: str,
    items: list[LayoutItem],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist the whole grid in one call, so a drag writes once rather than per block."""
    _owned_report(db, dashboard_id, current_user)
    blocks = {
        b.id: b
        for b in db.query(ReportBlock).filter(ReportBlock.dashboard_id == dashboard_id).all()
    }
    for item in items:
        block = blocks.get(item.id)
        if block:
            block.x, block.y, block.w, block.h = item.x, item.y, item.w, item.h
    db.commit()
    return [_to_response(b) for b in sorted(blocks.values(), key=lambda b: (b.y, b.x))]


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class DashboardBriefRequest(BaseModel):
    """What the dashboard should be about. Empty means "plan it from the data"."""

    brief: str = Field(default="", max_length=400)
    # Kinds picked with "/" in the brief; the plan must include one of each.
    chart_kinds: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("chart_kinds")
    @classmethod
    def _known_kinds(cls, value: list[str]) -> list[str]:
        unknown = [kind for kind in value if kind not in CHART_KINDS]
        if unknown:
            raise ValueError(f"unknown chart kinds {unknown}; kinds are: {', '.join(CHART_KINDS)}")
        return list(dict.fromkeys(value))


@router.post("/{dashboard_id}/blocks/dashboard")
async def generate_whole_dashboard(
    dashboard_id: str,
    payload: DashboardBriefRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Plan a dashboard from the data, then build it block by block.

    Streamed, because this is several model calls and five to eight chart
    generations end to end. A single response would leave the user with a
    spinner and no idea whether anything was happening; here each stage and
    each block is reported the moment it happens.
    """
    report = _owned_report(db, dashboard_id, current_user)
    sources = _user_sources(db, report)
    if not sources:
        raise HTTPException(
            status_code=400,
            detail="This report has no data to plan from. Add a file or a database first.",
        )
    brief = (payload.brief if payload else "").strip()
    mode = (settings.DASHBOARD_PLANNER or "ai").strip().lower()
    if mode == "rules":
        return await _rules_dashboard(report, sources, brief, current_user, db)
    if mode != "ai":
        raise HTTPException(
            status_code=500, detail=f"DASHBOARD_PLANNER must be 'ai' or 'rules', got {mode!r}"
        )
    memory = _report_memory(db, report.id)  # before this request is recorded: it is the brief, not history
    _record_request(db, report, current_user, "dashboard", brief)
    kinds = list(payload.chart_kinds) if payload else []
    return _ai_dashboard(report, sources, brief, current_user, db, memory, kinds)


def _ai_dashboard(report, sources, brief, current_user, db, memory: str = "", chart_kinds: list[str] | None = None):
    """The analyst proposes, the planner plans every chart at once, code checks
    both against the real tables, and the chartist draws each chart from its plan
    (agents/dashboard_flow.py). Nothing here reads a column name."""
    base_row = _next_row(db, report.id)
    tools_on = (settings.PLANNER_TOOLS or "off").strip().lower() == "on"
    flow = build_dashboard(
        brief,
        sources,
        settings.UPLOAD_DIR,
        get_llm("analyst"),
        get_llm("spec_planner"),
        _agents()[2],
        top=base_row,
        explorer_llm=get_llm("explorer") if tools_on else None,
        memory=memory,
        required_kinds=tuple(chart_kinds or ()),
    )

    async def events():
        iterator = iter(flow)
        total = 0
        while True:
            # The flow is synchronous model calls; each step runs off the event loop.
            event = await asyncio.to_thread(next, iterator, None)
            if event is None:
                break
            if event.kind == "status":
                yield _sse("status", event.data)
            elif event.kind == "error":
                yield _sse("error", event.data)
                return
            elif event.kind == "plan":
                intro, placed = event.data["intro"], event.data["placed"]
                total = len(placed) + 1
                sections = [
                    {"index": 0, "kind": "text", "label": "About this data",
                     "x": intro["x"], "y": intro["y"], "w": intro["w"], "h": intro["h"]}
                ]
                sections += [
                    {"index": n + 1, "kind": "chart", "label": p.spec["title"],
                     "x": p.x, "y": p.y, "w": p.w, "h": p.h}
                    for n, p in enumerate(placed)
                ]
                names = ", ".join(entry.label for entry in event.data["tables"])
                missing = event.data.get("missing_kinds", [])
                logger.info(
                    "[dashboard] planned %d charts from %s (tries: %s; dropped: %s; facts: %s; missing kinds: %s)",
                    len(placed), names, event.data["attempts"], event.data["dropped"], event.data.get("facts"),
                    missing,
                )
                yield _sse("plan", {"total": total, "source": names, "brief": brief, "sections": sections,
                                    "missing_kinds": missing})
                try:
                    block = ReportBlock(
                        dashboard_id=report.id,
                        user_id=current_user.id,
                        kind=BlockKind.TEXT,
                        title="About this data",
                        text_body=intro["text"],
                        x=intro["x"],
                        y=intro["y"],
                        w=intro["w"],
                        h=intro["h"],
                    )
                    db.add(block)
                    db.commit()
                    db.refresh(block)
                    yield _sse("block", _to_response(block).model_dump(mode="json"))
                except Exception as exc:  # noqa: BLE001 - one bad block must not end the build
                    db.rollback()
                    logger.exception("[dashboard] intro block failed")
                    yield _sse("skipped", {"index": 0, "label": "About this data", "reason": str(exc)})
            elif event.kind == "step":
                placed = event.data["placed"]
                yield _sse(
                    "step",
                    {"index": event.data["index"] + 1, "total": total, "label": placed.spec["title"]},
                )
            elif event.kind == "skipped":
                placed = event.data["placed"]
                yield _sse(
                    "skipped",
                    {"index": event.data["index"] + 1, "label": placed.spec["title"],
                     "reason": event.data["reason"]},
                )
            elif event.kind == "chart":
                placed, result = event.data["placed"], event.data["result"]
                spec = placed.spec
                try:
                    figure = decode_typed_arrays(result["execution_result"]["figure"])
                    code = result.get("code") or ""
                    context = result.get("data_context") or {}
                    block = ReportBlock(
                        dashboard_id=report.id,
                        user_id=current_user.id,
                        kind=BlockKind.METRIC if _indicator_title(figure) is not None else BlockKind.CHART,
                        title=spec["title"][:255],
                        prompt=spec["question"],
                        code=code,
                        figure_json=json.dumps(figure),
                        source_name=context.get("filename") or context.get("table"),
                        chart_type=spec["chart"],
                                        x=placed.x,
                        y=placed.y,
                        w=placed.w,
                        h=placed.h,
                    )
                    db.add(block)
                    db.commit()
                    db.refresh(block)
                    yield _sse("block", _to_response(block).model_dump(mode="json"))
                except Exception as exc:  # noqa: BLE001 - one bad block must not end the build
                    db.rollback()
                    logger.exception("[dashboard] block %s failed", spec["title"])
                    yield _sse(
                        "skipped",
                        {"index": event.data["index"] + 1, "label": spec["title"], "reason": str(exc)},
                    )
        yield _sse("done", {"total": total})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _rules_dashboard(report, sources, brief, current_user, db):
    """The previous name-based architect, kept behind DASHBOARD_PLANNER=rules."""
    source = sources[0]
    try:
        frame = await asyncio.to_thread(
            architect.sample_source, source, settings.UPLOAD_DIR
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[dashboard] could not sample %s: %s", source.get("name"), exc)
        raise HTTPException(status_code=400, detail=f"Could not read that source: {exc}")

    profile = architect.profile_frame(str(source.get("name")), frame)
    sections = architect.plan(profile, brief=brief)
    if not sections:
        raise HTTPException(
            status_code=400,
            detail=(
                "Nothing chartable was found in that source — it needs at least one numeric "
                "column or one column with a small set of repeated values."
            ),
        )

    base_row = _next_row(db, report.id)
    source_hint = str(source.get("name") or "")

    async def events():
        # The geometry goes out with the plan so the canvas can put every
        # block's placeholder down at once, in its final position and size,
        # instead of growing one tile at a time.
        yield _sse(
            "plan",
            {
                "total": len(sections),
                "source": profile.name,
                "brief": brief,
                "sections": [
                    {
                        "index": i,
                        "kind": s.kind,
                        "label": s.title or s.prompt,
                        "x": s.x,
                        "y": base_row + s.y,
                        "w": s.w,
                        "h": s.h,
                    }
                    for i, s in enumerate(sections)
                ],
            },
        )

        for index, section in enumerate(sections):
            yield _sse(
                "step",
                {"index": index, "total": len(sections), "label": section.title or section.prompt},
            )

            try:
                if section.kind == "text":
                    block = ReportBlock(
                        dashboard_id=report.id,
                        user_id=current_user.id,
                        kind=BlockKind.TEXT,
                        title=section.title or "About this data",
                        text_body=section.text_body,
                        x=section.x,
                        y=base_row + section.y,
                        w=section.w,
                        h=section.h,
                    )
                else:
                    result = await asyncio.to_thread(
                        run_agent_workflow, section.prompt, source_hint, sources
                    )
                    figure = (result.get("execution_result") or {}).get("figure")
                    if result.get("error") or not figure:
                        yield _sse(
                            "skipped",
                            {
                                "index": index,
                                "label": section.prompt,
                                "reason": result.get("error") or "no figure was produced",
                            },
                        )
                        continue

                    figure = decode_typed_arrays(figure)
                    metric_label = _indicator_title(figure)
                    code = result.get("code") or ""
                    context = result.get("data_context") or {}
                    title = metric_label or await asyncio.to_thread(
                        _narrator().title_for, section.prompt, context.get("columns") or []
                    )
                    block = ReportBlock(
                        dashboard_id=report.id,
                        user_id=current_user.id,
                        kind=BlockKind.METRIC if metric_label is not None else BlockKind.CHART,
                        title=(title or section.prompt)[:255],
                        prompt=section.prompt,
                        code=code,
                        figure_json=json.dumps(figure),
                        source_name=context.get("filename"),
                        chart_type=(result.get("plan") or {}).get("visualization_type"),
                                        x=section.x,
                        y=base_row + section.y,
                        w=section.w,
                        h=section.h,
                    )

                db.add(block)
                db.commit()
                db.refresh(block)
                yield _sse("block", _to_response(block).model_dump(mode="json"))
            except Exception as exc:  # noqa: BLE001 - one bad block must not end the build
                db.rollback()
                logger.exception("[dashboard] block %s failed", index)
                yield _sse("skipped", {"index": index, "label": section.prompt, "reason": str(exc)})

        yield _sse("done", {"total": len(sections)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/{dashboard_id}/blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_block(
    dashboard_id: str,
    block_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _owned_report(db, dashboard_id, current_user)
    block = (
        db.query(ReportBlock)
        .filter(ReportBlock.id == block_id, ReportBlock.dashboard_id == dashboard_id)
        .first()
    )
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
    db.delete(block)
    db.commit()
    return None
