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
_QUOTED = re.compile(r"""['"]([^'"]{1,80})['"]""")

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
    """Quoted identifier-ish strings that are not in the schema."""
    known = {str(c) for c in columns}
    known_lower = {c.lower() for c in known}
    out = []
    for value in sorted({m.group(1) for m in _QUOTED.finditer(code)}):
        if value in known or value.lower() in known_lower:
            continue
        if value.lower() in _NOT_COLUMNS:
            continue
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9 _]{1,40}", value):
            out.append(value)
    return out


def run_candidate(code: str, df_csv: str, timeout_seconds: int = 20) -> CandidateResult:
    violations = [v.value for v in validate_chart_code(code)]
    if violations:
        return CandidateResult(ok=False, violations=violations)

    try:
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
        figure = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return CandidateResult(
            ok=False, error="stdout was not valid JSON", unknown_columns=unknown
        )

    traces = figure.get("data") or []
    figure_type = traces[0].get("type") if traces and isinstance(traces[0], dict) else None
    if figure_type is None and traces:
        figure_type = "scatter"  # px.line omits an explicit type
    return CandidateResult(
        ok=not unknown, figure_type=figure_type, unknown_columns=unknown
    )
