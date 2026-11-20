"""Blocks on a report canvas: create from a question, move, resize, delete."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.dashboard import Dashboard
from app.models.data_source import DataSource, DataSourceStatus, DataSourceType
from app.models.report_block import BlockKind, ReportBlock
from app.models.user import User
from app.services import db_sources
from app.services.agents.workflow import run_agent_workflow
from app.utils.figure_json import decode_typed_arrays

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

FALLBACK_SIGNATURE = "promptdash: deterministic fallback"

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

    started = time.perf_counter()
    logger.info(
        "[blocks] generate report=%s user=%s prompt=%s",
        dashboard_id,
        current_user.id,
        payload.prompt[:150],
    )
    result = await asyncio.to_thread(
        run_agent_workflow,
        payload.prompt,
        payload.data_source or "",
        _user_sources(db, report),
    )

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

    block = ReportBlock(
        dashboard_id=report.id,
        user_id=current_user.id,
        kind=kind,
        title=(metric_label or payload.prompt.strip())[:255],
        prompt=payload.prompt.strip(),
        code=code,
        # Decoded above, not in the browser: plotly serialises numeric columns
        # as base64 typed arrays, and storing them decoded keeps the stored
        # figure readable by any Plotly version.
        figure_json=json.dumps(figure),
        source_name=data_context.get("filename"),
        chart_type=plan.get("visualization_type"),
        used_fallback=FALLBACK_SIGNATURE in code,
        x=0,
        y=_next_row(db, report.id),
        w=width,
        h=height,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    logger.info(
        "[blocks] created %s in %.2fs (fallback=%s)",
        block.id,
        time.perf_counter() - started,
        block.used_fallback,
    )
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
