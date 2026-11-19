"""The execution oracle: run a candidate against a real CSV and judge it."""
from __future__ import annotations

import json
import re
import subprocess
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
}


@dataclass
class CandidateResult:
    ok: bool
    violations: list[str] = field(default_factory=list)
    figure_type: str | None = None
    error: str | None = None
    unknown_columns: list[str] = field(default_factory=list)


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
        out.append(value)
    return out


def run_candidate(code: str, df_csv: str, timeout_seconds: int = 20) -> CandidateResult:
    violations = [v.value for v in validate_chart_code(code)]
    if violations:
        return CandidateResult(ok=False, violations=violations)

    try:
        if str(df_csv).endswith((".xlsx", ".xls")):
            columns = list(pd.read_excel(df_csv, nrows=1).columns)
        else:
            columns = list(pd.read_csv(df_csv, nrows=1).columns)
    except Exception as exc:  # noqa: BLE001
        return CandidateResult(ok=False, error=f"cannot read {df_csv}: {exc}")

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
            ok=False, error=f"timed out after {timeout_seconds}s", unknown_columns=unknown
        )

    if completed.returncode != 0:
        return CandidateResult(
            ok=False,
            error=(completed.stderr or "non-zero exit").strip()[-400:],
            unknown_columns=unknown,
        )

    try:
        lines = [ln for ln in completed.stdout.splitlines() if ln.strip()]
        figure = json.loads(lines[-1])
    except (json.JSONDecodeError, IndexError):
        return CandidateResult(
            ok=False, error="stdout was not valid JSON", unknown_columns=unknown
        )

    traces = figure.get("data") or []
    figure_type = traces[0].get("type") if traces and isinstance(traces[0], dict) else None
    if figure_type is None and traces:
        figure_type = "scatter"  # px.line omits an explicit type
    if figure_type is None:
        return CandidateResult(
            ok=False, error="figure has no traces (rendered nothing)", unknown_columns=unknown
        )
    return CandidateResult(
        ok=not unknown, figure_type=figure_type, unknown_columns=unknown
    )
