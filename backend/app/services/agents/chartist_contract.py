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

# The most tokens the chartist may generate. Production, the local eval and the
# A/B harness all read it from here: the eval used to stop at 800 while the live
# call allowed 1024, so a long but valid answer could fail in the eval and pass
# in the app, and the eval would score a failure the user never saw.
CHARTIST_MAX_TOKENS = 1024


# The planner decides a chart type and, by default, nobody downstream is told.
# `chart_type_hint` is the wire: it turns the planner's label into the exact text
# appended to the Task line. Two forms, because a sentence and a metadata field
# read differently and only measurement can say which a 9B model follows better:
#
#   "inline"     Task: <question> Show it as an area chart.
#   "directive"  Task: <question>\n\nChart type: area
#
# These strings live here rather than in the agent so that the dataset exporter
# can import the same ones through `chartist-finetune/contract.py`. A hint the
# model was trained on and a hint the app sends must be byte-identical, or the
# live prompt is a shape the fine-tune never saw -- which is the whole reason the
# chart type was dropped from the prompt in the first place.
#
# Keys are the planner's closed label set (`planner.CHART_TYPES`). Nothing else
# is accepted: an unrecognised label returns no hint rather than a guess.
CHART_TYPE_PHRASE = {
    "bar": "a bar chart",
    "line": "a line chart",
    "scatter": "a scatter plot",
    "pie": "a pie chart",
    "histogram": "a histogram",
    "box": "a box plot",
    "heatmap": "a heatmap",
    "area": "an area chart",
    "treemap": "a treemap",
    "funnel": "a funnel chart",
    "waterfall": "a waterfall chart",
    "indicator": "a single-number KPI indicator",
}

CHART_TYPE_LABEL = {
    "bar": "bar",
    "line": "line",
    "scatter": "scatter",
    "pie": "pie",
    "histogram": "histogram",
    "box": "box",
    "heatmap": "heatmap",
    "area": "area",
    "treemap": "treemap",
    "funnel": "funnel",
    "waterfall": "waterfall",
    "indicator": "KPI indicator",
}

HINT_STYLES = ("off", "inline", "directive")

# A question that already says which chart it wants. The architect writes every
# dashboard question this way ("... as a line chart", "... as a single big KPI
# number"), so without this check the dashboard path would be told twice -- and
# when the planner falls back, told two different things ("as a line chart.
# Show it as a bar chart."). Bare "line", "area" and "pie" are excluded on
# purpose: "production line", "sales area" and "apple pie" are column words, and
# 48 of the 82 training questions containing a chart word only used "line" in
# that sense. A false positive here costs a skipped hint; a false negative costs
# a contradictory prompt, so the pattern leans towards matching.
_NAMES_A_CHART = re.compile(
    r"\b(?:bar|line|area|pie|donut|doughnut|column|stacked)\s+(?:chart|graph|plot)s?\b"
    r"|\b(?:scatter\s*plots?|scatterplots?|scatter|box\s*plots?|boxplots?|histograms?|"
    r"heat\s*maps?|heatmaps?|treemaps?|sunbursts?|funnels?|waterfalls?|gauges?|kpis?|indicators?)\b",
    re.IGNORECASE,
)


def names_a_chart(task: str) -> bool:
    """True if the question itself already asks for a particular chart type."""
    return bool(_NAMES_A_CHART.search(task or ""))


def chart_type_hint(task: str, viz_type: str, style: str) -> str:
    """Return `task` with the planner's chart type attached, per `style`.

    Returns `task` unchanged for an unknown style, an empty task, a chart type
    outside the planner's label set, or a question that already names its chart.
    """
    task = (task or "").strip()
    key = (viz_type or "").strip().lower()
    if style not in ("inline", "directive") or not task or names_a_chart(task):
        return task
    if style == "directive":
        label = CHART_TYPE_LABEL.get(key)
        return f"{task}\n\nChart type: {label}" if label else task
    phrase = CHART_TYPE_PHRASE.get(key)
    if not phrase:
        return task
    # A second sentence needs the first one to end, and most questions have no
    # terminal punctuation ("Monthly MRR trend for the whole business").
    if task[-1] not in ".?!":
        task += "."
    return f"{task} Show it as {phrase}."


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


def render_spec(spec: dict) -> str:
    """The chartist's task text for one chart plan.

    The dashboard planner hands the chartist an exact plan, so it no longer has
    to guess the chart type and columns from a question. The v2 training rows are
    built with this same function (re-exported by chartist-finetune/contract.py):
    the plan a model was trained on and the plan the app sends are the same text.
    """
    lines = [str(spec.get("question") or spec.get("title") or "").strip(), "", "Chart plan:"]
    lines.append(f"- chart: {spec['chart']}")
    agg = str(spec.get("agg") or "")
    for key in ("x", "y", "group"):
        value = str(spec.get(key) or "").strip()
        if not value:
            continue
        if key == "y" and agg not in ("", "none"):
            lines.append(f"- y: {value} ({agg})")
        else:
            lines.append(f"- {key}: {value}")
    if not str(spec.get("y") or "").strip() and agg == "count":
        lines.append("- y: row count")
    if spec.get("grain"):
        lines.append(f"- time grain: {spec['grain']}")
    sort, top = str(spec.get("sort") or ""), int(spec.get("top_n") or 0)
    if sort or top:
        parts = (["descending" if sort == "desc" else "ascending"] if sort else []) + (
            [f"top {top}"] if top else []
        )
        lines.append(f"- order: {', '.join(parts)}")
    title = str(spec.get("title") or "").strip()
    if title:
        lines.append(f"- title: {title}")
    return "\n".join(lines)
