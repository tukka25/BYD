"""Writes the line of text that sits at the top of a block.

Before this, a block was titled with the sentence the user typed — so a canvas
read "Bar chart counting report blocks by kind" instead of "Blocks by kind".
The question is how you asked for the chart; it is not what the chart is called.

Built to the same rules as the planner, for the same reason: one decision per
call, the output shape shown literally rather than described, a couple of
examples, a lenient parse, and a deterministic fallback that is used whenever
the model's answer is unusable. A title is cosmetic, so this never fails a
request — it falls back and moves on.

It is told the columns that exist and is forbidden from inventing figures,
because a title that states a number the chart does not show is worse than no
title at all.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, Sequence

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

MAX_WORDS = 7
MAX_CHARS = 70

_SYSTEM = (
    "You write the title for one chart on a dashboard.\n"
    "\n"
    "Rules:\n"
    f"- At most {MAX_WORDS} words.\n"
    "- Name what the chart shows, not how it was asked for.\n"
    "- No quotes, no full stop, no chart-type words like 'bar' or 'chart'.\n"
    "- Never state a number or a finding; you have not seen the values.\n"
    "\n"
    "Reply with only the title, on one line."
)

_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("Bar chart counting report blocks by kind", "Blocks by kind"),
    ("show me monthly revenue trend by plan tier please", "Monthly revenue by plan tier"),
)

# Words a small model reaches for when it describes the chart rather than names
# the subject. Stripped from the front of whatever comes back.
_CHART_WORDS = (
    "bar",
    "line",
    "pie",
    "area",
    "scatter",
    "box",
    "histogram",
    "heatmap",
    "treemap",
    "funnel",
    "waterfall",
    "chart",
    "graph",
    "plot",
    "of",
    "a",
    "an",
    "the",
    "showing",
    "show",
    "display",
    "visualise",
    "visualize",
)

_FILLER = re.compile(
    r"^\s*(please|can you|could you|i want to see|i want|i would like|i need|"
    r"give|show|make|build|create|draw|plot|display|get)\s*(me|us)?\b[:,\s]*",
    re.IGNORECASE,
)

# A reply that is code, not a title. The narrator shares a model server with the
# chartist adapter, and every contract-compliant answer that adapter writes ends
# in `print(fig.to_json())` -- which is exactly the line `_clean` would keep,
# since it takes the last line. Parentheses on their own are allowed ("Revenue
# (USD) by region" is a fine title), and so are words like "Import", "Print" and
# "Return", which open real titles; an empty call, an assignment, an index or
# attribute access on the names the chartist always uses are not.
_CODE_SHAPED = re.compile(
    r"[=\[\]{}]"
    r"|\(\s*\)"
    r"|\b(?:fig|df|px|go|pd|np)\s*\."
)

# A title that ends on a preposition reads as if it was cut off, which after
# truncating to seven words it usually was.
_DANGLING = frozenset(
    "a an and as at by for from in into of on or over per the to with versus vs".split()
)


def _clean(text: str) -> str:
    """Trim a model reply down to a title, or return "" if nothing is left."""
    if not text:
        return ""
    # A thinking model can still emit a preamble; the last non-empty line is
    # the answer far more often than the first.
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    title = lines[-1]
    # Label before quotes: in `Title: "Monthly revenue"` the opening quote is not
    # at the start until the label is gone, so stripping quotes first left it on.
    title = re.sub(r"^(title|answer)\s*[:\-]\s*", "", title.strip(), flags=re.IGNORECASE)
    title = title.strip().strip("\"'`").strip()
    title = title.rstrip(".")
    title = re.sub(r"\s+", " ", title)
    if not title or len(title) > MAX_CHARS * 2:
        return ""
    # Code, or a bare closing bracket from the end of a multi-line call: either
    # way not a title, so let the caller fall back to the question.
    if _CODE_SHAPED.search(title) or not re.search(r"[A-Za-z]", title):
        return ""
    words = title.split()
    if len(words) > MAX_WORDS:
        words = words[:MAX_WORDS]
    return " ".join(words)[:MAX_CHARS].strip()


def _from_question(question: str) -> str:
    """The deterministic fallback: the question, tidied into a title.

    Strips the polite opening and the leading chart-type words, so
    "bar chart of sales by region" becomes "Sales by region" without a model.
    """
    text = (question or "").strip()
    # Looped: "please give me a pie chart of X" needs two passes before the
    # chart words are even at the front.
    while True:
        stripped = _FILLER.sub("", text).strip()
        if stripped == text:
            break
        text = stripped
    text = re.sub(r"[\s,]*(please|thanks|thank you)\s*$", "", text, flags=re.IGNORECASE)
    text = text.rstrip("?.")

    words = text.split()
    while words and words[0].lower().strip(",") in _CHART_WORDS:
        words.pop(0)
    words = words[:MAX_WORDS]
    while words and words[-1].lower().strip(",") in _DANGLING:
        words.pop()

    title = " ".join(words)[:MAX_CHARS].strip()
    if not any(ch.isalnum() for ch in title):
        return "Untitled"
    return title[:1].upper() + title[1:]


class Narrator:
    """One call, one short line of text. Never raises."""

    def __init__(self, llm=None):
        self.llm = llm

    def title_for(self, question: str, columns: Sequence[str] | None = None) -> str:
        fallback = _from_question(question)
        if self.llm is None:
            return fallback

        known: Iterable[str] = list(columns or [])[:14]
        messages = [("system", _SYSTEM)]
        for example_question, example_title in _EXAMPLES:
            messages.append(("human", example_question))
            messages.append(("ai", example_title))
        messages.append(
            (
                "human",
                ("Columns: " + ", ".join(known) + "\n" if known else "") + (question or ""),
            )
        )

        try:
            chain = ChatPromptTemplate.from_messages(messages) | self.llm | StrOutputParser()
            title = _clean(chain.invoke({}))
        except Exception as exc:  # noqa: BLE001 - a title is never worth a 500
            logger.warning("[narrator] failed, using the question: %s", exc)
            return fallback

        if not title:
            logger.info("[narrator] unusable reply, using the question")
            return fallback
        return title[:1].upper() + title[1:]
