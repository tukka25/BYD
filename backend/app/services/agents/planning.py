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

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Generator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.services.agents.chart_kinds import include_kinds
from app.services.agents.discovery import Probe, run_tools
from app.services.agents.planning_contract import (
    ANALYST_SYSTEM_PROMPT,
    ANALYST_USER_TEMPLATE,
    CHECKER_SYSTEM_PROMPT,
    CHECKER_USER_TEMPLATE,
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


def _answer(llm: Any, messages: list) -> Any:
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


# The checking turn is told to answer 'no changes' for a plan that needs none, and
# lora-v2 does so word for word. Only that reply (or "none"), with an optional list
# number, "Plan N:" prefix and "needed"/"required"/"necessary", asks for nothing.
# Anything else asks for a change: a revision costs one call, and it is kept only
# when it checks at least as well as the draft (the judge), so a doubtful line never
# loses a draft and a real request is never missed.
_NO_CHANGE = re.compile(r"(no changes?|none)( (needed|required|necessary))?")


def changes_asked(notes: str) -> list[str]:
    """The lines of the checking turn's reply that ask for a change. A line's plan
    number (a list number, or a "Plan N:"/"Chart N:" prefix) is kept as "chart N: ",
    the form the retry's own problems use, so the planner knows which chart to change.
    Only "no changes" (or "none"), optionally followed by "needed", "required" or
    "necessary", asks for nothing; so does a line without a letter. [] means the
    drafts stand."""
    asked = []
    for line in notes.splitlines():
        number = None
        marker = re.match(r"^\s*(?:(\d+)[.)]|[-*•])\s*", line)
        if marker:
            number = marker.group(1)
            line = line[marker.end():]
        words = line.strip()
        prefix = re.match(r"^(?:plan|chart)\s*(\d+)\s*[:.)-]\s*", words, flags=re.IGNORECASE)
        if prefix:
            number, words = prefix.group(1), words[prefix.end():].strip()
        plain = " ".join(re.findall(r"[^\W\d_]+", words.lower()))
        if not plain or _NO_CHANGE.fullmatch(plain):
            continue
        asked.append(f"chart {number}: {words}" if number else words)
    return asked


def check_drafts(llm: Any, bound: Any, draft: str, context: str, toolbox: Any) -> Generator[Probe, None, list[str]]:
    """The checking turn: a separate call with its own system prompt holds the
    tools and decides what to look at in the drafts (at most toolbox.max_calls,
    each result its compact fact line), then says what to change. When the budget
    runs out while it is still calling, the plain model answers. Returns the
    lines that ask for a change. The drafts are shown numbered, and preview_chart
    takes those numbers. A failed model call raises."""
    payload = extract_json(draft)
    plans = payload.get("charts") if isinstance(payload, dict) else None
    toolbox.drafts = list(plans) if isinstance(plans, list) else []
    shown = "\n".join(f"{n}. {json.dumps(plan, ensure_ascii=False)}"
                      for n, plan in enumerate(toolbox.drafts, 1) if isinstance(plan, dict)) or draft
    messages: list = [SystemMessage(content=CHECKER_SYSTEM_PROMPT),
                      HumanMessage(content=CHECKER_USER_TEMPLATE.format(context=context, drafts=shown))]
    reply = yield from run_tools(bound, messages, toolbox, compact=True)
    if reply is None or getattr(reply, "tool_calls", None):
        reply = _answer(llm, messages)
    return changes_asked(_text(reply))


def _checking_asker(llm: Any, toolbox: Any, context: str, judge: Callable[[str], tuple]) -> Ask | None:
    """How the planner answers when its drafts are checked (PLANNER_TOOLS=planner).
    Every try starts with a plain call, as the planner was trained. After the
    first, a checking turn holds the tools (`check_drafts`); the lines it asks to
    change go back to the planner once, in the retry's own form (FIX_PROMPT).
    A check or a revision that fails leaves the draft, never a failed build. A
    revision is kept only when `judge` (the rank of a reply under the same checks
    the retry loop uses) puts it at least as high as the draft; code chooses between
    two whole model answers, as run_checked does across tries, and never edits a plan.
    lora-v2's planner calls no tool while it plans (AGENTS.md), so the tools
    live in this separate turn."""
    try:
        bound = llm.bind_tools(toolbox.specs)
    except Exception as exc:  # noqa: BLE001 - no tools on this backend: plan without the check
        logger.warning("[planning] checking turn unavailable, planning without it: %s", exc)
        return None

    def ask(messages: list, attempt: int) -> Generator[Probe, None, str]:
        draft = _text(llm.invoke(messages))
        if attempt != 1:
            return draft
        try:
            asked = yield from check_drafts(llm, bound, draft, context, toolbox)
        except Exception as exc:  # noqa: BLE001 - the check failed: the draft stands
            logger.warning("[planning] checking turn failed, keeping the draft: %s", exc)
            return draft
        if not asked:
            return draft
        logger.info("[planning] checking turn asked for %d change(s): %s", len(asked), "; ".join(asked[:7]))
        revision = messages + [AIMessage(content=draft),
                               HumanMessage(content=FIX_PROMPT.format(errors="\n".join(f"- {line}" for line in asked)))]
        toolbox.revisions += 1
        try:
            revised = _text(llm.invoke(revision))
        except Exception as exc:  # noqa: BLE001 - the revision failed: the draft stands
            logger.warning("[planning] revision after the check failed, keeping the draft: %s", exc)
            return draft
        if judge(revised) >= judge(draft):
            return revised
        logger.warning("[planning] the revision checked worse than the draft; keeping the draft")
        return draft

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

    def check(payload: Any, tables: dict[str, dict[str, str]]) -> tuple[list[dict], list[str]]:
        return check_specs(payload, tables, validate, kinds)

    def rank(items: list[dict], errors: list[str]) -> tuple:
        # An attempt with the kinds the user picked beats a bigger one without them.
        present = sum(1 for kind in kinds if any(item["chart"] == kind for item in items))
        return (present, *by_size(items, errors))

    tables = columns_by_table(profiles)
    context = render_profiles(profiles) + (f"\n\n{links}" if links else "")
    ask = (_checking_asker(llm, toolbox, context, lambda text: rank(*check(extract_json(text), tables)))
           if toolbox is not None else None)
    user = with_context(
        PLANNER_USER_TEMPLATE.format(profiles=render_profiles(profiles), directions=render_directions(directions)),
        facts,
        links=links,
        notes=(include_kinds(kinds),),
    )

    return run_checked(llm, PLANNER_SYSTEM_PROMPT, user, check, tables, "planner",
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
