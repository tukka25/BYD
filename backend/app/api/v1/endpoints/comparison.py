"""Side-by-side: the local fine-tuned chartist against Claude Opus 5.5.

Streamed, because each cell is a real generation and a run is a dozen of them.
Nothing here is persisted: a comparison is an experiment, and its result is the
evidence on screen, not a report to keep.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.data_source import DataSource, DataSourceStatus, DataSourceType
from app.models.user import User
from app.services import comparison, db_sources
from app.services.agents import architect
from app.services.agents.workflow import _agents
from app.services.llm import get_llm

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# Each question is one generation per engine, and the API side costs money, so
# a run is bounded rather than however many the planner felt like.
MAX_QUESTIONS = 5
SAMPLE_ROWS = 50_000


class CompareRequest(BaseModel):
    source_id: str
    table: Optional[str] = None
    brief: str = Field(default="", max_length=400)


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _load(source: DataSource, table: Optional[str]) -> tuple[pd.DataFrame, str]:
    if source.source_type == DataSourceType.DB:
        tables = [t["table"] for t in db_sources.tables_with_columns(source, limit=40)]
        if not tables:
            raise HTTPException(status_code=400, detail="That database has no readable tables.")
        chosen = table if table in tables else tables[0]
        frame = architect.spread_sample(db_sources.load_table(source, chosen), SAMPLE_ROWS)
        return frame, f"{chosen} · {source.display_name}"

    path = source.file_path or source.original_filename or source.display_name
    frame = architect.sample_source(
        {"type": "file", "path": path, "name": source.display_name},
        settings.UPLOAD_DIR,
        rows=SAMPLE_ROWS,
    )
    return frame, source.display_name


@router.get("/engines")
def list_engines():
    """Which sides of the comparison this server can actually run."""
    available = comparison.available_engines()
    return [
        {"id": engine, "label": comparison.ENGINE_LABELS[engine], "available": ok}
        for engine, ok in available.items()
    ]


@router.post("/run")
async def run_comparison(
    payload: CompareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    source = (
        db.query(DataSource)
        .filter(
            DataSource.id == payload.source_id,
            DataSource.user_id == current_user.id,
            DataSource.status == DataSourceStatus.ACTIVE,
        )
        .first()
    )
    if source is None:
        raise HTTPException(status_code=404, detail="That data source was not found.")

    frame, source_label = await asyncio.to_thread(_load, source, payload.table)
    profile = architect.profile_frame(source_label, frame)
    planned = architect.plan(profile, brief=payload.brief)
    charts = [s for s in planned if s.kind == "chart"][:MAX_QUESTIONS]
    if not charts:
        raise HTTPException(
            status_code=400,
            detail="Nothing chartable was found in that source.",
        )
    # The opening text block is composed from the profile, not by a model, so
    # it is identical on both sides and is shown once rather than twice.
    intro = next((s.text_body for s in planned if s.kind == "text"), "")
    intro_title = next((s.title for s in planned if s.kind == "text"), "")
    questions = [s.prompt for s in charts]

    # Built once and shared by both engines: identical columns, dtypes and rows.
    data_context = {
        "filename": source_label,
        "columns": [str(c) for c in frame.columns],
        "dtypes": {str(c): str(d) for c, d in frame.dtypes.items()},
        "sample": json.loads(frame.head(3).to_json(orient="records", date_format="iso")),
    }

    planner, _detective, _chartist, executor = _agents()
    chartists = comparison.build_chartists(get_llm("chartist"))
    engines = [e for e in (comparison.SLM, comparison.OPUS) if e in chartists]

    async def events():
        yield _sse(
            "plan",
            {
                "source": source_label,
                "rows": int(len(frame)),
                "columns": data_context["columns"],
                "questions": questions,
                "intro": intro,
                "intro_title": intro_title,
                # The same plan lays out both dashboards, so a difference on
                # screen is the chart and never the arrangement.
                "sections": [
                    {"index": i, "question": s.prompt, "x": s.x, "y": s.y, "w": s.w, "h": s.h}
                    for i, s in enumerate(charts)
                ],
                "engines": [
                    {"id": e, "label": comparison.ENGINE_LABELS[e]} for e in engines
                ],
            },
        )

        for index, question in enumerate(questions):
            # One plan for the question, shared, so neither side is asked for a
            # different chart type than the other.
            try:
                task_plan = await asyncio.to_thread(planner.create_plan, question)
                if hasattr(task_plan, "model_dump"):
                    task_plan = task_plan.model_dump()
            except Exception:  # noqa: BLE001
                # "default", so a planner crash is never sent to either model
                # as an instruction to draw a bar chart.
                task_plan = {"visualization_type": "bar", "chart_type_source": "default"}

            yield _sse("question", {"index": index, "question": question, "plan": task_plan})

            for engine in engines:
                result = await asyncio.to_thread(
                    comparison.run_cell,
                    engine,
                    chartists[engine],
                    question,
                    task_plan,
                    data_context,
                    frame,
                    executor,
                )
                payload_out = result.to_json()
                payload_out["index"] = index
                yield _sse("cell", payload_out)

        yield _sse("done", {"questions": len(questions)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
