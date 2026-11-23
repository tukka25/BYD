"""The planner's tool step: the model checks facts about the data before it plans.

The adapter calls tools when it is asked to and not otherwise (measured
2026-11-23: offered tools with the real analyst prompt, it called none). So this
step asks explicitly, in a call of its own, and hands the planning calls only
what it found, condensed to a few lines. The tool transcript never reaches them,
and they stay in the format lora-v2 was trained on.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Generator

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.services.agents.data_tools import ToolBox, ToolCall
from app.services.agents.planning_contract import EXPLORER_SYSTEM_PROMPT, EXPLORER_USER_TEMPLATE, NO_REQUEST
from app.services.agents.profiler import TableProfile, render_profiles

logger = logging.getLogger(__name__)

FACTS_CHARS = 800  # about 200 tokens: what the facts note may add to each planning call


@dataclass
class Probe:
    """A tool call about to run, for the progress line."""

    name: str
    args: dict


@dataclass
class Findings:
    facts: list[str] = field(default_factory=list)
    calls: list[ToolCall] = field(default_factory=list)

    @property
    def note(self) -> str:
        """The facts as bullet lines, whole lines only, at most FACTS_CHARS."""
        lines: list[str] = []
        used = 0
        for fact in self.facts:
            line = f"- {fact}"
            if used + len(line) + (1 if lines else 0) > FACTS_CHARS:
                break
            used += len(line) + (1 if lines else 0)
            lines.append(line)
        return "\n".join(lines)


def discover(llm: Any, request: str, profiles: list[TableProfile], toolbox: ToolBox) -> Generator[Probe, None, Findings]:
    """Let the model call tools, at most toolbox.max_calls times; return what it found."""
    try:
        bound = llm.bind_tools(toolbox.specs)
    except Exception as exc:  # noqa: BLE001 - no tools on this backend: plan without facts
        logger.warning("[discovery] tools unavailable: %s", exc)
        return Findings()
    messages: list = [
        SystemMessage(content=EXPLORER_SYSTEM_PROMPT),
        HumanMessage(content=EXPLORER_USER_TEMPLATE.format(
            request=(request or "").strip() or NO_REQUEST, profiles=render_profiles(profiles))),
    ]
    while not toolbox.exhausted:
        try:
            reply = bound.invoke(messages)
        except Exception as exc:  # noqa: BLE001 - a failed step never fails the build
            logger.warning("[discovery] model call failed: %s", exc)
            break
        requested = list(getattr(reply, "tool_calls", None) or [])
        if not requested:
            break
        messages.append(reply)
        for call in requested:
            name, args, call_id = str(call.get("name", "")), dict(call.get("args") or {}), call.get("id") or ""
            if toolbox.exhausted:
                messages.append(ToolMessage(content='{"error":"tool budget used up"}', tool_call_id=call_id))
                continue
            yield Probe(name, args)
            messages.append(ToolMessage(content=toolbox.call(name, args), tool_call_id=call_id))
    findings = Findings(facts=toolbox.facts(), calls=list(toolbox.calls))
    logger.info("[discovery] %d tool call(s): %s", len(findings.calls),
                "; ".join(f"{c.name}({c.args})" for c in findings.calls))
    return findings
