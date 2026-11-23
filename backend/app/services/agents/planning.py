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

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.services.agents.chart_kinds import include_kinds
from app.services.agents.discovery import Probe, run_tools
from app.services.agents.planning_contract import (
    ANALYST_SYSTEM_PROMPT,
    ANALYST_USER_TEMPLATE,
    FIX_PROMPT,
    NO_REQUEST,
    PLANNER_SYSTEM_PROMPT,
    PLANNER_TOOLS_NOTE,
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
# How two checked attempts compare: the one with the larger key is kept.
Rank = Callable[[list[dict], list[str]], tuple]
# How one try is answered when it is more than one model call (the planner with
# tools): given the messages and the try number, yields tool calls, returns the reply text.
Ask = Callable[[list, int], Generator[Probe, None, str]]


def by_size(items: list[dict], errors: list[str]) -> tuple:
    """The default best attempt: the most usable items, then the fewest problems."""
    return (len(items), -len(errors))


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
    rank: Rank = by_size,
    ask: Ask | None = None,
) -> Generator[Retry | Probe, None, PlanStep]:
    """Call, check, and send problems back; yields a Retry before each retry (and
    a Probe for each tool call, when `ask` makes them), returns the PlanStep.
    The attempt kept is the one `rank` puts highest."""
    messages: list = [SystemMessage(content=system), HumanMessage(content=user)]
    best_items: list[dict] = []
    best_errors: list[str] = ["the model was not called"]
    replies: list[str] = []
    attempts = 0
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        try:
            raw = _text(llm.invoke(messages)) if ask is None else (yield from ask(messages, attempt))
        except Exception as exc:  # noqa: BLE001 - a dead model is an error, not a 500
            logger.warning("[planning] model call failed: %s", exc)
            if not best_items:
                best_errors = [f"the model call failed: {exc}"]
            break
        replies.append(raw)
        items, errors = check(extract_json(raw), tables)
        if attempt == 1 or rank(items, errors) > rank(best_items, best_errors):
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


def finish(steps: Generator[Retry | Probe, None, PlanStep]) -> PlanStep:
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


def _tool_asker(llm: Any, toolbox: Any) -> Ask | None:
    """How the planner answers when it holds the tools. On its first try it may
    call them (at most toolbox.max_calls, each result its compact fact line);
    when it stops, that reply is its answer, and when the budget runs out the
    plain model answers. A retry is a plain call, as the planner was trained.
    Tools that fail mean planning without them, never a failed build."""
    try:
        bound = llm.bind_tools(toolbox.specs)
    except Exception as exc:  # noqa: BLE001 - no tools on this backend: plan without them
        logger.warning("[planning] planner tools unavailable, planning without them: %s", exc)
        return None

    def answer(messages: list) -> Any:
        """The plain model's reply. A server that will not take tool turns without
        tools offered gets the same messages without them."""
        try:
            return llm.invoke(messages)
        except Exception as exc:  # noqa: BLE001 - retried once below, without the tool turns
            plain = [m for m in messages if not isinstance(m, ToolMessage) and not getattr(m, "tool_calls", None)]
            if len(plain) == len(messages):
                raise
            logger.warning("[planning] answering with the tool turns failed, answering without them: %s", exc)
            return llm.invoke(plain)

    def ask(messages: list, attempt: int) -> Generator[Probe, None, str]:
        reply = None
        if attempt == 1:
            try:
                reply = yield from run_tools(bound, messages, toolbox, compact=True)
            except Exception as exc:  # noqa: BLE001 - the tool step failed: answer without it
                logger.warning("[planning] planner tool step failed, planning without it: %s", exc)
        if reply is None or getattr(reply, "tool_calls", None):
            reply = answer(messages)
        return _text(reply)

    return ask


def plan_charts_steps(
    llm: Any,
    directions: list[dict],
    profiles: list[TableProfile],
    facts: str = "",
    validate: Callable[[dict], list[str]] | None = None,
    links: str = "",
    required_kinds: tuple[str, ...] = (),
    toolbox: Any = None,
) -> Generator[Retry | Probe, None, PlanStep]:
    kinds = tuple(required_kinds)
    ask = _tool_asker(llm, toolbox) if toolbox is not None else None
    user = with_context(
        PLANNER_USER_TEMPLATE.format(profiles=render_profiles(profiles), directions=render_directions(directions)),
        facts,
        links=links,
        notes=(include_kinds(kinds), PLANNER_TOOLS_NOTE if ask is not None else ""),
    )

    def check(payload: Any, tables: dict[str, dict[str, str]]) -> tuple[list[dict], list[str]]:
        return check_specs(payload, tables, validate, kinds)

    def rank(items: list[dict], errors: list[str]) -> tuple:
        # An attempt with the kinds the user picked beats a bigger one without them.
        present = sum(1 for kind in kinds if any(item["chart"] == kind for item in items))
        return (present, *by_size(items, errors))

    return run_checked(llm, PLANNER_SYSTEM_PROMPT, user, check, columns_by_table(profiles), "planner",
                       rank=rank, ask=ask)


def plan_charts(
    llm: Any,
    directions: list[dict],
    profiles: list[TableProfile],
    facts: str = "",
    validate: Callable[[dict], list[str]] | None = None,
    links: str = "",
    required_kinds: tuple[str, ...] = (),
    toolbox: Any = None,
) -> PlanStep:
    return finish(plan_charts_steps(llm, directions, profiles, facts, validate, links, required_kinds, toolbox))
