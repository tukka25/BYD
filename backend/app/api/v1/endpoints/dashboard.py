from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any
import asyncio
import json
import logging
import time
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.dashboard import Dashboard
from app.models.data_source import DataSource, DataSourceStatus, DataSourceType
from app.models.user import User
from app.schemas.dashboard import (
    DashboardCreateRequest,
    DashboardResponse as DashboardRecordResponse,
    DashboardUpdateRequest,
)
from app.services.agents.workflow import run_agent_workflow
from app.utils.figure_json import decode_typed_arrays

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


def _model_label() -> str:
    """Which model actually served the request, not a hardcoded Ollama name."""
    if (settings.LLM_BACKEND or "").lower() == "mlx":
        return f"{settings.chartist_model} (mlx)"
    return f"{settings.OLLAMA_MODEL} (ollama)"

class DashboardRequest(BaseModel):
    prompt: str
    data_source: Optional[str] = None # path to CSV or similar
    request_id: Optional[str] = None

class DashboardResponse(BaseModel):
    dashboard_html: str
    metadata: Dict[str, Any]


def _dashboard_to_response(dashboard: Dashboard) -> DashboardRecordResponse:
    return DashboardRecordResponse(
        id=dashboard.id,
        user_id=dashboard.user_id,
        title=dashboard.title,
        description=dashboard.description,
        data_source_ids=[ds.id for ds in dashboard.data_sources],
        created_at=dashboard.created_at,
        updated_at=dashboard.updated_at,
    )


@router.post("", response_model=DashboardRecordResponse, status_code=status.HTTP_201_CREATED)
def create_dashboard(
    payload: DashboardCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    linked_sources: list[DataSource] = []
    if payload.data_source_ids:
        linked_sources = (
            db.query(DataSource)
            .filter(
                DataSource.user_id == current_user.id,
                DataSource.id.in_(payload.data_source_ids),
            )
            .all()
        )
        if len(linked_sources) != len(set(payload.data_source_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more data_source_ids are invalid or not owned by the current user",
            )

    dashboard = Dashboard(
        user_id=current_user.id,
        title=payload.title.strip(),
        description=payload.description,
    )
    dashboard.data_sources = linked_sources
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)
    return _dashboard_to_response(dashboard)


@router.get("", response_model=list[DashboardRecordResponse])
def list_dashboards(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dashboards = (
        db.query(Dashboard)
        .filter(Dashboard.user_id == current_user.id)
        .order_by(Dashboard.created_at.desc())
        .all()
    )
    return [_dashboard_to_response(dashboard) for dashboard in dashboards]


@router.get("/{dashboard_id}", response_model=DashboardRecordResponse)
def get_dashboard(
    dashboard_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dashboard = (
        db.query(Dashboard)
        .filter(Dashboard.id == dashboard_id, Dashboard.user_id == current_user.id)
        .first()
    )
    if not dashboard:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
    return _dashboard_to_response(dashboard)


@router.put("/{dashboard_id}", response_model=DashboardRecordResponse)
def update_dashboard(
    dashboard_id: str,
    payload: DashboardUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dashboard = (
        db.query(Dashboard)
        .filter(Dashboard.id == dashboard_id, Dashboard.user_id == current_user.id)
        .first()
    )
    if not dashboard:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")

    if payload.title is not None:
        dashboard.title = payload.title.strip()
    if payload.description is not None:
        dashboard.description = payload.description

    if payload.data_source_ids is not None:
        linked_sources = []
        if payload.data_source_ids:
            linked_sources = (
                db.query(DataSource)
                .filter(
                    DataSource.user_id == current_user.id,
                    DataSource.id.in_(payload.data_source_ids),
                )
                .all()
            )
            if len(linked_sources) != len(set(payload.data_source_ids)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One or more data_source_ids are invalid or not owned by the current user",
                )
        dashboard.data_sources = linked_sources

    db.commit()
    db.refresh(dashboard)
    return _dashboard_to_response(dashboard)

def _user_file_sources(db: Session, user_id: str) -> list[Dict[str, Any]]:
    """The caller's registered file sources, as detective candidates.

    The DB is authoritative here. The canvas keeps its own copy of the source
    list in localStorage and never sent it, so the detective had nothing to rank
    and fell back to scanning the upload directory.
    """
    rows = (
        db.query(DataSource)
        .filter(
            DataSource.user_id == user_id,
            DataSource.status == DataSourceStatus.ACTIVE,
            DataSource.source_type == DataSourceType.FILE,
        )
        .all()
    )
    sources: list[Dict[str, Any]] = []
    for row in rows:
        path = row.file_path or row.original_filename or row.display_name
        if not path:
            continue
        sources.append(
            {
                "id": row.id,
                "name": row.original_filename or row.display_name,
                "type": "file",
                "path": path,
            }
        )
    return sources


@router.post("/generate", response_model=DashboardResponse)
async def generate_dashboard(
    request: DashboardRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a dashboard based on the user prompt using the multi-agent workflow.

    Requires authentication. This endpoint was previously the only unauthenticated
    route on the router, which left the most expensive operation in the API — a
    multi-agent LLM run — open to anyone who could reach the port.
    """
    try:
        started_at = time.perf_counter()
        logger.info(
            "[dashboard/generate] start request_id=%s user=%s prompt=%s",
            request.request_id or "-",
            current_user.id,
            request.prompt[:150],
        )
        available_sources = _user_file_sources(db, current_user.id)
        workflow_call = asyncio.to_thread(
            run_agent_workflow,
            request.prompt,
            request.data_source or "",
            available_sources,
        )
        if settings.WORKFLOW_TIMEOUT_SECONDS and settings.WORKFLOW_TIMEOUT_SECONDS > 0:
            result = await asyncio.wait_for(
                workflow_call,
                timeout=settings.WORKFLOW_TIMEOUT_SECONDS,
            )
        else:
            result = await workflow_call
        workflow_error = result.get("error")
        if workflow_error:
            logger.warning("[dashboard/generate] workflow error: %s", workflow_error)
            raise HTTPException(status_code=400, detail=workflow_error)

        execution_result = result.get("execution_result", {})
        figure = execution_result.get("figure")
        if not figure:
            output = execution_result.get("output", "")
            html_content = f"<div>No graph generated. Output: {output}</div>"
        else:
            # plotly 7 encodes numeric columns as base64 typed arrays, which the
            # CDN's plotly.js 2.35.2 cannot read -- the chart would render blank.
            figure_json = json.dumps(decode_typed_arrays(figure))
            html_content = f"""
<div id="promptdash-chart" style="width:100%;height:100%;min-height:420px;"></div>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<script>
  (function() {{
    const fig = {figure_json};
    Plotly.newPlot("promptdash-chart", fig.data, fig.layout || {{}}, {{responsive: true}});
  }})();
</script>
"""

        elapsed = time.perf_counter() - started_at
        logger.info(
            "[dashboard/generate] success request_id=%s in %.2fs",
            request.request_id or "-",
            elapsed,
        )
        return {
            "dashboard_html": html_content,
            "metadata": {
                "request_id": request.request_id,
                "model": _model_label(),
                "llm_backend": settings.LLM_BACKEND,
                "plan": result.get("plan", {}),
                "data_context": result.get("data_context", {}),
                "agent_steps": [m.content for m in result.get("messages", [])],
                # The generated program, so a caller can tell whether the model
                # wrote the chart or the deterministic fallback did.
                "code": result.get("code", ""),
                "used_fallback": "promptdash: deterministic fallback" in (result.get("code") or ""),
            }
        }
    except asyncio.TimeoutError as exc:
        logger.error(
            "[dashboard/generate] timed out after %ss",
            settings.WORKFLOW_TIMEOUT_SECONDS,
        )
        raise HTTPException(
            status_code=504,
            detail=(
                f"Workflow timed out after {settings.WORKFLOW_TIMEOUT_SECONDS}s. "
                f"Check that the {settings.LLM_BACKEND} backend is reachable and the "
                "model is loaded, then see the backend logs."
            ),
        ) from exc
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[dashboard/generate] unhandled error")
        raise HTTPException(status_code=500, detail=str(e))
