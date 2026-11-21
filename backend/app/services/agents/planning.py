"""The dashboard's two planning calls, each checked and retried.

`propose_directions` asks what the dashboard should answer; `plan_charts` turns
those answers into chart plans in one call. Both go through `run_checked`: the
reply is parsed, checked against the real tables by planning_contract, and any
problem goes back to the model in plain words, at most twice more. The best
attempt is kept, so a mostly-right plan still ships its good charts.

Messages are built as message objects, never through a prompt template: the
prompts contain JSON braces, which a template would read as variables.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.agents.planning_contract import (
    ANALYST_SYSTEM_PROMPT,
    ANALYST_USER_TEMPLATE,
    FIX_PROMPT,
    NO_REQUEST,
    PLANNER_SYSTEM_PROMPT,
    PLANNER_USER_TEMPLATE,
    check_directions,
    check_specs,
    extract_json,
    render_directions,
)
from app.services.agents.profiler import TableProfile, columns_by_table, render_profiles

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3

Check = Callable[[Any, dict[str, dict[str, str]]], tuple[list[dict], list[str]]]


@dataclass
class PlanStep:
    items: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    attempts: int = 0
    replies: list[str] = field(default_factory=list)


def _text(reply: Any) -> str:
    content = getattr(reply, "content", reply)
    if isinstance(content, list):  # some chat models return content parts
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content or "")


def run_checked(
    llm: Any,
    system: str,
    user: str,
    check: Check,
    tables: dict[str, dict[str, str]],
    max_attempts: int = MAX_ATTEMPTS,
) -> PlanStep:
    messages: list = [SystemMessage(content=system), HumanMessage(content=user)]
    best_items: list[dict] = []
    best_errors: list[str] = ["the model was not called"]
    replies: list[str] = []
    attempts = 0
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        try:
            raw = _text(llm.invoke(messages))
        except Exception as exc:  # noqa: BLE001 - a dead model is an error, not a 500
            logger.warning("[planning] model call failed: %s", exc)
            if not best_items:
                best_errors = [f"the model call failed: {exc}"]
            break
        replies.append(raw)
        items, errors = check(extract_json(raw), tables)
        better = len(items) > len(best_items) or (
            len(items) == len(best_items) and len(errors) < len(best_errors)
        )
        if attempt == 1 or better:
            best_items, best_errors = items, errors
        if items and not errors:
            break
        messages = messages + [
            AIMessage(content=raw),
            HumanMessage(content=FIX_PROMPT.format(errors="\n".join(f"- {e}" for e in errors[:10]))),
        ]
    return PlanStep(best_items, best_errors, attempts, replies)


def propose_directions(llm: Any, request: str, profiles: list[TableProfile]) -> PlanStep:
    user = ANALYST_USER_TEMPLATE.format(
        request=(request or "").strip() or NO_REQUEST, profiles=render_profiles(profiles)
    )
    return run_checked(llm, ANALYST_SYSTEM_PROMPT, user, check_directions, columns_by_table(profiles))


def plan_charts(llm: Any, directions: list[dict], profiles: list[TableProfile]) -> PlanStep:
    user = PLANNER_USER_TEMPLATE.format(
        profiles=render_profiles(profiles), directions=render_directions(directions)
    )
    return run_checked(llm, PLANNER_SYSTEM_PROMPT, user, check_specs, columns_by_table(profiles))
