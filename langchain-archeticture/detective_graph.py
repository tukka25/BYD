from __future__ import annotations

from typing import Any, Dict

from langgraph.prebuilt import create_react_agent

from .registry import build_detective_tools


SYSTEM_INSTRUCTION = """
You are DataDetective Agent.
Decision policy:
1) If selected_source is provided, inspect that source first.
2) Else if explicit filename is mentioned in the query, inspect it.
3) Else use tools to list sources, read headers, and verify relevance against the query.
Always call tools before making a final source decision.
Return concise structured JSON in your final answer with:
- chosen_source
- confidence
- checked_sources
- rationale
""".strip()


def build_detective_agent(llm, data_dir: str, db_url: str = ""):
    """Create LangGraph ReAct agent with detective tools."""
    tools = build_detective_tools(data_dir=data_dir, db_url=db_url)
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=SYSTEM_INSTRUCTION,
    )


def run_detective(agent, query: str, selected_source: str = "", data_dir: str = "backend/uploads", db_url: str = "") -> Dict[str, Any]:
    """Invoke detective agent with context for tool calls."""
    user_msg = (
        f"selected_source={selected_source}\n"
        f"data_dir={data_dir}\n"
        f"db_url={db_url}\n"
        f"query={query}\n"
        "Use tools and then decide the best datasource."
    )
    return agent.invoke({"messages": [("user", user_msg)]})
