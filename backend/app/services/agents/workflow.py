"""The planner -> detective -> chartist -> executor graph.

Changes from the original, all of them things that bit:

* **The error path did not terminate.** The graph was a straight line, so when
  the detective could not resolve a source it returned `{"error": ...}` and the
  graph carried on regardless: the chartist produced fallback code against an
  empty schema, then the executor did `data_context["filename"]` and raised
  KeyError. A failed lookup crashed the request instead of reporting itself.
  There are conditional edges now, and each node short-circuits on an error
  already in state.
* **Models and the graph were built at import time**, so importing this module
  opened three chat clients. That made the module untestable and meant the
  container had to be restarted to pick up a config change. Both are lazy now.
* **`data_dir` was `Path("/app/uploads")` with a CWD-relative fallback**, which
  ignored `UPLOAD_DIR` entirely and resolved differently depending on where
  uvicorn was started. It comes from settings.
* **Debug `print()` calls** interleaved with real logging, including one that
  dumped the whole generated program to stdout.
* The chartist now receives the user's question, which is what its fine-tune was
  trained on. See `chartist._task_description`.
* **A hardcoded chart stood in whenever the model's code failed** (since March,
  removed 2026-11-23). It picked columns by name and plotted every row, so on a
  32,833-row table it drew one bar per row of the wrong column under the planned
  title and froze the report. Failed code now goes back to the model with the
  error (`run_on_frame`), and a chart it cannot fix is reported as failed.
"""
from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, TypedDict

import pandas as pd
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph

from app.core.config import get_settings
from app.services.agents.chartist import ChartistAgent, ChartistUnavailable
from app.services.agents.chartist_contract import figure_problems, problems_with
from app.services import db_sources
from app.services.agents.data_detective import DataDetective
from app.services.agents.planner import PlannerAgent
from app.services.llm import get_llm
from app.utils.executor import SafeExecutor
from app.utils.figure_json import decode_typed_arrays

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    user_query: str
    selected_source: str
    available_sources: List[Dict[str, Any]]
    messages: Sequence[BaseMessage]
    plan: Dict[str, Any]
    source_decision: Dict[str, Any]
    data_context: Dict[str, Any]
    code: str
    chart_prompt: Dict[str, Any]
    execution_result: Dict[str, Any]
    error: str


def _data_dir() -> Path:
    """Where uploads live, from settings rather than a hardcoded container path."""
    path = get_settings().upload_dir_path
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def _agents() -> tuple[PlannerAgent, DataDetective, ChartistAgent, SafeExecutor]:
    """Build the agents once, on first use rather than on import."""
    return (
        PlannerAgent(get_llm("planner")),
        DataDetective(data_dir=str(_data_dir()), llm=get_llm("detective")),
        ChartistAgent(get_llm("chartist")),
        SafeExecutor(),
    )


# --- nodes ---------------------------------------------------------------


def planning_node(state: AgentState) -> Dict[str, Any]:
    planner, _, _, _ = _agents()
    query = state.get("user_query") or (state["messages"][-1].content if state.get("messages") else "")
    started = time.perf_counter()
    plan = planner.create_plan(query)
    if hasattr(plan, "model_dump"):
        plan = plan.model_dump()
    elif hasattr(plan, "dict"):
        plan = plan.dict()
    logger.info(
        "[workflow/planner] %.2fs chart=%s via=%s",
        time.perf_counter() - started,
        plan.get("visualization_type"),
        plan.get("chart_type_source"),
    )
    return {
        "plan": plan,
        "messages": [AIMessage(content=f"Chart type: {plan.get('visualization_type')}")],
    }


def _db_schema(selected: Dict[str, Any]) -> Dict[str, Any]:
    """Schema for a database table, in the same shape a file returns."""
    from app.core.database import SessionLocal
    from app.models.data_source import DataSource

    session = SessionLocal()
    try:
        source = (
            session.query(DataSource).filter(DataSource.id == selected.get("source_id")).first()
        )
        if source is None:
            return {"error": "that database connection no longer exists"}
        if selected.get("join"):
            schema = db_sources.joined_schema(source, db_sources.Link.from_dict(selected["join"]))
        else:
            schema = db_sources.schema_of(source, str(selected.get("table")))
        if "error" not in schema:
            # Carried so the executor can load the same table without
            # resolving the source a second time.
            schema["source_id"] = source.id
            schema["table"] = selected.get("table")
            if selected.get("join"):
                schema["join"] = selected["join"]
        return schema
    finally:
        session.close()


def data_sourcing_node(state: AgentState) -> Dict[str, Any]:
    _, detective, _, _ = _agents()
    query = state.get("user_query", "")
    started = time.perf_counter()

    decision = detective.detect_source(
        query=query,
        plan=state.get("plan", {}),
        selected_source=state.get("selected_source", "") or "",
        available_sources=state.get("available_sources") or None,
    )
    selected = decision.get("selected")
    if not selected:
        logger.warning("[workflow/detective] unresolved: %s", decision.get("reason"))
        return {
            "error": (
                f"Could not resolve a data source ({decision.get('reason')}). "
                f"Upload a file or select one explicitly."
            ),
            "source_decision": decision,
            "messages": [AIMessage(content="Could not resolve the data source.")],
        }

    if selected.get("type") == "db":
        schema = _db_schema(selected)
    else:
        schema = detective.get_schema(selected.get("path") or selected.get("name"))
    if "error" in schema:
        logger.error("[workflow/detective] schema error: %s", schema["error"])
        return {
            "error": f"Could not read {selected.get('name')}: {schema['error']}",
            "source_decision": decision,
            "messages": [AIMessage(content=f"Error reading schema: {schema['error']}")],
        }

    logger.info(
        "[workflow/detective] %.2fs file=%s via=%s confidence=%.2f",
        time.perf_counter() - started,
        schema.get("filename"),
        decision.get("reason"),
        float(decision.get("confidence", 0.0)),
    )
    return {
        "source_decision": decision,
        "data_context": schema,
        "messages": [AIMessage(content=f"Using {schema.get('filename')}")],
    }


def coding_node(state: AgentState) -> Dict[str, Any]:
    _, _, chartist, _ = _agents()
    data_context = state.get("data_context") or {}
    if not data_context.get("columns"):
        return {"error": "No schema available to chart against."}

    dataframe_plan = (state.get("source_decision") or {}).get("dataframe_plan") or {}
    started = time.perf_counter()
    variables = chartist.prompt_variables(
        user_query=state.get("user_query", ""),
        task_plan=state.get("plan") or {},
        data_context=data_context,
        dataframe_plan=dataframe_plan if isinstance(dataframe_plan, dict) else {},
    )
    try:
        code = chartist.write(variables)
    except ChartistUnavailable as exc:
        return {"error": f"The chart model could not be reached: {exc}"}
    logger.info(
        "[workflow/chartist] %.2fs code_chars=%d",
        time.perf_counter() - started,
        len(code),
    )
    logger.debug("[workflow/chartist] code:\n%s", code)
    return {"code": code, "chart_prompt": variables, "messages": [AIMessage(content="Generated chart code.")]}


def execution_node(state: AgentState) -> Dict[str, Any]:
    _, _, chartist, executor = _agents()
    variables = state.get("chart_prompt") or {}
    repair = (lambda code, problem: chartist.write(variables, code, problem)) if variables else None
    outcome = run_chart_code(state.get("data_context") or {}, state.get("code") or "", executor, repair)
    if outcome.get("code_run"):
        # The code that ran, which after a repair is the model's fix, not its first answer.
        outcome["code"] = outcome["code_run"]
    return outcome


# Failed code goes back to the model this many times before the chart is
# reported as failed: its first answer and two fixes, like the planner's three
# tries. There is no hardcoded chart behind this, by design.
MAX_REPAIRS = 2

# How a caller lets the model fix its own code: (code, problem) -> its new code.
Repair = Callable[[str, str], str]


def run_chart_code(
    data_context: Dict[str, Any],
    code: str,
    executor: SafeExecutor,
    repair: Optional[Repair] = None,
) -> Dict[str, Any]:
    """Run the model's chart code against the data it was written for.

    Shared by the question workflow and the dashboard's planned charts, so both
    send failed code back to the model the same way (`run_on_frame`).
    """
    if data_context.get("source_id") and data_context.get("join"):
        try:
            df = db_sources.load_joined_by_id(
                str(data_context["source_id"]), db_sources.Link.from_dict(data_context["join"])
            )
        except Exception as exc:
            logger.error("[workflow/executor] joined table load failed: %s", exc)
            return {"error": f"Failed to read that joined table: {exc}"}
        return run_on_frame(executor, code, df, repair)

    if data_context.get("source_id") and data_context.get("table"):
        try:
            df = db_sources.load_table_by_id(
                str(data_context["source_id"]), str(data_context["table"])
            )
        except Exception as exc:
            logger.error("[workflow/executor] database load failed: %s", exc)
            return {"error": f"Failed to read that table: {exc}"}
        return run_on_frame(executor, code, df, repair)

    filepath = data_context.get("filepath")
    if not filepath:
        filename = data_context.get("filename")
        if not filename:
            return {"error": "No data file to execute against."}
        filepath = str(_data_dir() / filename)

    try:
        if filepath.endswith(".csv"):
            df = pd.read_csv(filepath)
        elif filepath.endswith((".xlsx", ".xls")):
            df = pd.read_excel(filepath)
        else:
            return {"error": f"Unsupported file format: {filepath}"}
    except Exception as exc:
        logger.error("[workflow/executor] load failed: %s", exc)
        return {"error": f"Failed to load data: {exc}"}

    return run_on_frame(executor, code, df, repair)


def _run_problem(result: Dict[str, Any]) -> str:
    """Why a run failed, as the model will read it: Plotly's or pandas' own words."""
    error = str(result.get("error") or "it produced no figure").strip()
    if error == "Output is not valid JSON":
        printed = str(result.get("output") or "").strip()[:200]
        return f"it printed something that is not the figure's JSON: {printed!r}"
    return f"it failed when it ran: {error[:1500]}"


def run_on_frame(
    executor: Any,
    code: str,
    df: "pd.DataFrame",
    repair: Optional[Repair] = None,
    max_repairs: int = MAX_REPAIRS,
) -> Dict[str, Any]:
    """Check and run the model's code; on any failure send the problem back to
    the model for a fix, at most `max_repairs` times, then report the failure.

    A failure is code that breaks the contract, code that does not run, or a
    figure that breaks it (`figure_problems`: a line whose x repeats runs back
    and forth, or bars that repeat a category stack raw rows). `repair_reasons`
    lists the problem behind each fix asked for.

    The chart is always the model's own code. There is no deterministic
    stand-in and no code-side patching: a hardcoded backup once drew 32,833 bars
    of the wrong column under the planned title, froze the report it sat in and
    hid that the model had failed. A chart the model cannot fix is reported.
    """
    started = time.perf_counter()
    repairs = 0
    reasons: List[str] = []
    result: Dict[str, Any] = {}
    while True:
        problems = problems_with(code)
        if problems:
            problem = "; ".join(problems)
        else:
            result = executor.execute(code, df)
            drawn = figure_problems(decode_typed_arrays(result.get("figure") or {})) if result.get("success") else []
            if result.get("success") and not drawn:
                logger.info(
                    "[workflow/executor] success in %.2fs after %d fix(es)",
                    time.perf_counter() - started,
                    repairs,
                )
                return {
                    "execution_result": result,
                    "code_run": code,
                    "repairs": repairs,
                    "repair_reasons": reasons,
                    "messages": [AIMessage(content="Chart rendered.")],
                }
            if drawn:
                problem = "; ".join(drawn)
                # It ran, but what it drew breaks the contract: no caller may take it for a chart.
                result = {**result, "success": False, "figure": None, "error": problem}
            else:
                problem = _run_problem(result)
        if repair is None or repairs >= max_repairs:
            break
        repairs += 1
        reasons.append(problem)
        logger.info(
            "[workflow/executor] asking the model to fix its code (%d of %d): %s",
            repairs,
            max_repairs,
            problem[:300],
        )
        try:
            code = repair(code, problem)
        except ChartistUnavailable as exc:
            problem = f"the model could not be asked to fix it: {exc}"
            break

    logger.error("[workflow/executor] the model's code failed after %d fix(es): %s", repairs, problem[:300])
    return {
        "error": f"The model could not draw this chart: {problem}",
        "execution_result": result,
        "code_run": code,
        "repairs": repairs,
        "repair_reasons": reasons,
        "messages": [AIMessage(content=f"Chart failed: {problem}")],
    }


def _continue_or_stop(state: AgentState) -> str:
    """Route to END as soon as a node reports an error.

    Without this the graph ran every node regardless, so a failed source lookup
    became a KeyError three nodes later instead of the message it already had.
    """
    return "stop" if state.get("error") else "continue"


@lru_cache(maxsize=1)
def _graph():
    builder = StateGraph(AgentState)
    builder.add_node("planner", planning_node)
    builder.add_node("detective", data_sourcing_node)
    builder.add_node("chartist", coding_node)
    builder.add_node("executor", execution_node)

    builder.set_entry_point("planner")
    builder.add_conditional_edges("planner", _continue_or_stop, {"continue": "detective", "stop": END})
    builder.add_conditional_edges("detective", _continue_or_stop, {"continue": "chartist", "stop": END})
    builder.add_conditional_edges("chartist", _continue_or_stop, {"continue": "executor", "stop": END})
    builder.add_edge("executor", END)
    return builder.compile()


def run_agent_workflow(
    query: str,
    selected_source: str = "",
    available_sources: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run the full workflow for one question.

    Honours the caller's `selected_source` and `available_sources`. This used to
    discard both and substitute a hardcoded
    `/app/uploads/abu_dhabi_population_density.csv`, so every request charted
    that one file whatever the user picked.
    """
    sources = available_sources or []
    logger.info(
        "[workflow] start query=%r selected=%r candidates=%d",
        (query or "")[:120],
        selected_source,
        len(sources),
    )
    initial_state: AgentState = {
        "user_query": query,
        "selected_source": selected_source,
        "available_sources": sources,
        "messages": [HumanMessage(content=query)],
        "plan": {},
        "source_decision": {},
        "data_context": {},
        "code": "",
        "chart_prompt": {},
        "execution_result": {},
        "error": "",
    }
    started = time.perf_counter()
    result = _graph().invoke(initial_state)
    logger.info(
        "[workflow] done in %.2fs error=%s",
        time.perf_counter() - started,
        result.get("error") or None,
    )
    return result
