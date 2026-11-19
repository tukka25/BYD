"""The chartist output contract.

Single source of truth for what the chartist is told and what its output must
look like. The fine-tuning dataset is built against these exact strings;
chartist-finetune/contract.py loads this module by path so there is no copy.
"""
from __future__ import annotations

import ast
import re
from enum import Enum

CHARTIST_SYSTEM_PROMPT = """You are a Plotly code generator. You receive a pandas DataFrame named `df` that is already loaded, and its schema. You write Python that builds one Plotly figure from it.

Hard rules:
- `df` already exists. Never create it. Never call pd.read_csv, pd.read_excel, pd.read_json, px.data.*, or fetch any URL.
- Use only the column names given in the schema. Never invent a column.
- Assign the figure to a variable named `fig`.
- End the script with exactly: print(fig.to_json())
- Never call fig.show(). Never save a file. Never use matplotlib.
- Output executable Python only. No markdown fences, no explanation, no commentary."""

CHARTIST_USER_TEMPLATE = """Task: {task}

DataFrame `df` schema:
columns: {columns}
dtypes: {dtypes}
first rows: {sample_rows}

Write the Python now."""


class ContractViolation(str, Enum):
    SYNTAX_ERROR = "syntax_error"
    NO_FIGURE = "no_figure_assignment"
    NO_JSON_PRINT = "missing_json_print"
    CALLS_SHOW = "calls_fig_show"
    READS_DATA = "reads_external_data"
    USES_MATPLOTLIB = "uses_matplotlib"
    CREATES_DATAFRAME = "creates_dataframe"
    WRITES_FILE = "writes_file"
    BLOCKED_IMPORT = "blocked_import"
    EXTRA_PRINT = "extra_print"


# Deliberately conservative: any URL literal is rejected, even in a title or
# hover text, because this is also the filter for the training set. Case-sensitive
# on purpose (identifiers are); bare `open(` only, not `Open(` or `x.open(`.
_READS_DATA = re.compile(
    r"\b(?:pd|pandas)\s*\.\s*read_\w+"
    r"|from\s+pandas\s+import\s+[^\n]*read_"
    r"|\bpx\s*\.\s*data\s*\."
    r"|https?://"
    r"|(?<![\w.])open\s*\("
    r"|\brequests\s*\."
    r"|\burllib\b"
)
# Construction only; `df = df.groupby(...)` and other reassignments are fine.
_CREATES_DF = re.compile(r"\b(?:pd|pandas)\s*\.\s*DataFrame\s*\(")
# `to_json` is intentionally absent: print(fig.to_json()) is required.
_WRITES_FILE = re.compile(
    r"\.\s*(?:write_html|write_image|write_json|to_csv|to_excel|to_parquet|to_pickle)\s*\("
    r"|\bsavefig\s*\("
)
# Mirror of SafeExecutor.blocked_patterns in backend/app/utils/executor.py, which
# rejects these (on lowercased code) AFTER the chartist's fallback decision has
# been made. tests/test_contract_sync.py fails if the two lists drift apart.
BLOCKED_PATTERNS = [
    r"\bimport\s+os\b",
    r"\bimport\s+subprocess\b",
    r"\bfrom\s+os\s+import\b",
    r"\bfrom\s+subprocess\s+import\b",
    r"\bopen\(",
    r"\beval\(",
    r"\bexec\(",
    r"\b__import__\(",
]
_FIG_ASSIGN = re.compile(r"^\s*fig\s*=", re.MULTILINE)


def _is_json_print(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
        and len(node.args) == 1
        and not node.keywords
        and ast.unparse(node.args[0]) == "fig.to_json()"
    )


def _print_profile(tree: ast.Module) -> tuple[int, int, bool]:
    """(print(fig.to_json()) calls, any other print calls, last statement is the JSON print).

    Production json.loads the whole of stdout, so any second line of output
    breaks it; the JSON print must be the only one and the final statement.
    """
    json_prints = other_prints = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            if _is_json_print(node):
                json_prints += 1
            else:
                other_prints += 1
    last = tree.body[-1] if tree.body else None
    last_ok = isinstance(last, ast.Expr) and _is_json_print(last.value)
    return json_prints, other_prints, last_ok


def validate_chart_code(code: str) -> list[ContractViolation]:
    """Static contract checks. An empty list means compliant."""
    text = (code or "").strip()
    if not text:
        return [ContractViolation.SYNTAX_ERROR]
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [ContractViolation.SYNTAX_ERROR]

    violations: list[ContractViolation] = []
    lowered = text.lower()
    if not _FIG_ASSIGN.search(text):
        violations.append(ContractViolation.NO_FIGURE)
    json_prints, other_prints, last_is_json_print = _print_profile(tree)
    if json_prints != 1 or not last_is_json_print:
        violations.append(ContractViolation.NO_JSON_PRINT)
    if other_prints:
        violations.append(ContractViolation.EXTRA_PRINT)
    if any(re.search(pattern, lowered) for pattern in BLOCKED_PATTERNS):
        violations.append(ContractViolation.BLOCKED_IMPORT)
    if "fig.show(" in lowered:
        violations.append(ContractViolation.CALLS_SHOW)
    if _READS_DATA.search(text):
        violations.append(ContractViolation.READS_DATA)
    if _CREATES_DF.search(text):
        violations.append(ContractViolation.CREATES_DATAFRAME)
    if _WRITES_FILE.search(text):
        violations.append(ContractViolation.WRITES_FILE)
    if "matplotlib" in lowered or re.search(r"\bplt\s*\.", lowered):
        violations.append(ContractViolation.USES_MATPLOTLIB)
    return violations
