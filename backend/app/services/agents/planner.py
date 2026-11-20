"""Picks the chart type for a request.

Rewritten for a small local model. What the previous version asked for, and why
each part was a problem on an SLM:

* It asked for FOUR fields at once (steps, visualization_type, style_config,
  data_requirements) in one JSON object. Small models degrade sharply as the
  number of simultaneous obligations grows. Only `visualization_type` was ever
  used downstream; `steps` reached a log line and `data_requirements` nothing.
* It said "Return the output strictly in JSON format matching the TaskPlan
  schema" — but the prompt had no `{format_instructions}` placeholder, so **the
  schema was never actually sent.** The model was asked to match a schema it had
  never seen.
* The instruction was indented multi-line prose. Tokens spent on manners rather
  than on the decision.
* There was no closed label set, so "visualization_type" could come back as
  anything, and no examples, which is the cheapest accuracy win available on a
  small model.

So: one decision, a closed set of labels, the exact output shape shown, two
examples, and a deterministic keyword fallback that beats "always bar" when the
model's answer is unusable.

Note that the chart type no longer steers the chartist. The fine-tuned chartist
infers the chart from the user's question, as it was trained to; this label is
used for the deterministic fallback renderer and for response metadata.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Closed set. Kept aligned with the chart buckets the chartist was fine-tuned on.
CHART_TYPES: tuple[str, ...] = (
    "bar",
    "line",
    "scatter",
    "pie",
    "histogram",
    "box",
    "heatmap",
    "area",
    "treemap",
    "funnel",
    "waterfall",
    "indicator",
)

DEFAULT_CHART = "bar"
DEFAULT_STYLE: Dict[str, Any] = {"theme": "plotly_white"}

# Ordered most-specific first: "share of total over time" should read as a trend,
# not a composition, so `_keyword_chart` checks time words before share words.
_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("line", ("over time", "trend", "monthly", "weekly", "daily", "quarterly", "yearly", "by month", "growth")),
    ("indicator", ("kpi", "single number", "total number", "gauge", "how many in total", "headline")),
    ("histogram", ("distribution", "histogram", "spread of", "frequency")),
    ("box", ("outlier", "quartile", "box plot", "variance across", "median by")),
    ("heatmap", ("heatmap", "correlation", "matrix", "by hour and day", "cross-tab")),
    ("scatter", ("against", "versus", " vs ", "relationship", "correlate")),
    ("pie", ("share", "proportion", "percentage of total", "breakdown of total", "split of")),
    ("treemap", ("treemap", "hierarch", "nested")),
    ("funnel", ("funnel", "conversion", "drop-off", "pipeline stage")),
    ("waterfall", ("waterfall", "contribution to change", "variance explained")),
    ("area", ("cumulative", "stacked over time", "area chart")),
)

_SYSTEM = (
    "You choose the chart type for a dashboard question.\n"
    "\n"
    "Allowed values, choose exactly one:\n"
    + ", ".join(CHART_TYPES)
    + "\n\n"
    'Reply with only this JSON, no prose:\n'
    '{{"chart_type": "<one allowed value>"}}'
)

# Two examples. On a small model this is the cheapest accuracy available, and it
# also pins the output shape far more reliably than describing it does.
_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("Monthly revenue trend for the last year", '{{"chart_type": "line"}}'),
    ("Which product categories make up our sales", '{{"chart_type": "pie"}}'),
)

_JSON_OBJECT = re.compile(r"\{[^{}]*\}", re.DOTALL)


class TaskPlan(BaseModel):
    """What the rest of the workflow consumes. Only two fields are load-bearing."""

    visualization_type: str = Field(default=DEFAULT_CHART, description="One of CHART_TYPES")
    style_config: Dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_STYLE))
    steps: List[str] = Field(default_factory=list)
    data_requirements: str = Field(default="")


def _keyword_chart(query: str) -> str:
    """Deterministic backstop. Beats defaulting to bar, and costs nothing."""
    text = f" {(query or '').lower()} "
    for chart, needles in _KEYWORD_RULES:
        if any(n in text for n in needles):
            return chart
    return DEFAULT_CHART


def _parse_chart_type(raw: str) -> str | None:
    """Pull a chart type out of whatever the model said.

    Tries strict JSON, then the first JSON-looking object anywhere in the reply,
    then a bare mention of an allowed label. A small model that wraps its answer
    in a sentence should not cost us the request.
    """
    if not raw:
        return None
    text = raw.strip()
    for candidate in ([text] if text.startswith("{") else []) + _JSON_OBJECT.findall(text):
        try:
            value = json.loads(candidate).get("chart_type")
        except (json.JSONDecodeError, AttributeError):
            continue
        if isinstance(value, str) and value.strip().lower() in CHART_TYPES:
            return value.strip().lower()
    lowered = text.lower()
    hits = [c for c in CHART_TYPES if re.search(rf"\b{c}\b", lowered)]
    return hits[0] if len(hits) == 1 else None


class PlannerAgent:
    """Chooses one chart type. Never raises."""

    def __init__(self, llm):
        self.llm = llm
        messages: list[tuple[str, str]] = [("system", _SYSTEM)]
        for question, answer in _EXAMPLES:
            messages.append(("human", question))
            messages.append(("ai", answer))
        messages.append(("human", "{input}"))
        self.prompt = ChatPromptTemplate.from_messages(messages)
        self.chain = self.prompt | self.llm | StrOutputParser()

    def create_plan(self, user_query: str) -> Dict[str, Any]:
        """Return a plan dict. Falls back to keywords, then to bar."""
        chart = None
        try:
            raw = self.chain.invoke({"input": user_query})
            chart = _parse_chart_type(raw)
            if chart is None:
                logger.warning("[planner] unusable reply %r, falling back to keywords", (raw or "")[:120])
        except Exception:
            logger.exception("[planner] call failed, falling back to keywords")

        source = "llm"
        if chart is None:
            chart, source = _keyword_chart(user_query), "keywords"

        logger.info("[planner] chart_type=%s via=%s", chart, source)
        return {
            "visualization_type": chart,
            "style_config": dict(DEFAULT_STYLE),
            "steps": [f"Chart type {chart} chosen via {source}", "Resolve data source", "Generate chart"],
            "data_requirements": user_query,
            "chart_type_source": source,
        }
