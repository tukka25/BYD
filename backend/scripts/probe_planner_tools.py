"""Probe the model server for what PLANNER_TOOLS=planner relies on that the
tests' fake models cannot show. Host-side, against `make serve-model`;
it saves nothing and draws nothing.

    cd backend && .venv/bin/python scripts/probe_planner_tools.py

0. A plain planner call (trained prompt, no tool text) gives the draft.
1. The checking turn: with the tools offered and its own system prompt, does it
   call any, and does preview_chart's `plans` arrive as a list?
2. After that call and its tool results, does a plain call (no tools offered)
   still answer? If it raises, planning.py answers again without the tool
   turns, at the cost of one failed call per check.
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
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage  # noqa: E402

from app.services.agents.data_tools import PLANNER_TOOL_NAMES, ToolBox  # noqa: E402
from app.services.agents.planning_contract import (  # noqa: E402
    CHECKER_SYSTEM_PROMPT, CHECKER_USER_TEMPLATE, PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE, extract_json,
    render_directions)
from app.services.agents.profiler import profile_table, render_profiles  # noqa: E402
from app.services.llm import get_llm  # noqa: E402

TABLE = "web_traffic.csv"
frame = pd.read_csv(BACKEND / "uploads" / TABLE)
profile = profile_table(TABLE, frame)
direction = [{"question": "How does the bounce rate move through the day?", "why": "asked", "table": TABLE,
              "columns": ["hourOfDay", "bounceRatePct"]}]
user = PLANNER_USER_TEMPLATE.format(profiles=render_profiles([profile]), directions=render_directions(direction))
box = ToolBox({TABLE: {"type": "file", "name": TABLE}}, str(BACKEND / "uploads"),
              loader=lambda source, data_dir: frame, tools=PLANNER_TOOL_NAMES, kinds={TABLE: profile.kinds()})
planner = get_llm("spec_planner")


def prompt_tokens(message) -> object:
    """The server's own prompt token count, when it reports usage."""
    usage = (getattr(message, "response_metadata", None) or {}).get("token_usage") or {}
    return usage.get("prompt_tokens", "not reported")


draft_reply = planner.invoke([SystemMessage(content=PLANNER_SYSTEM_PROMPT), HumanMessage(content=user)])
draft = str(getattr(draft_reply, "content", "") or "")
payload = extract_json(draft)
plans = payload.get("charts", []) if isinstance(payload, dict) else []
print("0. draft:", [(p.get("chart"), p.get("x"), p.get("y"), p.get("agg")) for p in plans] or f"no plan JSON: {draft[:200]!r}")
print("   prompt tokens (server):", prompt_tokens(draft_reply))

messages = [SystemMessage(content=CHECKER_SYSTEM_PROMPT),
            HumanMessage(content=CHECKER_USER_TEMPLATE.format(context=render_profiles([profile]), drafts=draft))]
reply = planner.bind_tools(box.specs).invoke(messages)
asked = list(getattr(reply, "tool_calls", None) or [])
print("1. tool calls:", [call.get("name") for call in asked] or "none")
print("   prompt tokens (server):", prompt_tokens(reply))
for call in asked:
    if call.get("name") == "preview_chart":
        print("   preview_chart plans arrived as", type((call.get("args") or {}).get("plans")).__name__)

turns = messages + [reply] if asked else list(messages)
for i, call in enumerate(asked):
    turns.append(ToolMessage(content=box.call(call.get("name"), call.get("args") or {}, compact=True),
                             tool_call_id=call.get("id") or f"probe-{i}"))
try:
    answer = planner.invoke(turns)
    print("2. plain call after tool turns:", str(getattr(answer, "content", "") or "")[:200])
    print("   prompt tokens (server):", prompt_tokens(answer))
except Exception as exc:  # noqa: BLE001 - this is what the probe is for
    print("2. plain call after tool turns: raised:", exc)
