"""A single chart in the kind the user picked with "/".

The pick travels as a field, not as words in the prompt, and reaches the
chartist the way lora-v2 was trained to read a chart kind: inside a chart plan.
So this is the dashboard's path shrunk to one chart. The detective picks the
table, the planner writes one plan that must be that kind (checked, retried),
and the chartist draws it through the same repair loop. A joined table comes
with the same join line build_dashboard gives the planner. Nothing here draws a chart.
"""
from __future__ import annotations

from typing import Any, Callable

from app.services.agents.chart_kinds import KIND_INFO
from app.services.agents.dashboard_flow import profile_sources
from app.services.agents.links import render_links
from app.services.agents.planning import plan_charts
from app.services.agents.spec_runner import run_spec

MAX_DIRECTION_COLUMNS = 12


def run_kind_request(
    question: str,
    chart_kind: str,
    sources: list[dict],
    selected_source: str,
    planner_llm: Any,
    chartist: Any,
    data_dir: str,
    detect: Callable[[dict], dict] | None = None,
) -> dict:
    if detect is None:
        from app.services.agents.workflow import data_sourcing_node as detect
    label = KIND_INFO[chart_kind]["label"].lower()
    asked = {"visualization_type": chart_kind, "chart_type_source": "user"}
    decision = detect({"user_query": question, "plan": {"visualization_type": chart_kind},
                       "selected_source": selected_source, "available_sources": sources})
    if decision.get("error"):
        return {"error": decision["error"], "plan": asked}
    selected = (decision.get("source_decision") or {}).get("selected") or {}
    entries = profile_sources([selected], data_dir)
    if not entries:
        return {"error": f"Could not read {selected.get('name', 'that source')}.", "plan": asked}
    entry = entries[0]
    direction = {"question": question.strip(), "why": f"the user asked for a {label}", "table": entry.label,
                 "columns": [column.name for column in entry.profile.columns][:MAX_DIRECTION_COLUMNS]}
    links = render_links([entry.source["join"]] if entry.source.get("join") else [])
    step = plan_charts(planner_llm, [direction], [entry.profile], links=links, required_kinds=(chart_kind,))
    spec = next((s for s in step.items if s["chart"] == chart_kind), None)
    if spec is None:
        return {"error": f"The model could not plan a {label} for this question: " + "; ".join(step.errors[:3]),
                "plan": asked}
    return {**run_spec(spec, entry.source, chartist, data_dir), "spec": spec, "plan": asked}
