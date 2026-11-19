"""The execution oracle: run a candidate against a real CSV and judge it."""
from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from contract import validate_chart_code

RUNNER = Path(__file__).with_name("_candidate_runner.py")
_COLUMN_KWARGS = (
    "x", "y", "z", "color", "size", "names", "values", "facet_col", "facet_row",
    "path", "hover_name", "line_group", "symbol", "pattern_shape",
)
# A string is a column reference only as one of these kwargs' values or in df[...].
_COLUMN_REF = re.compile(
    r"""(?:\b(?:%s)\s*=\s*|\bdf\s*\[\s*)(['"])([^'"]{1,80})\1""" % "|".join(_COLUMN_KWARGS)
)

_NOT_COLUMNS = {
    "plotly", "plotly_white", "plotly_dark", "seaborn", "simple_white", "ggplot2",
    "presentation", "group", "stack", "overlay", "relative", "h", "v", "linear",
    "log", "date", "category", "outliers", "all", "sum", "mean", "count", "avg",
    "total", "value", "variable", "index", "none", "top", "bottom", "left", "right",
    "red", "blue", "green", "black", "white", "grey", "gray", "orange", "purple",
    "yellow", "cyan", "magenta", "brown", "pink", "teal", "navy", "olive", "maroon",
    "lime", "aqua", "silver", "gold", "crimson", "indigo", "violet", "turquoise",
    "salmon", "khaki", "beige", "ivory",
}


@dataclass
class CandidateResult:
    ok: bool
    violations: list[str] = field(default_factory=list)
    figure_type: str | None = None
    error: str | None = None
    # Informational only: over-reports columns derived in code (groupby/agg/etc).
    # Never use it as a gate; execution is the oracle.
    unknown_columns: list[str] = field(default_factory=list)
    failure_kind: str | None = None  # hallucinated_column | runtime_error | timeout | bad_output


def _unknown_columns(code: str, columns: list[str]) -> list[str]:
    """Strings in a column position (x='..', df['..']) that are not in the schema."""
    known = {str(c) for c in columns}
    known_lower = {c.lower() for c in known}
    out = []
    for value in sorted({m.group(2) for m in _COLUMN_REF.finditer(code)}):
        if value in known or value.lower() in known_lower:
            continue
        if value.lower() in _NOT_COLUMNS:
            continue
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9 _]{1,40}", value):  # skips '#ff0000', 'rgb(..)'
            out.append(value)
    return out


_HALLUCINATION = re.compile(
    r"KeyError|not in index|None of \[.*\] are in the \[columns\]"
    r"|is not the name of a column|Could not interpret value"
)


def run_candidate(code: str, df_csv: str, timeout_seconds: int = 20) -> CandidateResult:
    """Total function: returns a verdict for any input, never raises."""
    try:
        return _run_candidate(code, df_csv, timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - one bad row must not sink a batch
        return CandidateResult(
            ok=False, error=f"{type(exc).__name__}: {exc}"[-400:], failure_kind="runtime_error"
        )


def _run_candidate(code: str, df_csv: str, timeout_seconds: int) -> CandidateResult:
    violations = [v.value for v in validate_chart_code(code)]
    if violations:
        return CandidateResult(ok=False, violations=violations)

    try:
        if str(df_csv).endswith((".xlsx", ".xls")):
            columns = list(pd.read_excel(df_csv, nrows=1).columns)
        else:
            columns = list(pd.read_csv(df_csv, nrows=1).columns)
    except Exception as exc:  # noqa: BLE001
        return CandidateResult(
            ok=False, error=f"cannot read {df_csv}: {exc}", failure_kind="unreadable_input"
        )

    unknown = _unknown_columns(code, columns)

    try:
        completed = subprocess.run(
            [sys.executable, "-I", str(RUNNER)],
            input=json.dumps({"code": code, "data_path": str(df_csv)}),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(RUNNER.parent),
        )
    except subprocess.TimeoutExpired:
        return CandidateResult(
            ok=False, error=f"timed out after {timeout_seconds}s", unknown_columns=unknown,
            failure_kind="timeout",
        )

    if completed.returncode != 0:
        stderr = completed.stderr or ""
        return CandidateResult(
            ok=False,
            error=(stderr or "non-zero exit").strip()[-400:],
            unknown_columns=unknown,
            failure_kind="hallucinated_column" if _HALLUCINATION.search(stderr) else "runtime_error",
        )

    try:
        lines = [ln for ln in completed.stdout.splitlines() if ln.strip()]
        figure = json.loads(lines[-1])
    except (ValueError, IndexError, RecursionError):
        return CandidateResult(
            ok=False, error="stdout was not valid JSON", unknown_columns=unknown,
            failure_kind="bad_output",
        )

    if not isinstance(figure, dict):
        return CandidateResult(
            ok=False, error=f"stdout JSON was {type(figure).__name__}, not an object",
            unknown_columns=unknown, failure_kind="bad_output",
        )

    traces = figure.get("data")
    if not isinstance(traces, list) or (traces and not isinstance(traces[0], dict)):
        return CandidateResult(
            ok=False, error="figure 'data' is not a list of trace objects",
            unknown_columns=unknown, failure_kind="bad_output",
        )
    figure_type = None
    if traces:
        figure_type = traces[0].get("type") or "scatter"  # px.line omits an explicit type
    if figure_type is None:
        return CandidateResult(
            ok=False, error="figure has no traces (rendered nothing)", unknown_columns=unknown,
            failure_kind="no_figure",
        )
    return CandidateResult(
        ok=True, figure_type=figure_type, unknown_columns=unknown
    )


def run_candidates(
    jobs: list[tuple[str, str]],
    max_workers: int = 8,
    timeout_seconds: int = 20,
) -> list[CandidateResult]:
    """Validate many candidates concurrently, preserving input order.

    run_candidate blocks in subprocess.run, which releases the GIL, so threads
    give near-linear speedup without multiprocessing. Each verdict depends only
    on its own (code, csv) pair, so concurrency cannot change any result.
    """
    if not jobs:
        return []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(lambda job: run_candidate(job[0], job[1], timeout_seconds), jobs))
