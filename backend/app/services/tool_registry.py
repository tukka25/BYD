from __future__ import annotations

from typing import List

from langchain_core.tools import BaseTool

from app.services.tools.langgraph_tools import (
    build_dataframe_load_plan,
    list_sources,
    read_source_headers,
    verify_source_matches_query,
)


def build_tool_registry() -> List[BaseTool]:
    """Central registry for DataDetective LangGraph tool-calling tools."""
    return [
        list_sources,
        read_source_headers,
        verify_source_matches_query,
        build_dataframe_load_plan,
    ]
