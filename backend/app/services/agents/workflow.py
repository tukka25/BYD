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
"""
from __future__ import annotations

import logging
import os.path
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, TypedDict

import pandas as pd
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph

from app.core.config import get_settings
from app.services.agents.chartist import ChartistAgent
from app.services import db_sources
from app.services.agents.data_detective import DataDetective
from app.services.agents.planner import PlannerAgent
from app.services.llm import get_llm
from app.utils.executor import SafeExecutor

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
        schema = db_sources.schema_of(source, str(selected.get("table")))
        if "error" not in schema:
            # Carried so the executor can load the same table without
            # resolving the source a second time.
            schema["source_id"] = source.id
            schema["table"] = selected.get("table")
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
    code = chartist.generate_code(
        user_query=state.get("user_query", ""),
        task_plan=state.get("plan") or {},
        data_context=data_context,
        dataframe_plan=dataframe_plan if isinstance(dataframe_plan, dict) else {},
    )
    logger.info(
        "[workflow/chartist] %.2fs code_chars=%d",
        time.perf_counter() - started,
        len(code),
    )
    logger.debug("[workflow/chartist] code:\n%s", code)
    return {"code": code, "messages": [AIMessage(content="Generated chart code.")]}


def execution_node(state: AgentState) -> Dict[str, Any]:
    _, _, chartist, executor = _agents()
    data_context = state.get("data_context") or {}
    code = state.get("code") or ""
    if not code:
        return {"error": "No chart code was generated."}

    viz = (state.get("plan") or {}).get("visualization_type", "bar")
    fallback_code = chartist._fallback_plotly_code(data_context, viz)

    if data_context.get("source_id") and data_context.get("table"):
        started = time.perf_counter()
        try:
            df = db_sources.load_table_by_id(
                str(data_context["source_id"]), str(data_context["table"])
            )
        except Exception as exc:
            logger.error("[workflow/executor] database load failed: %s", exc)
            return {"error": f"Failed to read that table: {exc}"}
        return _run_executor(executor, code, df, started, fallback_code)

    filepath = data_context.get("filepath")
    if not filepath:
        filename = data_context.get("filename")
        if not filename:
            return {"error": "No data file to execute against."}
        filepath = str(_data_dir() / filename)

    started = time.perf_counter()
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

    return _run_executor(executor, code, df, started, fallback_code)


# Plotly names the property it rejected, which is enough to repair the code
# without guessing: the model invents `value*` keys on an indicator's number
# (`valuecolor`, `valuesize`) that carry no meaning, and dropping the one it
# named is the whole fix. Done from the error rather than from a list, so a
# newly invented name costs nothing. One retry only — if the second attempt
# fails the chart is genuinely wrong, not decorated wrong.
_INVALID_PROPERTY = re.compile(
    r"Invalid property specified for object of type [\w.]+: '([A-Za-z_]\w*)'"
)
# Plotly names the property it wanted whenever the mistake is a near miss
# ("'valueuffix' Did you mean \"suffix\"?"). Taking the suggestion keeps what
# the model meant -- the currency suffix on a KPI -- where dropping the
# property throws it away and silently changes the chart.
_SUGGESTION = re.compile(r'Did you mean ["\']([A-Za-z_]\w*)["\']')


def _has_key(code: str, name: str) -> bool:
    """`'name':` or `name=` -- Plotly code is written both ways."""
    return bool(
        re.search(rf"['\"]{re.escape(name)}['\"]\s*:", code)
        or re.search(rf"(?<![\w.]){re.escape(name)}\s*=", code)
    )


def _plausible_rename(wrong: str, right: str) -> bool:
    """Is Plotly's suggestion a near miss, or just the nearest string?

    It suggested "font" for a misplaced `value`, which shares not one letter
    with it; taking that would have set the number's font to a population
    count. A real near miss shares a head or a tail -- ticklabelformat and
    tickformat share "tick", valueuffix and suffix share "uffix".
    """
    a, b = wrong.lower(), right.lower()
    if a in b or b in a:
        return True
    prefix = len(os.path.commonprefix([a, b]))
    suffix = len(os.path.commonprefix([a[::-1], b[::-1]]))
    return prefix >= 3 or suffix >= 3


def _rename_property(code: str, wrong: str, right: str) -> str:
    renamed = re.sub(
        rf"(['\"]){re.escape(wrong)}\1(\s*:)",
        lambda m: f"{m.group(1)}{right}{m.group(1)}{m.group(2)}",
        code,
    )
    # `update_xaxes(ticklabelformat=...)` is the other half of the problem.
    return re.sub(
        rf"(?<![\w.]){re.escape(wrong)}(\s*=)",
        lambda m: f"{right}{m.group(1)}",
        renamed,
    )


def _drop_property(code: str, prop: str) -> str:
    """Remove `'prop': <value>` from a dict literal, whatever the value is.

    Bracket- and quote-aware on purpose: a first attempt matched the value as
    "everything up to a comma or brace", which cut `{'size': 48}` in half and
    turned a bad property into a syntax error.
    """
    key = re.compile(rf"['\"]{re.escape(prop)}['\"]\s*:\s*")
    out = code
    while True:
        match = key.search(out)
        if not match:
            return out

        i = match.end()
        depth = 0
        quote = ""
        while i < len(out):
            ch = out[i]
            if quote:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = ""
            elif ch in "\"'":
                quote = ch
            elif ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:
                    break
                depth -= 1
            elif ch == "," and depth == 0:
                break
            i += 1

        end = i
        # Take the separating comma with it, so the dict stays well formed.
        if end < len(out) and out[end] == ",":
            end += 1
        while end < len(out) and out[end] in " \t":
            end += 1
        out = out[: match.start()] + out[end:]


def _compiles(code: str) -> bool:
    """A repair that does not parse is not a repair."""
    try:
        compile(code, "<repair>", "exec")
        return True
    except SyntaxError:
        logger.info("[workflow/executor] repair did not parse, keeping the original error")
        return False


def _run_executor(
    executor: Any,
    code: str,
    df: "pd.DataFrame",
    started: float,
    fallback_code: str | None = None,
) -> Dict[str, Any]:
    """Run the generated code against `df`, whatever the data came from."""
    result = executor.execute(code, df)

    # At most two repairs, each from what Plotly actually said: take its
    # suggested spelling first, and only drop the property if there was no
    # suggestion or the rename did not help.
    for _ in range(2):
        if result.get("success"):
            break
        message = str(result.get("error") or "")
        match = _INVALID_PROPERTY.search(message)
        if not match:
            break

        wrong = match.group(1)
        suggestion = _SUGGESTION.search(message)
        target = suggestion.group(1) if suggestion else ""
        # Never rename onto a key that is already there. Plotly suggests on
        # spelling, not meaning: it answered `valuecolor` with "did you mean
        # valueformat?" next to a real `valueformat`, and the rename produced a
        # duplicate key whose junk value won -- a KPI that silently lost its
        # number format. Where the target exists, the property is dropped.
        if (
            target
            and target != wrong
            and not _has_key(code, target)
            and _plausible_rename(wrong, target)
        ):
            repaired = _rename_property(code, wrong, target)
            action = f"renaming {wrong!r} to {target!r}"
        else:
            repaired = _drop_property(code, wrong)
            action = f"dropping invented property {wrong!r}"

        if repaired == code or not _compiles(repaired):
            break

        logger.info("[workflow/executor] %s", action)
        attempt = executor.execute(repaired, df)
        if attempt.get("success"):
            code = repaired
            result = attempt
            break
        # The rename did not take; the next pass drops whatever it now names.
        code = repaired
        result = attempt
    if result.get("success"):
        logger.info("[workflow/executor] success in %.2fs", time.perf_counter() - started)
        return {
            "execution_result": result,
            "code_run": code,
            "messages": [AIMessage(content="Chart rendered.")],
        }
    # The static contract catches code that is wrong on its face. This catches
    # code that is only wrong once Plotly sees it -- a property in the wrong
    # place, say -- which otherwise reaches the user as a stack trace where a
    # chart should be. A plain chart, marked as the fallback it is, beats that.
    if fallback_code and fallback_code != code:
        logger.info("[workflow/executor] runtime failure, using the deterministic chart")
        attempt = executor.execute(fallback_code, df)
        if attempt.get("success"):
            return {
                "execution_result": attempt,
                "code_run": fallback_code,
                "messages": [AIMessage(content="Chart rendered by the fallback.")],
            }

    logger.error("[workflow/executor] failed: %s", result.get("error"))
    return {
        "error": result.get("error") or "Chart code failed to execute.",
        "execution_result": result,
        "code_run": code,
        "messages": [AIMessage(content=f"Execution failed: {result.get('error')}")],
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
