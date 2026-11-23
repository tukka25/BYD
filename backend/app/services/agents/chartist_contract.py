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

# The turn that sends failed code back to the model, after its own answer. Every
# chart is the model's: when its code breaks the contract or fails to run, it is
# shown what went wrong and fixes it itself. Nothing else ever draws the chart.
CHARTIST_REPAIR_TEMPLATE = """That code did not work:
{problem}

Reply with the whole corrected code, ending with print(fig.to_json())."""

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
# rejects these (on lowercased code) again at run time, after this check has
# already sent any match back to the model. tests/test_contract_sync.py fails if
# the two lists drift apart.
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


# Each rule as the model is told it when its code breaks it: what is wrong and
# what to do instead, never the bare enum value.
VIOLATION_WORDS: dict[ContractViolation, str] = {
    ContractViolation.SYNTAX_ERROR: "it is not valid Python",
    ContractViolation.NO_FIGURE: "it never assigns the chart to `fig`",
    ContractViolation.NO_JSON_PRINT: "it must end with print(fig.to_json()), printed exactly once",
    ContractViolation.CALLS_SHOW: "it calls fig.show(); end with print(fig.to_json()) instead",
    ContractViolation.READS_DATA: "it reads a file or a URL; use `df`, which is already loaded",
    ContractViolation.USES_MATPLOTLIB: "it uses matplotlib; draw the chart with plotly",
    ContractViolation.CREATES_DATAFRAME: "it builds a DataFrame from scratch; use the data in `df`",
    ContractViolation.WRITES_FILE: "it writes a file; the only output allowed is print(fig.to_json())",
    ContractViolation.BLOCKED_IMPORT: "it uses something that is not allowed (os, subprocess, open, eval, exec or __import__)",
    ContractViolation.EXTRA_PRINT: "it prints something besides the figure; print(fig.to_json()) must be the only print",
}


def problems_with(code: str) -> list[str]:
    """What breaks the contract, in words the model can act on; [] when nothing does."""
    problems = []
    for violation in validate_chart_code(code):
        if violation is ContractViolation.SYNTAX_ERROR:
            problems.append(_syntax_problem(code))
        else:
            problems.append(VIOLATION_WORDS[violation])
    return problems


# Said to the model when a line it drew runs back and forth. The planning
# measurement counts repairs by these words, so change both together.
REPEATED_X_FIX = "each x value should appear once per line: aggregate y for each x and sort by x"


def _drawn_as_line(trace: dict) -> bool:
    """A scatter trace that Plotly draws with lines: its mode includes "lines",
    it is a stacked area, or it has no mode (Plotly's reference: "lines+markers"
    under 20 points when not stacked, otherwise "lines"). Markers-only traces
    may repeat x, and a closed shape (fill="toself", such as a band) goes back
    over its x by design."""
    if trace.get("type", "scatter") not in ("scatter", "scattergl") or trace.get("fill") == "toself":
        return False
    mode = trace.get("mode")
    return bool(trace.get("stackgroup")) or mode is None or "lines" in str(mode)


def figure_problems(figure: dict) -> list[str]:
    """What a drawn figure gets wrong, in words the model can act on; [] when nothing does.

    Expects plain lists: decode Plotly's typed arrays first, as
    workflow.run_on_frame does. One rule today: a line on which one x value
    carries more than one y value runs back and forth across the chart (rows of
    two keys, drawn as one line over one of them). The same x with the same y
    draws over itself and is fine. An x or y that cannot be read is not a problem.
    """
    problems = []
    for n, trace in enumerate((figure or {}).get("data") or [], 1):
        if not isinstance(trace, dict) or not _drawn_as_line(trace):
            continue
        xs, ys = trace.get("x"), trace.get("y")
        if not isinstance(xs, list) or not isinstance(ys, list) or len(xs) != len(ys):
            continue
        points = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
        seen: dict = {}
        try:
            for x, y in points:
                seen.setdefault(tuple(x) if isinstance(x, list) else x, set()).add(
                    tuple(y) if isinstance(y, list) else y)
        except TypeError:
            continue
        if any(len(values) > 1 for values in seen.values()):
            name = str(trace.get("name") or "").strip() or f"trace {n}"
            problem = (f"the line '{name}' has {len(points):,} points but only {len(seen):,} x values, "
                       f"so it runs back and forth: {REPEATED_X_FIX}")
            if trace.get("mode") is None and not trace.get("stackgroup"):
                problem += " (it has no mode, so Plotly draws it as a line; for a scatter, set mode='markers')"
            problems.append(problem)
    return problems


def _syntax_problem(code: str) -> str:
    text = (code or "").strip()
    if not text:
        return "the reply had no code"
    try:
        ast.parse(text)
    except SyntaxError as exc:
        return f"{VIOLATION_WORDS[ContractViolation.SYNTAX_ERROR]}: {exc.msg} (line {exc.lineno})"
    return VIOLATION_WORDS[ContractViolation.SYNTAX_ERROR]


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
