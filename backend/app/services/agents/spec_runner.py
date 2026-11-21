"""Draw one chart from its plan: the chartist writes it, the runner runs it.

A plan already names the table and the columns, so the planner and the data
detective, which exist to work those out from a question, are skipped. The
code still goes through the same executor, the same property repair and the
same backup chart as every other chart (`workflow.run_chart_code`).
"""
from __future__ import annotations

from typing import Any

_FALLBACK_KIND = {"line": "line", "area": "line", "scatter": "scatter"}


def fallback_kind(chart: str) -> str:
    """The backup chart's type: the deterministic renderer knows line, scatter and bar."""
    return _FALLBACK_KIND.get(chart, "bar")


def context_for(source: dict, data_dir: str) -> dict:
    """Columns, dtypes and three rows for the chartist, from a file or a table."""
    if source.get("type") == "db":
        from app.services.agents.workflow import _db_schema

        return _db_schema(source)
    from app.services.agents.data_detective import DataDetective

    return DataDetective(data_dir=str(data_dir), llm=None).get_schema(
        str(source.get("path") or source.get("name"))
    )


def run_spec(spec: dict, source: dict, chartist: Any, data_dir: str, executor: Any = None) -> dict[str, Any]:
    from app.services.agents.workflow import run_chart_code
    from app.utils.executor import SafeExecutor

    context = context_for(source, data_dir)
    if "error" in context:
        return {
            "code": "",
            "execution_result": {},
            "error": f"Could not read {source.get('name')}: {context['error']}",
            "data_context": {},
        }
    kind = fallback_kind(spec["chart"])
    code = chartist.generate_code(
        user_query=spec["question"],
        task_plan={"visualization_type": kind},
        data_context=context,
        spec=spec,
    )
    outcome = run_chart_code(context, code, kind, chartist, executor or SafeExecutor())
    return {
        "code": outcome.get("code_run") or code,
        "execution_result": outcome.get("execution_result") or {},
        "error": outcome.get("error") or "",
        "data_context": context,
    }
