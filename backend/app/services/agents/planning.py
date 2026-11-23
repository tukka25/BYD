"""The dashboard's two planning calls, each checked and retried.

`propose_directions` asks what the dashboard should answer; `plan_charts` turns
those answers into chart plans in one call. Both go through `run_checked`: the
reply is parsed, checked against the real tables by planning_contract, and any
problem goes back to the model in plain words, at most twice more. The best
attempt is kept, so a mostly-right plan still ships its good charts.

Each failed try is logged with its problems, and each retry is announced before
it starts (the `*_steps` variants yield a `Retry`), because a retry is another
half-minute model call and the dashboard build shows it on screen.

Messages are built as message objects, never through a prompt template: the
prompts contain JSON braces, which a template would read as variables.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Generator

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
    with_context,
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


@dataclass
class Retry:
    """A checked call is going back to the model: the try about to start, and why."""

    attempt: int
    of: int
    errors: list[str]


def run_checked(
    llm: Any,
    system: str,
    user: str,
    check: Check,
    tables: dict[str, dict[str, str]],
    label: str = "planning",
    max_attempts: int = MAX_ATTEMPTS,
) -> Generator[Retry, None, PlanStep]:
    """Call, check, and send problems back; yields a Retry before each retry, returns the PlanStep."""
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
        logger.info(
            "[planning] %s try %d of %d: %d usable, %d problem(s): %s",
            label, attempt, max_attempts, len(items), len(errors), "; ".join(errors[:10]),
        )
        if attempt == max_attempts:
            break
        messages = messages + [
            AIMessage(content=raw),
            HumanMessage(content=FIX_PROMPT.format(errors="\n".join(f"- {e}" for e in errors[:10]))),
        ]
        yield Retry(attempt + 1, max_attempts, errors)
    return PlanStep(best_items, best_errors, attempts, replies)


def finish(steps: Generator[Retry, None, PlanStep]) -> PlanStep:
    """Run a checked call to the end without announcing its retries."""
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value


def propose_directions_steps(
    llm: Any, request: str, profiles: list[TableProfile], facts: str = "", memory: str = "", links: str = ""
) -> Generator[Retry, None, PlanStep]:
    user = with_context(
        ANALYST_USER_TEMPLATE.format(request=(request or "").strip() or NO_REQUEST, profiles=render_profiles(profiles)),
        facts,
        memory,
        links,
    )
    return run_checked(llm, ANALYST_SYSTEM_PROMPT, user, check_directions, columns_by_table(profiles), "analyst")


def propose_directions(
    llm: Any, request: str, profiles: list[TableProfile], facts: str = "", memory: str = "", links: str = ""
) -> PlanStep:
    return finish(propose_directions_steps(llm, request, profiles, facts, memory, links))


def plan_charts_steps(
    llm: Any,
    directions: list[dict],
    profiles: list[TableProfile],
    facts: str = "",
    validate: Callable[[dict], list[str]] | None = None,
    links: str = "",
) -> Generator[Retry, None, PlanStep]:
    user = with_context(
        PLANNER_USER_TEMPLATE.format(profiles=render_profiles(profiles), directions=render_directions(directions)),
        facts,
        links=links,
    )
    check = check_specs if validate is None else (lambda payload, tables: check_specs(payload, tables, validate))
    return run_checked(llm, PLANNER_SYSTEM_PROMPT, user, check, columns_by_table(profiles), "planner")


def plan_charts(
    llm: Any,
    directions: list[dict],
    profiles: list[TableProfile],
    facts: str = "",
    validate: Callable[[dict], list[str]] | None = None,
    links: str = "",
) -> PlanStep:
    return finish(plan_charts_steps(llm, directions, profiles, facts, validate, links))
