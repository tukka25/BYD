"""Run the same chart question on two models and keep the evidence.

Everything that is not the model is shared on purpose, and shared by reusing
the objects rather than by copying them:

* one data source, sampled once, so both see the same rows
* one schema block, built once, so both get the same `columns`/`dtypes`/`sample`
* one planner call, so both are asked for the same chart type
* the same `ChartistAgent` class -- same prompt, same reply reading, same
  contract validation, same repair turn
* the same `SafeExecutor`, the same DataFrame object and the same repair loop
  (`workflow.run_on_frame`): failed code goes back to the model that wrote it,
  at most twice. Nothing hardcoded ever draws a cell.

What is recorded per cell is what actually happened: the code that ran, how
many times the model had to fix it, the contract violations in its first
answer, the execution error if any, the wall clock, and for the API model the
tokens it billed across every call.

The comparison is not persisted. It is an experiment, not a report.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from app.core.config import get_settings
from app.services.agents.chartist import ChartistAgent, ChartistUnavailable
from app.services.agents.chartist_contract import validate_chart_code
from app.services.agents.workflow import run_on_frame
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
    repairs: int = 0
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
    variables = chartist.prompt_variables(question, task_plan, data_context)

    def bill() -> Optional[str]:
        """Add the API model's last call to the cell; its refusal, if it refused."""
        call = getattr(chartist.generator, "last", None)
        if call is None:
            return None
        result.input_tokens += call.input_tokens
        result.output_tokens += call.output_tokens
        return call.refused

    try:
        code = chartist.write(variables)
    except ChartistUnavailable as exc:
        result.error = f"generation failed: {exc}"
        result.seconds = time.perf_counter() - started
        return result
    refused = bill()
    result.code = code
    result.violations = [v.value for v in validate_chart_code(code)]
    if refused:
        result.error = f"the model declined ({refused})"
        result.seconds = time.perf_counter() - started
        return result

    def repair(previous: str, problem: str) -> str:
        fixed = chartist.write(variables, previous, problem)
        declined = bill()
        if declined:
            raise ChartistUnavailable(f"the model declined ({declined})")
        return fixed

    # The workflow's own runner, so both sides get exactly the app's repair
    # loop. The frame is copied so one model's code cannot disturb the other's.
    outcome = run_on_frame(executor, code, frame.copy(), repair)
    execution = outcome.get("execution_result") or {}
    result.code = outcome.get("code_run") or code
    result.repairs = int(outcome.get("repairs") or 0)
    result.seconds = time.perf_counter() - started

    if execution.get("success") and execution.get("figure"):
        result.ok = True
        result.figure = decode_typed_arrays(execution["figure"])
    else:
        result.error = outcome.get("error") or execution.get("error") or "no figure was produced"
    return result
