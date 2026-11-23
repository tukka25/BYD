"""Draw one chart from its plan: the chartist writes it, the runner runs it.

A plan already names the table and the columns, so the planner and the data
detective, which exist to work those out from a question, are skipped. The
code goes through the same contract check, executor and repair loop as every
other chart (`workflow.run_chart_code`): when it fails, the model is shown the
error and fixes its own code; a chart it cannot fix is reported, never redrawn
by anything else.
"""
from __future__ import annotations

from typing import Any


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
    from app.services.agents.chartist import ChartistUnavailable
    from app.services.agents.workflow import run_chart_code
    from app.utils.executor import SafeExecutor

    context = context_for(source, data_dir)
    if "error" in context:
        return {
            "code": "",
            "execution_result": {},
            "error": f"Could not read {source.get('name')}: {context['error']}",
            "data_context": context,
            "repairs": 0,
            "repair_reasons": [],
        }
    variables = chartist.prompt_variables(spec["question"], {}, context, spec=spec)
    try:
        code = chartist.write(variables)
    except ChartistUnavailable as exc:
        return {
            "code": "",
            "execution_result": {},
            "error": f"The chart model could not be reached: {exc}",
            "data_context": context,
            "repairs": 0,
            "repair_reasons": [],
        }
    outcome = run_chart_code(
        context,
        code,
        executor or SafeExecutor(),
        repair=lambda previous, problem: chartist.write(variables, previous, problem),
    )
    return {
        "code": outcome.get("code_run") or code,
        "execution_result": outcome.get("execution_result") or {},
        "error": outcome.get("error") or "",
        "data_context": context,
        "repairs": outcome.get("repairs", 0),
        "repair_reasons": outcome.get("repair_reasons", []),
    }
