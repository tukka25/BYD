"""Probe the model server for two things PLANNER_TOOLS=planner relies on that
the tests' fake models cannot show. Host-side, against `make serve-model`;
it saves nothing and draws nothing.

    cd backend && .venv/bin/python scripts/probe_planner_tools.py

1. Offered the planner's tools and asked to check its draft, does the planner
   call any, and does preview_chart's `plans` arrive as a list?
2. After a tool call and its result, does a plain call (no tools offered)
   still answer with the plan JSON? If it raises, planning.py answers again
   without the tool turns, at the cost of one failed call per tool-using try.
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("LLM_BACKEND", "mlx")
os.environ.setdefault("MLX_BASE_URL", "http://127.0.0.1:8080/v1")
os.environ.setdefault("MLX_MODEL", "default_model")

import pandas as pd  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402

from app.services.agents.data_tools import PLANNER_TOOL_NAMES, ToolBox  # noqa: E402
from app.services.agents.planning_contract import (  # noqa: E402
    PLANNER_SYSTEM_PROMPT, PLANNER_TOOLS_NOTE, PLANNER_USER_TEMPLATE, extract_json, render_directions,
    with_context)
from app.services.agents.profiler import profile_table, render_profiles  # noqa: E402
from app.services.llm import get_llm  # noqa: E402

TABLE = "web_traffic.csv"
frame = pd.read_csv(BACKEND / "uploads" / TABLE)
profile = profile_table(TABLE, frame)
direction = [{"question": "How does the bounce rate move through the day?", "why": "asked", "table": TABLE,
              "columns": ["hourOfDay", "bounceRatePct"]}]
user = with_context(PLANNER_USER_TEMPLATE.format(profiles=render_profiles([profile]),
                                                 directions=render_directions(direction)),
                    notes=(PLANNER_TOOLS_NOTE,))
box = ToolBox({TABLE: {"type": "file", "name": TABLE}}, str(BACKEND / "uploads"),
              loader=lambda source, data_dir: frame, tools=PLANNER_TOOL_NAMES, kinds={TABLE: profile.kinds()})
planner = get_llm("spec_planner")
messages = [SystemMessage(content=PLANNER_SYSTEM_PROMPT), HumanMessage(content=user)]

def prompt_tokens(message) -> object:
    """The server's own prompt token count, when it reports usage."""
    usage = (getattr(message, "response_metadata", None) or {}).get("token_usage") or {}
    return usage.get("prompt_tokens", "not reported")


reply = planner.bind_tools(box.specs).invoke(messages)
asked = list(getattr(reply, "tool_calls", None) or [])
print("1. tool calls:", [call.get("name") for call in asked] or "none")
print("   prompt tokens (server):", prompt_tokens(reply))
for call in asked:
    if call.get("name") == "preview_chart":
        print("   preview_chart plans arrived as", type((call.get("args") or {}).get("plans")).__name__)

draft = [{"chart": "line", "table": TABLE, "x": "hourOfDay", "y": "bounceRatePct", "agg": "none"}]
turns = messages + [
    AIMessage(content="", tool_calls=[{"name": "preview_chart", "args": {"plans": draft}, "id": "probe-1"}]),
    ToolMessage(content=box.call("preview_chart", {"plans": draft}, compact=True), tool_call_id="probe-1"),
]
try:
    answer = planner.invoke(turns)
    text = str(getattr(answer, "content", "") or "")
    payload = extract_json(text)
    found = isinstance(payload, dict) and "charts" in payload
    print("2. plain call after tool turns:", "JSON with charts" if found else f"no plan JSON: {text[:200]!r}")
    print("   prompt tokens (server):", prompt_tokens(answer))
except Exception as exc:  # noqa: BLE001 - this is what the probe is for
    print("2. plain call after tool turns raised:", exc)
