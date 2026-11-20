"""The chartist, run on Claude Opus 5.5, for comparison against the local SLM.

The point of this module is that it changes exactly one thing. It sends the
SAME system prompt and the SAME user template as the fine-tuned model gets --
imported from `chartist_contract`, not copied -- and hands the raw reply back
to the SAME `ChartistAgent._sanitize_generated_code`, which runs the same
contract validation, the same deterministic fallback and the same property
repair. The executor and the data are identical. Only the weights differ, which
is the only way the comparison means anything.

Deliberate asymmetries, because they cannot be avoided and should be read with
the numbers:

* `temperature` is not sent. The API rejects it on current models, so the SLM's
  `temperature=0` has no counterpart here; Opus runs at its own default.
* Thinking is always on for this model and cannot be disabled, so Opus gets to
  reason before answering and the SLM does not. `effort` is the only dial and
  it is set explicitly rather than left to the default.
* Server-side refusal fallbacks are NOT enabled, against the usual advice. A
  fallback silently answers on a different model, and a comparison whose rows
  may have been served by something other than the model named at the top of
  the column is worthless. A refusal is surfaced as a failed generation.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import anthropic

from app.core.config import get_settings
from app.services.agents.chartist_contract import (
    CHARTIST_SYSTEM_PROMPT,
    CHARTIST_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"

# A Plotly snippet is a few hundred tokens; the headroom is for thinking, which
# is always on for this model. Non-streaming stays well inside the SDK timeout.
MAX_TOKENS = 16000


class ClaudeUnavailable(RuntimeError):
    """No API key, or the SDK could not be constructed."""


@dataclass
class ClaudeCall:
    """What the call cost and what it returned, for the comparison table."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    refused: Optional[str] = None


class ClaudeGenerator:
    """Stands in for the LangChain chain inside `ChartistAgent`.

    `ChartistAgent` calls `.invoke(variables)` and expects the model's raw text
    back. Matching that one method is all it takes to reuse the whole harness.
    """

    def __init__(self, effort: str = "medium"):
        settings = get_settings()
        key = settings.claude_api_key
        if not key:
            raise ClaudeUnavailable(
                "No Claude API key. Set CLAUDE_API_KEY (or ANTHROPIC_API_KEY) for the backend."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self._effort = effort
        self.last: Optional[ClaudeCall] = None

    def invoke(self, variables: Dict[str, Any]) -> str:
        """Same inputs the SLM gets, rendered into the same two prompt strings."""
        user_text = CHARTIST_USER_TEMPLATE.format(
            task=variables.get("task", ""),
            columns=variables.get("columns", ""),
            dtypes=variables.get("dtypes", ""),
            sample_rows=variables.get("sample_rows", ""),
        )

        started = time.perf_counter()
        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=CHARTIST_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_text}],
                # Thinking cannot be turned off on this model; effort is the
                # only control, and the default is medium. Set, not assumed.
                output_config={"effort": self._effort},
            )
        except anthropic.RateLimitError as exc:
            raise RuntimeError(f"Claude rate limited: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise RuntimeError(f"Claude returned {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise RuntimeError(f"Could not reach Claude: {exc}") from exc

        elapsed = time.perf_counter() - started

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            self.last = ClaudeCall(text="", seconds=elapsed, refused=str(category))
            logger.warning("[claude-chartist] refused (%s)", category)
            return ""

        # Thinking blocks carry no text by default; only the answer is wanted.
        text = "".join(block.text for block in response.content if block.type == "text")
        self.last = ClaudeCall(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            seconds=elapsed,
        )
        return text


def is_configured() -> bool:
    return bool(get_settings().claude_api_key)
