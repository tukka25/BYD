"""Run the same chart question on two models and keep the evidence.

Everything that is not the model is shared on purpose, and shared by reusing
the objects rather than by copying them:

* one data source, sampled once, so both see the same rows
* one schema block, built once, so both get the same `columns`/`dtypes`/`sample`
* one planner call, so both are asked for the same chart type
* the same `ChartistAgent` class -- same prompt, same sanitiser, same contract
  validation, same deterministic fallback
* the same `SafeExecutor` and the same DataFrame object

What is recorded per cell is what actually happened: the code, whether it was
the model's or the fallback's, the contract violations if any, the execution
error if any, the wall clock, and for the API model the tokens it billed.

The comparison is not persisted. It is an experiment, not a report.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from app.core.config import get_settings
from app.services.agents.chartist import FALLBACK_MARKER, ChartistAgent
from app.services.agents.chartist_contract import validate_chart_code
from app.services.claude_chartist import ClaudeGenerator, ClaudeUnavailable
from app.utils.figure_json import decode_typed_arrays

logger = logging.getLogger(__name__)

SLM = "slm"
OPUS = "opus"

ENGINE_LABELS = {
    SLM: "Fine-tuned Qwen3.5-9B (local)",
    OPUS: "Claude Opus 5.5 (API)",
}


@dataclass
class CellResult:
    """One model's answer to one question."""

    engine: str
    ok: bool = False
    code: str = ""
    figure: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    used_fallback: bool = False
    violations: List[str] = field(default_factory=list)
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)


def available_engines() -> Dict[str, bool]:
    return {SLM: True, OPUS: bool(get_settings().claude_api_key)}


def build_chartists(llm_for_slm) -> Dict[str, ChartistAgent]:
    """One agent per engine. Same class, same contract; different weights."""
    settings = get_settings()
    agents: Dict[str, ChartistAgent] = {SLM: ChartistAgent(llm=llm_for_slm)}
    try:
        agents[OPUS] = ChartistAgent(
            llm=None, generator=ClaudeGenerator(effort=settings.CLAUDE_EFFORT)
        )
    except ClaudeUnavailable as exc:
        logger.info("[comparison] Claude not configured: %s", exc)
    return agents


def run_cell(
    engine: str,
    chartist: ChartistAgent,
    question: str,
    task_plan: Dict[str, Any],
    data_context: Dict[str, Any],
    frame: pd.DataFrame,
    executor: Any,
) -> CellResult:
    """Generate and run one chart. Never raises: a failure is a result."""
    result = CellResult(engine=engine)
    started = time.perf_counter()

    try:
        code = chartist.generate_code(
            user_query=question, task_plan=task_plan, data_context=data_context
        )
    except Exception as exc:  # noqa: BLE001 - a dead model is a cell, not a 500
        result.error = f"generation failed: {exc}"
        result.seconds = time.perf_counter() - started
        return result

    result.code = code
    result.used_fallback = FALLBACK_MARKER in code
    # On a fallback these are the reasons the MODEL's code was rejected, which
    # is the interesting part; otherwise they describe the code that ran.
    result.violations = (
        list(getattr(chartist, "last_violations", []))
        if result.used_fallback
        else [v.value for v in validate_chart_code(code)]
    )

    # The API model reports its own cost and latency; the local one is timed
    # by the same clock that wraps both.
    call = getattr(chartist.generator, "last", None)
    if call is not None:
        result.input_tokens = call.input_tokens
        result.output_tokens = call.output_tokens
        if call.refused:
            result.error = f"the model declined ({call.refused})"

    # The DataFrame is copied so one model's code cannot mutate what the other
    # is about to be run against.
    execution = executor.execute(code, frame.copy())
    result.seconds = time.perf_counter() - started

    if execution.get("success") and execution.get("figure"):
        result.ok = True
        result.figure = decode_typed_arrays(execution["figure"])
    else:
        result.error = result.error or execution.get("error") or "no figure was produced"
    return result
