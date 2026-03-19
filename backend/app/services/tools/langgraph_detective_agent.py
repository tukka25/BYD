from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field, ValidationError
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from app.services.tools.langgraph_tools import get_detective_tools


SYSTEM_PROMPT = """You are DataDetective, a strict tool-calling agent.

Process (you MUST call tools before finalizing):
Case 1: selected_source provided
1) Call list_sources with the same file path as provided (absolute / relative).
2) Verify selected_source exists in available sources (from the available sources dict where will be provided to you).
3) Call read_source_headers for selected_source and ensure it has columns/data (call it with the same file path as provided (absolute / relative)).
4) Optionally call verify_source_matches_query for confidence.

Case 2: filename appears in user query
1) Call list_sources.
2) Confirm filename exists in returned sources (do not assume).
3) Call read_source_headers for that file.
4) Call verify_source_matches_query for confidence and required fields extraction.

Case 3: no selected_source and no explicit filename
1) Call list_sources.
2) Call read_source_headers for plausible sources.
3) Call verify_source_matches_query for at least top candidates.
4) Choose the most relevant source based on tool evidence.

Hard rules:
- Never finalize without calling at least two tools.
- chosen_source must be from listed sources.
- If chosen source has no columns or read error, lower confidence and explain.

Output:
Return only JSON with keys:
- chosen_source: string
- confidence: number (0..1)
- checked_sources: string[]
- rationale: string
- required_fields_for_next_step: string[]
""".strip()

DATAFRAME_BUILDER_PROMPT = """You are DataFrameBuilder, a strict tool-calling agent.

Goal:
Prepare a dataframe loading plan that can be consumed by the Plotly visualization agent.

Inputs you receive:
- chosen_source
- required_fields_for_next_step
- query (user goal + plan context)

Mandatory tool sequence:
1) Call read_source_headers(chosen_source) first.
2) Analyze headers/sample and map required_fields_for_next_step to real columns.
3) Call build_dataframe_load_plan(chosen_source, required_fields, sample_rows).
4) Use tool outputs only; do not invent columns.

Behavior requirements:
- If chosen_source cannot be read, return low confidence and clear rationale.
- If some fields are missing, keep best possible selected columns and list missing_fields.
- For DB source: prefer sql_query in output.
- For CSV/Excel source: prefer pandas_code in output.
- Keep output concise and machine-friendly for the next agent.

Output JSON keys (strict):
- chosen_source: string
- dataframe_schema: object<string, string> (column -> dtype)
- selected_columns: string[]
- missing_fields: string[]
- load_type: "sql" | "csv" | "excel" | "unknown"
- df_query_or_code: string (SQL query or pandas loading code)
- plotly_ready_spec: object with keys:
  - x
  - y
  - color
  - group_by
  - aggregation
  - chart_hint
- confidence: number (0..1)
- rationale: string
""".strip()


class DetectiveDecision(BaseModel):
    chosen_source: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    checked_sources: List[str] = Field(default_factory=list)
    rationale: str = Field(default="")
    required_fields_for_next_step: List[str] = Field(default_factory=list)


class DataFrameBuildDecision(BaseModel):
    chosen_source: str = Field(default="")
    dataframe_schema: Dict[str, str] = Field(default_factory=dict)
    selected_columns: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    df_query_or_code: str = Field(default="")
    load_type: str = Field(default="")
    plotly_ready_spec: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = Field(default="")


class Color:
    RESET = "\033[0m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"


class ColoredDetectiveCallback(BaseCallbackHandler):
    """Color logs for AI and tool events."""

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[BaseMessage]], **kwargs: Any) -> None:
        model_name = serialized.get("name") or serialized.get("id", ["chat_model"])[-1]
        print(f"{Color.BLUE}[AI request] model={model_name} prompts={len(messages)}{Color.RESET}")

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        print(f"{Color.BLUE}[AI response] completed{Color.RESET}")

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        tool_name = serialized.get("name", "unknown_tool")
        print(f"{Color.YELLOW}[Tool call] {tool_name} args={input_str}{Color.RESET}")

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        preview = output[:240] if isinstance(output, str) else str(output)[:240]
        print(f"{Color.GREEN}[Tool result] {preview}{Color.RESET}")

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        print(f"{Color.RED}[Tool error] {error}{Color.RESET}")


def _coerce_str_list(values: Any) -> List[str]:
    """
    Convert mixed LLM outputs into stable list[str].
    Handles cases like:
    - ["file.csv", "db:sales"]
    - [{"source": "file.csv"}, {"name": "sales.csv"}]
    - [{"path": "/app/uploads/file.csv"}]
    """
    if not isinstance(values, list):
        return []

    out: List[str] = []
    for item in values:
        if isinstance(item, str):
            v = item.strip()
            if v:
                out.append(v)
            continue
        if isinstance(item, dict):
            for key in ("source", "name", "path", "id"):
                raw = item.get(key)
                if isinstance(raw, str) and raw.strip():
                    out.append(raw.strip())
                    break
            continue
        raw = str(item).strip()
        if raw:
            out.append(raw)

    # Deduplicate preserving order
    return list(dict.fromkeys(out))


def _print_tool_trace_from_messages(messages: List[BaseMessage]) -> None:
    """
    Guaranteed fallback logging: print tool calls/results from final message list.
    Useful when callback hooks are not emitted by a specific stack/version.
    """
    for msg in messages:
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            for call in tool_calls:
                name = call.get("name", "unknown_tool")
                args = call.get("args", {})
                print(f"{Color.YELLOW}[Tool call(trace)] {name} args={args}{Color.RESET}")

        if msg.__class__.__name__ == "ToolMessage":
            tool_name = getattr(msg, "name", "") or "tool_result"
            content = str(getattr(msg, "content", ""))
            preview = content[:240]
            print(f"{Color.GREEN}[Tool result(trace)] {tool_name}: {preview}{Color.RESET}")


def _has_tool_activity(messages: List[BaseMessage]) -> bool:
    for msg in messages:
        if getattr(msg, "tool_calls", None):
            return True
        if msg.__class__.__name__ == "ToolMessage":
            return True
    return False


def _extract_json_payload(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except Exception:
            return {}


def _extract_last_message_content(run_result: Dict[str, Any]) -> str:
    messages = run_result.get("messages", [])
    if not messages:
        return ""
    return str(getattr(messages[-1], "content", "")).strip()


def validate_detective_decision(run_result: Dict[str, Any]) -> DetectiveDecision:
    payload = _extract_json_payload(_extract_last_message_content(run_result))
    try:
        return DetectiveDecision(**payload)
    except ValidationError:
        return DetectiveDecision(
            chosen_source=str(payload.get("chosen_source", "")),
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            checked_sources=_coerce_str_list(payload.get("checked_sources", [])),
            rationale=str(payload.get("rationale", "invalid_or_partial_schema_from_agent")),
            required_fields_for_next_step=_coerce_str_list(
                payload.get("required_fields_for_next_step", [])
            ),
        )


def validate_dataframe_build_decision(run_result: Dict[str, Any]) -> DataFrameBuildDecision:
    payload = _extract_json_payload(_extract_last_message_content(run_result))
    try:
        return DataFrameBuildDecision(**payload)
    except ValidationError:
        return DataFrameBuildDecision(
            chosen_source=str(payload.get("chosen_source", "")),
            dataframe_schema=dict(payload.get("dataframe_schema", {}) or {}),
            selected_columns=_coerce_str_list(payload.get("selected_columns", [])),
            missing_fields=_coerce_str_list(payload.get("missing_fields", [])),
            df_query_or_code=str(payload.get("df_query_or_code", "")),
            load_type=str(payload.get("load_type", "")),
            plotly_ready_spec=dict(payload.get("plotly_ready_spec", {}) or {}),
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            rationale=str(payload.get("rationale", "invalid_or_partial_schema_from_agent")),
        )


def build_detective_agent(
    llm,
    data_dir: str,
    db_url: str = "",
    checkpointer: Optional[MemorySaver] = None,
):
    """
    Build a ReAct agent with structured tools and memory checkpointer.
    Best-practice: bind infra context (data_dir/db_url) at build time.
    """
    tools = get_detective_tools(data_dir=data_dir, db_url=db_url)
    if checkpointer is None:
        checkpointer = MemorySaver()
    model_for_agent = llm
    if hasattr(llm, "bind_tools"):
        try:
            model_for_agent = llm.bind_tools(tools, tool_choice="any")
        except Exception:
            model_for_agent = llm

    agent = create_react_agent(
        model=model_for_agent,
        tools=tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )
    setattr(agent, "_registered_tools", tools)
    return agent


def build_dataframe_builder_agent(
    llm,
    data_dir: str,
    db_url: str = "",
    checkpointer: Optional[MemorySaver] = None,
):
    """Build a second ReAct agent that outputs dataframe generation plan/query."""
    tools = get_detective_tools(data_dir=data_dir, db_url=db_url)
    if checkpointer is None:
        checkpointer = MemorySaver()
    model_for_agent = llm
    if hasattr(llm, "bind_tools"):
        try:
            model_for_agent = llm.bind_tools(tools, tool_choice="any")
        except Exception:
            model_for_agent = llm
    agent = create_react_agent(
        model=model_for_agent,
        tools=tools,
        prompt=DATAFRAME_BUILDER_PROMPT,
        checkpointer=checkpointer,
    )
    setattr(agent, "_registered_tools", tools)
    return agent


def _print_registered_tools(agent: Any, stage_name: str) -> None:
    tools = getattr(agent, "_registered_tools", []) or []
    print(f"{Color.BLUE}[{stage_name}] Tools sent to AI ({len(tools)} tools):{Color.RESET}")
    for tool in tools:
        name = getattr(tool, "name", "unknown_tool")
        description = getattr(tool, "description", "") or ""
        args_schema = getattr(tool, "args_schema", None)
        schema_name = getattr(args_schema, "__name__", str(args_schema)) if args_schema else "None"
        print(f"{Color.YELLOW}- {name}{Color.RESET}")
        print(f"  description: {description}")
        print(f"  args_schema: {schema_name}")


def run_detective_agent(
    agent,
    query: str,
    selected_source: str = "",
    thread_id: str = "detective-default",
    callbacks: Optional[list[Any]] = None,
    enable_colored_logs: bool = True,
) -> Dict[str, Any]:
    """Invoke detective agent with thread-scoped memory, callbacks, and validated schema."""
    user_input = (
        f"selected_source={selected_source}\n"
        f"query={query}\n"
        "Use tools to identify the best datasource."
    )
    config: Dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    all_callbacks: List[Any] = []
    if enable_colored_logs:
        all_callbacks.append(ColoredDetectiveCallback())
    if callbacks:
        all_callbacks.extend(callbacks)
    if all_callbacks:
        config["callbacks"] = all_callbacks

    _print_registered_tools(agent, "detective_source")
    result = agent.invoke({"messages": [("user", user_input)]}, config=config)
    if not _has_tool_activity(result.get("messages", [])):
        print(f"{Color.RED}[Tool warning] No tool activity detected. Retrying with mandatory tool instruction.{Color.RESET}")
        forced_input = (
            f"{user_input}\n"
            "MANDATORY: First call `list_sources`, then call either `read_source_headers` "
            "or `verify_source_matches_query` before final JSON."
        )
        result = agent.invoke({"messages": [("user", forced_input)]}, config=config)
    if enable_colored_logs:
        _print_tool_trace_from_messages(result.get("messages", []))
    decision = validate_detective_decision(result)
    result["structured_output"] = decision.model_dump()
    return result


def run_dataframe_builder_agent(
    agent,
    query: str,
    chosen_source: str,
    required_fields_for_next_step: List[str],
    thread_id: str = "detective-dataframe-builder-default",
    callbacks: Optional[list[Any]] = None,
    enable_colored_logs: bool = True,
) -> Dict[str, Any]:
    """Invoke dataframe-builder agent and attach validated structured output."""
    user_input = (
        f"chosen_source={chosen_source}\n"
        f"required_fields_for_next_step={required_fields_for_next_step}\n"
        f"query={query}\n"
        "Use tools to build dataframe schema and query/code plan."
    )
    config: Dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    all_callbacks: List[Any] = []
    if enable_colored_logs:
        all_callbacks.append(ColoredDetectiveCallback())
    if callbacks:
        all_callbacks.extend(callbacks)
    if all_callbacks:
        config["callbacks"] = all_callbacks

    _print_registered_tools(agent, "dataframe_builder")
    result = agent.invoke({"messages": [("user", user_input)]}, config=config)
    if not _has_tool_activity(result.get("messages", [])):
        print(f"{Color.RED}[Tool warning] No tool activity detected. Retrying with mandatory tool instruction.{Color.RESET}")
        forced_input = (
            f"{user_input}\n"
            "MANDATORY: Call `read_source_headers` for chosen_source and then "
            "`build_dataframe_load_plan` before final JSON."
        )
        result = agent.invoke({"messages": [("user", forced_input)]}, config=config)
    if enable_colored_logs:
        _print_tool_trace_from_messages(result.get("messages", []))
    decision = validate_dataframe_build_decision(result)
    result["structured_output"] = decision.model_dump()
    return result
