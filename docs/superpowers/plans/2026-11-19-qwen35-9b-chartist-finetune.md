# Qwen3.5-9B Chartist Fine-Tune Implementation Plan (schema-first, rev 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a Qwen3.5-9B LoRA adapter that writes chartist-contract-compliant Plotly code from a dataframe schema and a natural question, and prove it beats the base model on a frozen, schema-disjoint test set.

**Architecture:** Generation is **schema-first**, not docs-first. We synthesize business-shaped table schemas, materialize a real CSV per schema, generate natural dashboard questions against each, and only then generate code targets — every target gated by actually executing it against that CSV and checking the resulting figure type. The test set is built and frozen **before** any training data exists, and needs no gold answers because execution is the oracle. The scraped Plotly-docs rows survive only as a small base layer for chart-type breadth.

**Tech Stack:** Python 3.13 in a project venv, `anthropic` SDK 2.10 (Batch API), `mlx` / `mlx-lm` on Apple Silicon, pandas + plotly for the execution oracle, Qwen3.5-9B.

## Global Constraints

- **Hardware:** MacBook Pro, Apple M2 Pro, 32 GB unified memory, ~496 GB free. GPU addresses ~24 GB by default. ~200 GB/s bandwidth — measure throughput, never assume it.
- **Python:** the host is PEP 668 externally managed. **Every command uses the project venv at `chartist-finetune/.venv/bin/python`.** A bare `pip install` fails.
- **Credentials:** the key lives in `/Users/atukka/Desktop/BYD/.env` as **`CLAUDE_API_KEY`**, which is *not* a name the Anthropic SDK resolves. Scripts must read it and pass it to `anthropic.Anthropic(api_key=...)` via the shared helper in Task 2. `.env` is already gitignored (`.gitignore:34`). **Never print, log, or commit the key value.**
- **Models, exactly:** `claude-haiku-5-5` for schemas and questions; `claude-sonnet-5-5` for code targets. Both verified available on this key. The code target is what the student model imitates, so it never drops to Haiku.
- **Pricing for every estimate here:** Sonnet 5.5 $2.00/MTok in, $10.00/MTok out, cache reads $0.10/MTok. Haiku 5.5 $0.10/MTok in, $0.50/MTok out. Batch API runs at 50%. Thinking tokens bill as output.
- **Budget: $30 total, allocated — ~$1 test set, ~$14 train round 1, ~$15 held in reserve.** The reserve is not optional slack: it is spent only after the first eval, against the measured failure mode. No task may exceed its line without reporting the new projection first.
- **Batch API constraints that shape the code:** a batch request cannot set `stream`, `speed`, `fallbacks`, or `max_tokens: 0`. With no server-side `fallbacks`, `stop_reason == "refusal"` is handled per result. Results return in arbitrary order — key by `custom_id`. Limits: 100,000 requests / 256 MB per batch; usually under an hour, max 24; results readable for 29 days.
- **Sonnet 5.5 / Haiku 5.5 API surface:** thinking is adaptive and on by default; `thinking: {"type": "disabled"}` returns 400 on Sonnet 5.5. Control spend with `output_config={"effort": ...}` — `"low"` for routine rows, `"medium"` for the hard subset. No assistant prefill. Forced `tool_choice` `any`/`tool` returns 400, so every structured response uses `output_config.format`.
- **The chartist contract** (fixed): generated code receives a preloaded DataFrame named `df`; never reads a file or URL; never calls `fig.show()`; assigns `fig`; ends with `print(fig.to_json())`.
- **Leakage rule:** splits are disjoint **by schema id**, never by row. A schema and every question and target derived from it live in exactly one split.
- **Task 11's serving step depends on** `docs/superpowers/plans/2026-11-19-platform-correctness.md` Tasks 4-8 being merged (it edits `get_llms()`, which that plan introduces). Tasks 1-10 here are self-contained.
- Commit after every task. Never commit `.env`, `.venv/`, `runs/`, or `models/`.

## Budget ledger

Keep this table current in `chartist-finetune/README.md` as tasks land. A task that overruns its line stops and reports.

| Line | Task | Model | Budgeted | Actual |
|---|---|---|---|---|
| Schemas | 3 | haiku-5-5 | $0.30 | |
| Questions | 4 | haiku-5-5 | $0.70 | |
| Test set freeze | 5 | — (reuses 3+4) | $0.00 | |
| Train targets, best-of-k | 6 | sonnet-5-5 | $14.00 | |
| Reserve (round 2, post-eval) | — | tbd by eval | $15.00 | |

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `backend/app/services/agents/chartist_contract.py` | Canonical `CHARTIST_SYSTEM_PROMPT`, `CHARTIST_USER_TEMPLATE`, `validate_chart_code()`. The one place the contract is written down. |
| `backend/tests/test_chartist_contract.py` | Proves the validator accepts compliant code and rejects each violation. |
| `chartist-finetune/.gitignore`, `requirements.txt`, `pyproject.toml` | Project setup. |
| `chartist-finetune/client.py` | Reads `CLAUDE_API_KEY` from `.env`, builds the SDK client, and holds the batch submit/poll/collect loop and the cost accounting. Every paid task goes through it. |
| `chartist-finetune/contract.py` | Loads the backend contract module by path — no copy to drift. |
| `chartist-finetune/executor.py`, `_candidate_runner.py` | The execution oracle: run a candidate against a real CSV, report contract violations, figure type, and unknown columns. |
| `chartist-finetune/chart_types.py` | The chart-type quota and the hard-case mix. |
| `chartist-finetune/gen_schemas.py` | Haiku → schema specs → materialized CSVs. |
| `chartist-finetune/gen_questions.py` | Haiku → natural questions + `expected_chart_type` per schema. |
| `chartist-finetune/freeze_testset.py` | Builds and freezes the test set from the reserved schemas. No gold answers. |
| `chartist-finetune/gen_targets.py` | Sonnet → code targets with adaptive best-of-k and the execution gate. |
| `chartist-finetune/rewrite_docs.py` | The deterministic docs-row rewrite, now only a base layer. |
| `chartist-finetune/export_mlx.py` | Merge + schema-disjoint splits in mlx-lm chat format. |
| `chartist-finetune/evaluate.py` | Generate from a model, score by execution, break results down per chart type. |
| `chartist-finetune/tests/` | Unit tests for the validator, the quota, the rewrite, and contract reachability. |
| `chartist-finetune/README.md` | Run order, the budget ledger, the measured costs and eval numbers. |

**Modified:** `backend/app/services/agents/chartist.py` (Task 1), and in Task 11 `backend/app/core/config.py`, `backend/app/services/qwen_slm.py`, `backend/app/services/agents/workflow.py`, `backend/requirements.txt`, `backend/.env.example`.

**Dropped from rev 1:** `build_baseline.py` and `augment.py`. The docs-first baseline measured a hard ceiling of 715 rows from 150 pages with 100% templated prompts and only 18% dashboard-core chart types; prompt-paraphrase augmentation of that set fixed the wrong variable.

**Out of scope:** fine-tuning the planner or the detective; pandas-analysis beyond charts; GGUF conversion for Ollama.

---

### Task 1: The contract, in one place

Today the contract lives in three disagreeing places: the prompt text in `chartist.py:14-37`, the rejection rules in `_sanitize_generated_code` at `chartist.py:113-131`, and the JSON check in `executor.py`. Everything downstream is built against it, so first make there be one.

**Files:**
- Create: `backend/app/services/agents/chartist_contract.py`, `backend/tests/test_chartist_contract.py`
- Modify: `backend/app/services/agents/chartist.py`

**Interfaces:**
- Produces: `CHARTIST_SYSTEM_PROMPT: str`; `CHARTIST_USER_TEMPLATE: str` (`.format` fields `task`, `columns`, `dtypes`, `sample_rows`); `ContractViolation(str, Enum)` with `SYNTAX_ERROR`, `NO_FIGURE`, `NO_JSON_PRINT`, `CALLS_SHOW`, `READS_DATA`, `USES_MATPLOTLIB`; `validate_chart_code(code: str) -> list[ContractViolation]` where `[]` means compliant.
- Consumed by: every later task, and by the live chartist.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_chartist_contract.py
from app.services.agents.chartist_contract import (
    CHARTIST_SYSTEM_PROMPT,
    CHARTIST_USER_TEMPLATE,
    ContractViolation,
    validate_chart_code,
)

COMPLIANT = (
    "import plotly.express as px\n"
    "fig = px.bar(df, x='Category', y='Value')\n"
    "print(fig.to_json())\n"
)


def test_accepts_compliant_code():
    assert validate_chart_code(COMPLIANT) == []


def test_rejects_fig_show():
    violations = validate_chart_code(COMPLIANT.replace("print(fig.to_json())", "fig.show()"))
    assert ContractViolation.CALLS_SHOW in violations
    assert ContractViolation.NO_JSON_PRINT in violations


def test_rejects_reading_data():
    code = (
        "import pandas as pd\nimport plotly.express as px\n"
        "df = pd.read_csv('https://example.com/d.csv')\n"
        "fig = px.bar(df, x='a', y='b')\nprint(fig.to_json())\n"
    )
    assert ContractViolation.READS_DATA in validate_chart_code(code)


def test_rejects_matplotlib():
    assert ContractViolation.USES_MATPLOTLIB in validate_chart_code(
        "import matplotlib.pyplot as plt\nplt.plot([1,2])\n"
    )


def test_rejects_missing_figure_assignment():
    assert ContractViolation.NO_FIGURE in validate_chart_code(
        "import plotly.express as px\nprint(px.bar(df).to_json())\n"
    )


def test_rejects_syntax_error():
    assert validate_chart_code("fig = (((") == [ContractViolation.SYNTAX_ERROR]


def test_user_template_has_the_schema_fields():
    rendered = CHARTIST_USER_TEMPLATE.format(
        task="t", columns="['a']", dtypes="{'a': 'int64'}", sample_rows="[{'a': 1}]"
    )
    assert "['a']" in rendered and "int64" in rendered


def test_system_prompt_states_the_hard_rules():
    assert "print(fig.to_json())" in CHARTIST_SYSTEM_PROMPT
    lowered = CHARTIST_SYSTEM_PROMPT.lower()
    assert "fig.show" in lowered and "pd.read_csv" in lowered
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /Users/atukka/Desktop/BYD/backend && python3 -m pytest tests/test_chartist_contract.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.agents.chartist_contract'`. If pytest itself is not configured yet, add `backend/pyproject.toml` with `[tool.pytest.ini_options]` / `testpaths = ["tests"]` / `pythonpath = ["."]` — the platform-correctness plan's Task 1 creates it, and duplicating those three lines here is cheaper than taking a dependency on that plan.

- [ ] **Step 3: Implement**

```python
# backend/app/services/agents/chartist_contract.py
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


_READS_DATA = re.compile(
    r"\b(?:pd|pandas)\s*\.\s*read_\w+|\bpx\s*\.\s*data\s*\.|https?://|\bopen\s*\(",
    re.IGNORECASE,
)
_FIG_ASSIGN = re.compile(r"^\s*fig\s*=", re.MULTILINE)


def validate_chart_code(code: str) -> list[ContractViolation]:
    """Static contract checks. An empty list means compliant."""
    text = (code or "").strip()
    if not text:
        return [ContractViolation.SYNTAX_ERROR]
    try:
        ast.parse(text)
    except SyntaxError:
        return [ContractViolation.SYNTAX_ERROR]

    violations: list[ContractViolation] = []
    lowered = text.lower()
    if not _FIG_ASSIGN.search(text):
        violations.append(ContractViolation.NO_FIGURE)
    if "print(fig.to_json())" not in text:
        violations.append(ContractViolation.NO_JSON_PRINT)
    if "fig.show(" in lowered:
        violations.append(ContractViolation.CALLS_SHOW)
    if _READS_DATA.search(text):
        violations.append(ContractViolation.READS_DATA)
    if "matplotlib" in lowered or re.search(r"\bplt\s*\.", lowered):
        violations.append(ContractViolation.USES_MATPLOTLIB)
    return violations
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Users/atukka/Desktop/BYD/backend && python3 -m pytest tests/test_chartist_contract.py -v
```

Expected: 8 PASS.

- [ ] **Step 5: Point the live chartist at it**

In `backend/app/services/agents/chartist.py` add:

```python
import logging

from app.services.agents.chartist_contract import (
    CHARTIST_SYSTEM_PROMPT,
    CHARTIST_USER_TEMPLATE,
    ContractViolation,
    validate_chart_code,
)

logger = logging.getLogger(__name__)
```

Replace the `ChatPromptTemplate.from_messages([...])` block in `__init__` with:

```python
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", CHARTIST_SYSTEM_PROMPT),
            ("human", CHARTIST_USER_TEMPLATE),
        ])
```

Replace the `self.chain.invoke({...})` call in `generate_code` with:

```python
            raw = self.chain.invoke({
                "task": self._task_description(task_plan, dataframe_plan),
                "columns": str(data_context.get("columns", [])),
                "dtypes": str(data_context.get("dtypes", {})),
                "sample_rows": str(data_context.get("sample", [])),
            })
```

Add the helper so plan hints still reach the model:

```python
    def _task_description(
        self,
        task_plan: Dict[str, Any],
        dataframe_plan: Optional[Dict[str, Any]],
    ) -> str:
        parts = [
            f"Build a {task_plan.get('visualization_type', 'bar')} chart.",
            f"Style: {task_plan.get('style_config', {})}.",
        ]
        plan = dataframe_plan or {}
        if plan.get("selected_columns"):
            parts.append(f"Prefer these columns: {plan['selected_columns']}.")
        if plan.get("plotly_ready_spec"):
            parts.append(f"Suggested encoding: {plan['plotly_ready_spec']}.")
        if plan.get("missing_fields"):
            parts.append(f"Unavailable, do not use: {plan['missing_fields']}.")
        return " ".join(parts)
```

In `_sanitize_generated_code`, keep the fence-stripping and prose-stripping, then replace the matplotlib/`plt.`/`fig.show(` branch, the `print(fig.to_json())` branch, and the trailing `ast.parse` block with:

```python
        violations = validate_chart_code(code)
        if ContractViolation.NO_JSON_PRINT in violations and "fig =" in code:
            code = f"{code}\nprint(fig.to_json())"
            violations = validate_chart_code(code)
        if violations:
            logger.warning("[chartist] contract violations %s, using fallback", violations)
            return self._fallback_plotly_code(data_context, viz_type)
        return code
```

- [ ] **Step 6: Verify nothing regressed**

```bash
cd /Users/atukka/Desktop/BYD/backend && python3 -m pytest -v
```

Expected: all PASS. `_fallback_plotly_code` already emits compliant code.

- [ ] **Step 7: Commit**

```bash
cd /Users/atukka/Desktop/BYD && git add backend/app/services/agents/chartist_contract.py backend/app/services/agents/chartist.py backend/tests/test_chartist_contract.py backend/pyproject.toml && git commit -m "refactor(chartist): extract the output contract into one module

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Scaffold, the execution oracle, and the API client

Three things every paid task depends on: a venv-based project, a validator that proves a chart renders, and one client helper that reads `CLAUDE_API_KEY` and accounts for spend.

**Files:**
- Create: `chartist-finetune/{.gitignore,requirements.txt,pyproject.toml,contract.py,executor.py,_candidate_runner.py,client.py,chart_types.py}`
- Create: `chartist-finetune/tests/{__init__.py,test_contract_sync.py,test_executor.py,test_chart_types.py}`

**Interfaces:**
- Produces:
  - `contract.py` re-exporting the four backend names, loaded by path.
  - `executor.run_candidate(code: str, df_csv: str, timeout_seconds: int = 20) -> CandidateResult` with fields `ok: bool`, `violations: list[str]`, `figure_type: str | None`, `error: str | None`, `unknown_columns: list[str]`.
  - `client.get_client() -> anthropic.Anthropic`
  - `client.run_batch(requests: list, label: str, poll_seconds: int = 30) -> BatchOutcome` with fields `payloads: dict[str, dict]`, `usage: dict`, `refusals: int`, `batch_id: str`.
  - `client.price(usage: dict, model: str, batched: bool = True) -> float`
  - `chart_types.QUOTA: dict[str, float]` and `chart_types.HARD_CASE_KINDS: list[str]`.

- [ ] **Step 1: Scaffold (the venv already exists from session setup)**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && mkdir -p tests data runs && touch tests/__init__.py && printf '.venv/\nruns/\nmodels/\n__pycache__/\n*.pyc\n.env\n' > .gitignore && printf 'anthropic>=2.10.0\npandas\nplotly\nopenpyxl\npytest\n' > requirements.txt && printf '[tool.pytest.ini_options]\ntestpaths = ["tests"]\npythonpath = ["."]\naddopts = "-q"\n' > pyproject.toml
```

- [ ] **Step 2: Write `contract.py` and its reachability test**

```python
# chartist-finetune/contract.py
"""Loads the backend chartist contract by path, so there is no copy to drift."""
from __future__ import annotations

import importlib.util
from pathlib import Path

BACKEND_CONTRACT = (
    Path(__file__).resolve().parent.parent
    / "backend/app/services/agents/chartist_contract.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("chartist_contract", BACKEND_CONTRACT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BACKEND_CONTRACT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_backend = _load()
CHARTIST_SYSTEM_PROMPT = _backend.CHARTIST_SYSTEM_PROMPT
CHARTIST_USER_TEMPLATE = _backend.CHARTIST_USER_TEMPLATE
ContractViolation = _backend.ContractViolation
validate_chart_code = _backend.validate_chart_code
```

```python
# chartist-finetune/tests/test_contract_sync.py
from contract import BACKEND_CONTRACT, CHARTIST_SYSTEM_PROMPT, validate_chart_code


def test_backend_contract_is_reachable():
    assert BACKEND_CONTRACT.is_file(), f"{BACKEND_CONTRACT} missing — run Task 1 first"


def test_contract_loads_and_works():
    assert "print(fig.to_json())" in CHARTIST_SYSTEM_PROMPT
    assert validate_chart_code("fig = 1\nprint(fig.to_json())\n") == []
```

- [ ] **Step 3: Write the chart-type quota and its test**

The quota exists because the scraped data was 18% dashboard-core and missing area/bubble/gauge/indicator entirely. Here we choose the mix instead of inheriting it.

```python
# chartist-finetune/chart_types.py
"""The chart mix we choose, rather than the one the Plotly docs happened to have."""
from __future__ import annotations

QUOTA: dict[str, float] = {
    "bar": 0.15,
    "line": 0.15,
    "grouped_or_stacked_bar": 0.10,
    "scatter": 0.10,
    "pie_or_donut": 0.08,
    "area": 0.08,
    "histogram": 0.07,
    "box": 0.07,
    "heatmap": 0.07,
    "time_series": 0.06,
    "treemap_funnel_waterfall": 0.05,
    "gauge_or_indicator": 0.02,
}

# Plotly trace types each bucket may legitimately produce, for the eval's
# chart-type match check.
TRACE_TYPES: dict[str, set[str]] = {
    "bar": {"bar"},
    "line": {"scatter", "scattergl"},
    "grouped_or_stacked_bar": {"bar"},
    "scatter": {"scatter", "scattergl"},
    "pie_or_donut": {"pie"},
    "area": {"scatter", "scattergl"},
    "histogram": {"histogram", "bar"},
    "box": {"box"},
    "heatmap": {"heatmap", "histogram2d"},
    "time_series": {"scatter", "scattergl", "bar"},
    "treemap_funnel_waterfall": {"treemap", "funnel", "waterfall", "sunburst"},
    "gauge_or_indicator": {"indicator"},
}

HARD_CASE_KINDS: list[str] = [
    "multi_column_aggregation",
    "date_parsing_and_resampling",
    "grouped_or_faceted",
    "missing_field",
    "ambiguous_question",
]

HARD_CASE_SHARE = 0.40


def allocate(total: int) -> dict[str, int]:
    """Split a row budget across the quota, preserving the total exactly."""
    counts = {k: int(total * v) for k, v in QUOTA.items()}
    shortfall = total - sum(counts.values())
    for key in sorted(QUOTA, key=lambda k: -QUOTA[k])[:shortfall]:
        counts[key] += 1
    return counts
```

```python
# chartist-finetune/tests/test_chart_types.py
from chart_types import QUOTA, TRACE_TYPES, allocate


def test_quota_sums_to_one():
    assert abs(sum(QUOTA.values()) - 1.0) < 1e-9


def test_every_bucket_has_trace_types():
    assert set(QUOTA) == set(TRACE_TYPES)
    assert all(TRACE_TYPES.values())


def test_allocate_preserves_the_total():
    for total in (100, 300, 1500, 7):
        counts = allocate(total)
        assert sum(counts.values()) == total


def test_allocate_covers_the_types_the_docs_data_lacked():
    counts = allocate(1500)
    for missing_in_docs in ("area", "gauge_or_indicator"):
        assert counts[missing_in_docs] > 0
```

- [ ] **Step 4: Write the failing executor test**

```python
# chartist-finetune/tests/test_executor.py
import pytest

from executor import run_candidate

COMPLIANT = (
    "import plotly.express as px\n"
    "fig = px.bar(df, x='Category', y='Value')\n"
    "print(fig.to_json())\n"
)


@pytest.fixture()
def csv_path(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("Category,Value\nA,10\nB,20\n", encoding="utf-8")
    return str(path)


def test_compliant_code_runs(csv_path):
    result = run_candidate(COMPLIANT, csv_path)
    assert result.ok is True
    assert result.figure_type == "bar"
    assert result.violations == []


def test_static_violation_short_circuits(csv_path):
    result = run_candidate(COMPLIANT.replace("print(fig.to_json())", "fig.show()"), csv_path)
    assert result.ok is False
    assert "calls_fig_show" in result.violations


def test_hallucinated_columns_reported(csv_path):
    code = (
        "import plotly.express as px\n"
        "fig = px.bar(df, x='Region', y='Revenue')\n"
        "print(fig.to_json())\n"
    )
    result = run_candidate(code, csv_path)
    assert result.ok is False
    assert set(result.unknown_columns) == {"Region", "Revenue"}


def test_runtime_error_captured(csv_path):
    code = COMPLIANT.replace("print(", "raise ValueError('boom')\nprint(")
    result = run_candidate(code, csv_path)
    assert result.ok is False
    assert "boom" in (result.error or "")


def test_timeout_captured(csv_path):
    result = run_candidate("while True:\n    pass\n", csv_path, timeout_seconds=3)
    assert result.ok is False
    assert "timed out" in (result.error or "").lower()
```

- [ ] **Step 5: Run it to verify it fails**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -m pytest -v
```

Expected: contract-sync and chart-type tests PASS; every executor test FAILS with `ModuleNotFoundError: No module named 'executor'`.

- [ ] **Step 6: Implement the executor**

```python
# chartist-finetune/executor.py
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
```

```python
# chartist-finetune/_candidate_runner.py
"""Subprocess entry point. Reads {"code", "data_path"} as JSON on stdin."""
from __future__ import annotations

import json
import socket
import sys


def main() -> int:
    job = json.loads(sys.stdin.read())
    import pandas as pd

    path = job["data_path"]
    df = pd.read_excel(path) if path.endswith((".xlsx", ".xls")) else pd.read_csv(path)

    def _deny(*args, **kwargs):
        raise OSError("network disabled")

    socket.socket = _deny  # type: ignore[assignment]
    socket.create_connection = _deny  # type: ignore[assignment]

    import plotly.express as px
    import plotly.graph_objects as go

    exec(
        compile(job["code"], "<candidate>", "exec"),
        {"df": df, "pd": pd, "px": px, "go": go, "json": json},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Implement the client helper**

The key never appears in a log line, a committed file, or a subprocess argument.

```python
# chartist-finetune/client.py
"""Anthropic client, batch runner, and cost accounting.

The key lives in <repo>/.env as CLAUDE_API_KEY, which the SDK does not resolve
on its own, so it is read here and passed explicitly. Never printed.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

REPO = Path(__file__).resolve().parent.parent
ENV_FILE = REPO / ".env"

SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"

PRICES = {  # USD per 1M tokens: (input, output, cache_read)
    SONNET: (2.00, 10.00, 0.10),
    HAIKU: (0.10, 0.50, 0.01),
}


def _read_key() -> str:
    if not ENV_FILE.is_file():
        raise RuntimeError(f"{ENV_FILE} not found")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() in {"CLAUDE_API_KEY", "ANTHROPIC_API_KEY"}:
            cleaned = value.strip().strip('"').strip("'")
            if cleaned:
                return cleaned
    raise RuntimeError("CLAUDE_API_KEY not set in .env")


def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=_read_key())


def cached_system(text: str) -> list[dict]:
    """System block with a cache breakpoint. All requests in a batch share it."""
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def json_request(
    custom_id: str,
    model: str,
    system: str,
    user: str,
    schema: dict,
    max_tokens: int,
    effort: str = "low",
) -> Request:
    return Request(
        custom_id=custom_id,
        params=MessageCreateParamsNonStreaming(
            model=model,
            max_tokens=max_tokens,
            system=cached_system(system),
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            messages=[{"role": "user", "content": user}],
        ),
    )


@dataclass
class BatchOutcome:
    batch_id: str
    payloads: dict[str, dict] = field(default_factory=dict)
    usage: dict = field(default_factory=lambda: {"input": 0, "output": 0, "cache_read": 0})
    refusals: int = 0
    errored: int = 0
    unparsed: int = 0


def run_batch(requests: list, label: str, poll_seconds: int = 30) -> BatchOutcome:
    """Submit, poll to completion, collect structured payloads keyed by custom_id."""
    client = get_client()
    batch = client.messages.batches.create(requests=requests)
    print(f"[{label}] batch {batch.id}: {len(requests)} requests", flush=True)

    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        print(
            f"[{label}] {batch.processing_status} "
            f"processing={batch.request_counts.processing} "
            f"succeeded={batch.request_counts.succeeded}",
            flush=True,
        )
        time.sleep(poll_seconds)

    outcome = BatchOutcome(batch_id=batch.id)
    outcome.errored = batch.request_counts.errored

    for result in client.messages.batches.results(batch.id):
        if result.result.type != "succeeded":
            continue
        message = result.result.message
        outcome.usage["input"] += message.usage.input_tokens
        outcome.usage["output"] += message.usage.output_tokens
        outcome.usage["cache_read"] += (
            getattr(message.usage, "cache_read_input_tokens", 0) or 0
        )
        if message.stop_reason == "refusal":
            outcome.refusals += 1
            continue
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            outcome.payloads[result.custom_id] = json.loads(text)
        except json.JSONDecodeError:
            outcome.unparsed += 1
    return outcome


def price(usage: dict, model: str, batched: bool = True) -> float:
    rate_in, rate_out, rate_cache = PRICES[model]
    billed_input = max(0, usage.get("input", 0) - usage.get("cache_read", 0))
    total = (
        billed_input / 1_000_000 * rate_in
        + usage.get("cache_read", 0) / 1_000_000 * rate_cache
        + usage.get("output", 0) / 1_000_000 * rate_out
    )
    return round(total * (0.5 if batched else 1.0), 4)


def record_spend(label: str, model: str, usage: dict, extra: dict | None = None) -> float:
    """Append a line to the ledger so the budget stays auditable."""
    cost = price(usage, model)
    ledger = Path("runs/spend.jsonl")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {"label": label, "model": model, "usage": usage, "cost_usd": cost,
                 **(extra or {})}
            )
            + "\n"
        )
    print(f"[{label}] cost ${cost:.4f} (batched)")
    return cost
```

- [ ] **Step 8: Run the tests**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -m pytest -v
```

Expected: 11 PASS.

- [ ] **Step 9: Verify the client reads the key without printing it**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -c "
import client
c = client.get_client()
print('client built, models reachable:', len([m.id for m in c.models.list(limit=5)]) > 0)
print('ledger pricing sanity, 1M in / 1M out sonnet batched: \$' + str(client.price({'input':1_000_000,'output':1_000_000,'cache_read':0}, client.SONNET)))
"
```

Expected: `client built, models reachable: True` and `$6.0`. No key material in the output.

- [ ] **Step 10: Commit**

```bash
cd /Users/atukka/Desktop/BYD && git add chartist-finetune/ && git commit -m "feat(finetune): scaffold with execution oracle, chart quota, and batch client

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Synthesize business schemas (Haiku, ~$0.30)

180 schemas: **60 reserved for the frozen test set, 120 for training.** The split is decided here and never revisited, so leakage is structurally impossible.

Column-name diversity is the point. The scraped data taught `gdpPercap` and `pop`; a model that memorizes those has learned nothing. Each concept must appear under several names across schemas.

**Files:**
- Create: `chartist-finetune/gen_schemas.py`
- Produces: `chartist-finetune/data/schemas.jsonl`, `chartist-finetune/data/fixtures/<schema_id>.csv`

**Interfaces:**
- Consumes: `client.run_batch`, `client.json_request`, `client.HAIKU`.
- Produces: one JSONL row per schema — `{"schema_id": str, "split": "test"|"train", "domain": str, "naming_style": str, "columns": [{"name","dtype","role","categories"?,"min"?,"max"?}], "fixture_csv": str}` where `dtype` is one of `date`, `int`, `float`, `category`, `bool`, and `role` is one of `dimension`, `measure`, `time`.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Synthesize business table schemas with Haiku, then materialize a CSV per schema."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd

import client

DOMAINS = [
    "retail store sales", "e-commerce orders", "SaaS subscription revenue",
    "SaaS churn and retention", "HR headcount and attrition", "recruiting pipeline",
    "marketing campaign performance", "web traffic and conversion",
    "customer support tickets", "call centre staffing", "warehouse inventory",
    "freight and logistics shipments", "delivery fleet telemetry",
    "manufacturing line output", "quality control defects", "energy consumption by site",
    "utility billing", "hospital clinic throughput", "patient appointment scheduling",
    "pharmacy dispensing", "school enrolment and attendance", "university course grades",
    "municipal service requests", "public transport ridership", "traffic incidents",
    "real estate listings and sales", "property rental yields", "construction project costs",
    "bank transaction volumes", "loan portfolio performance", "insurance claims",
    "credit card fraud flags", "restaurant orders and covers", "hotel occupancy and ADR",
    "airline on-time performance", "cargo port throughput", "agricultural yield by plot",
    "water usage by district", "waste collection routes", "telecom network usage",
    "mobile app engagement", "game session analytics", "streaming content watch time",
    "advertising spend and ROAS", "supply chain supplier scorecards",
]

NAMING_STYLES = [
    "snake_case, spelled out (order_date, total_revenue)",
    "snake_case, abbreviated (ord_dt, tot_rev)",
    "camelCase (orderDate, totalRevenue)",
    "Title Case With Spaces (Order Date, Total Revenue)",
    "UPPER_SNAKE legacy warehouse style (ORDER_DT, TOT_REV_AMT)",
    "prefixed by entity (sales_order_date, sales_total_amount)",
]

SYSTEM = """You design realistic database table schemas for business dashboards.

Return one table schema. Requirements:
- 5 to 10 columns.
- Exactly one date/time column, 2 to 4 categorical dimensions, 2 to 5 numeric measures.
- Column names must follow the requested naming style EXACTLY and consistently.
- Names must be plausible for the domain, never generic placeholders like "col1", "value", "x", "data".
- For each category column give 3 to 8 realistic category values.
- For each numeric column give a realistic min and max for the domain.
- dtype is one of: date, int, float, category, bool
- role is one of: time, dimension, measure"""

SCHEMA = {
    "type": "object",
    "properties": {
        "table_name": {"type": "string"},
        "columns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "dtype": {"type": "string", "enum": ["date", "int", "float", "category", "bool"]},
                    "role": {"type": "string", "enum": ["time", "dimension", "measure"]},
                    "categories": {"type": "array", "items": {"type": "string"}},
                    "min": {"type": "number"},
                    "max": {"type": "number"},
                },
                "required": ["name", "dtype", "role"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["table_name", "columns"],
    "additionalProperties": False,
}


def materialize(schema: dict, out_path: Path, n_rows: int, seed: int) -> None:
    """Build a real CSV from the declared schema. Deterministic given the seed."""
    rng = np.random.default_rng(seed)
    data: dict[str, object] = {}
    for col in schema["columns"]:
        name, dtype = col["name"], col["dtype"]
        if dtype == "date":
            start = pd.Timestamp("2024-01-01")
            data[name] = pd.to_datetime(
                start + pd.to_timedelta(rng.integers(0, 540, n_rows), unit="D")
            ).strftime("%Y-%m-%d")
        elif dtype == "category":
            cats = col.get("categories") or [f"{name}_{i}" for i in range(4)]
            data[name] = rng.choice(cats, n_rows)
        elif dtype == "bool":
            data[name] = rng.choice([True, False], n_rows)
        else:
            low = float(col.get("min", 0))
            high = float(col.get("max", max(low + 1, 1000)))
            if high <= low:
                high = low + 1000
            values = rng.uniform(low, high, n_rows)
            data[name] = values.round(0).astype(int) if dtype == "int" else values.round(2)
    pd.DataFrame(data).to_csv(out_path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--total", type=int, default=180)
    parser.add_argument("--test-schemas", type=int, default=60)
    parser.add_argument("--rows-per-fixture", type=int, default=240)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    plan = []
    for i in range(args.total):
        plan.append(
            {
                "schema_id": f"s{i:04d}",
                "domain": DOMAINS[i % len(DOMAINS)],
                "naming_style": NAMING_STYLES[i % len(NAMING_STYLES)],
                "split": "test" if i < args.test_schemas else "train",
            }
        )
    rng.shuffle(plan)

    requests = [
        client.json_request(
            custom_id=item["schema_id"],
            model=client.HAIKU,
            system=SYSTEM,
            user=(
                f"Domain: {item['domain']}\n"
                f"Naming style: {item['naming_style']}\n"
                "Design the table schema."
            ),
            schema=SCHEMA,
            max_tokens=2048,
            effort="low",
        )
        for item in plan
    ]

    outcome = client.run_batch(requests, label="schemas")
    client.record_spend(
        "schemas", client.HAIKU, outcome.usage, {"requests": len(requests)}
    )

    fixture_dir = Path("data/fixtures")
    fixture_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, item in enumerate(plan):
        payload = outcome.payloads.get(item["schema_id"])
        if not payload or not payload.get("columns"):
            continue
        names = [c["name"] for c in payload["columns"]]
        if len(set(names)) != len(names):
            continue
        fixture = fixture_dir / f"{item['schema_id']}.csv"
        try:
            materialize(payload, fixture, args.rows_per_fixture, args.seed + index)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {item['schema_id']}: {exc}")
            continue
        frame = pd.read_csv(fixture)
        rows.append(
            {
                **item,
                "table_name": payload["table_name"],
                "columns": payload["columns"],
                "fixture_csv": str(fixture),
                "pandas_columns": list(frame.columns),
                "pandas_dtypes": {c: str(d) for c, d in frame.dtypes.items()},
                "sample_rows": frame.head(2).to_dict(orient="records"),
            }
        )

    out = Path("data/schemas.jsonl")
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    by_split = {"test": 0, "train": 0}
    for row in rows:
        by_split[row["split"]] += 1
    print(json.dumps({"schemas_kept": len(rows), "by_split": by_split,
                      "refusals": outcome.refusals, "unparsed": outcome.unparsed}, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Pilot on 12 schemas and inspect the names**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python gen_schemas.py --total 12 --test-schemas 4
```

Then read what came back:

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -c "
import json
for line in open('data/schemas.jsonl', encoding='utf-8'):
    r = json.loads(line)
    print(f\"{r['schema_id']} [{r['split']}] {r['domain'][:28]:28s} {r['pandas_columns']}\")
"
```

**Gate:** column names must look like the requested style and be domain-plausible. If you see `col1`, `value`, `x`, or the same names across different domains, fix `SYSTEM` and re-pilot. This is the diversity the whole dataset rests on — do not scale past it.

- [ ] **Step 3: Full run**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python gen_schemas.py 2>&1 | tee runs/schemas.log
```

Expected: ~180 kept, 60 test / 120 train, cost well under $0.30. Check `runs/spend.jsonl`.

- [ ] **Step 4: Verify the fixtures are real and loadable**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -c "
import json, pandas as pd
rows = [json.loads(l) for l in open('data/schemas.jsonl', encoding='utf-8')]
print('schemas:', len(rows))
bad = [r['schema_id'] for r in rows if pd.read_csv(r['fixture_csv']).empty]
print('empty fixtures:', bad)
names = [n for r in rows for n in r['pandas_columns']]
print('distinct column names:', len(set(names)), 'of', len(names))
print('test/train schema ids disjoint:', not (
  {r['schema_id'] for r in rows if r['split']=='test'} &
  {r['schema_id'] for r in rows if r['split']=='train'}))
"
```

Expected: no empty fixtures, a high distinct-name ratio, disjoint splits.

- [ ] **Step 5: Commit**

```bash
cd /Users/atukka/Desktop/BYD && git add chartist-finetune/gen_schemas.py chartist-finetune/data/schemas.jsonl chartist-finetune/data/fixtures && git commit -m "feat(finetune): synthesize 180 business schemas with materialized CSV fixtures

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Generate natural questions (Haiku, ~$0.70)

The scraped prompts were 100% "Create a {X} example in Plotly Python." A user types "which regions are growing". This task produces the latter, under the chart-type quota, with 40% hard cases.

**Files:**
- Create: `chartist-finetune/gen_questions.py`
- Produces: `chartist-finetune/data/questions.jsonl`

**Interfaces:**
- Consumes: `data/schemas.jsonl`, `chart_types.allocate`, `chart_types.HARD_CASE_KINDS`.
- Produces: `{"question_id": str, "schema_id": str, "split": str, "question": str, "chart_bucket": str, "hard_case": str|null}`.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Generate natural dashboard questions per schema, under the chart-type quota."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import chart_types
import client

SYSTEM = """You write the questions a business user types into a dashboard tool.

Rules:
- Never mention Plotly, Python, code, charts-as-examples, or column names verbatim unless a person naturally would.
- Write like a person asking for something, not like documentation. 4 to 18 words.
- The question must be answerable from the given table, and must suit the requested chart shape.
- Vary phrasing across the batch: questions, imperatives, and fragments all appear in real usage.
- No greetings, no "please", no "could you".

Hard-case kinds, when requested:
- multi_column_aggregation: needs a group-by and a sum/mean across more than one column.
- date_parsing_and_resampling: needs the date column rolled up by month, quarter, or week.
- grouped_or_faceted: needs a second dimension as colour, group, or facet.
- missing_field: asks about something NOT in this table, so the answer must work with what is there.
- ambiguous_question: genuinely underspecified, the kind a real user types."""

SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "chart_bucket": {"type": "string"},
                    "hard_case": {"type": "string"},
                },
                "required": ["question", "chart_bucket"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-schema", type=int, default=16)
    parser.add_argument("--limit-schemas", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    schemas = [json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l]
    if args.limit_schemas:
        schemas = schemas[: args.limit_schemas]

    rng = random.Random(args.seed)
    requests = []
    assignments = {}

    for schema in schemas:
        buckets = chart_types.allocate(args.per_schema)
        wanted = [b for b, n in buckets.items() for _ in range(n)]
        rng.shuffle(wanted)
        hard_flags = [
            rng.choice(chart_types.HARD_CASE_KINDS)
            if rng.random() < chart_types.HARD_CASE_SHARE
            else None
            for _ in wanted
        ]
        spec = "\n".join(
            f"{i + 1}. chart shape: {bucket}"
            + (f", hard case: {hard}" if hard else "")
            for i, (bucket, hard) in enumerate(zip(wanted, hard_flags))
        )
        assignments[schema["schema_id"]] = list(zip(wanted, hard_flags))
        requests.append(
            client.json_request(
                custom_id=schema["schema_id"],
                model=client.HAIKU,
                system=SYSTEM,
                user=(
                    f"Table: {schema['table_name']} ({schema['domain']})\n"
                    f"columns: {json.dumps(schema['columns'], default=str)}\n\n"
                    f"Write exactly {len(wanted)} questions, one per line item below, "
                    f"returning them in the same order with the chart_bucket copied "
                    f"and hard_case set when given:\n{spec}"
                ),
                schema=SCHEMA,
                max_tokens=4096,
                effort="low",
            )
        )

    outcome = client.run_batch(requests, label="questions")
    client.record_spend("questions", client.HAIKU, outcome.usage, {"requests": len(requests)})

    rows = []
    for schema in schemas:
        payload = outcome.payloads.get(schema["schema_id"])
        if not payload:
            continue
        wanted = assignments[schema["schema_id"]]
        for index, item in enumerate(payload.get("questions", [])):
            text = (item.get("question") or "").strip()
            if len(text) < 8:
                continue
            bucket, hard = wanted[index] if index < len(wanted) else (item.get("chart_bucket", "bar"), None)
            if bucket not in chart_types.QUOTA:
                bucket = item.get("chart_bucket") if item.get("chart_bucket") in chart_types.QUOTA else "bar"
            rows.append(
                {
                    "question_id": f"{schema['schema_id']}-q{index:02d}",
                    "schema_id": schema["schema_id"],
                    "split": schema["split"],
                    "question": text,
                    "chart_bucket": bucket,
                    "hard_case": hard,
                }
            )

    out = Path("data/questions.jsonl")
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    from collections import Counter

    print(json.dumps(
        {
            "questions": len(rows),
            "by_split": dict(Counter(r["split"] for r in rows)),
            "by_bucket": dict(Counter(r["chart_bucket"] for r in rows).most_common()),
            "hard_case_share": round(sum(1 for r in rows if r["hard_case"]) / max(1, len(rows)), 3),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Pilot on 6 schemas and read the questions**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python gen_questions.py --limit-schemas 6 --per-schema 8
```

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -c "
import json
for line in list(open('data/questions.jsonl', encoding='utf-8'))[:24]:
    r = json.loads(line)
    print(f\"[{r['chart_bucket']:24s}] {r['hard_case'] or '-':28s} {r['question']}\")
"
```

**Gate:** these must read like a person, not a docs page. Any question containing "Plotly", "Python", "example", or a bare column name dump means the prompt needs work. Re-pilot before scaling.

- [ ] **Step 3: Full run**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python gen_questions.py 2>&1 | tee runs/questions.log
```

Expected: ~2,880 questions (180 × 16), hard-case share near 0.40, bucket distribution tracking the quota. Cost under $0.70.

- [ ] **Step 4: Commit**

```bash
cd /Users/atukka/Desktop/BYD && git add chartist-finetune/gen_questions.py chartist-finetune/data/questions.jsonl && git commit -m "feat(finetune): generate natural dashboard questions under a chart-type quota

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Freeze the test set ($0.00)

Built before any training target exists, and **no gold answers** — execution is the oracle, so a test row only needs a schema, a question, an expected chart bucket, and the fixture. 300 rows gives ±8pp on a single proportion and detects a ~16pp gap between two arms; `--limit 40` would only have seen ≥31pp.

Once written, this file is frozen. Nothing downstream may regenerate it.

**Files:**
- Create: `chartist-finetune/freeze_testset.py`
- Produces: `chartist-finetune/data/testset.jsonl`, `chartist-finetune/data/testset.sha256`

**Interfaces:**
- Consumes: `data/schemas.jsonl`, `data/questions.jsonl` (test split only).
- Produces: `{"test_id", "schema_id", "question", "chart_bucket", "hard_case", "fixture_csv", "prompt"}` where `prompt` is the rendered `CHARTIST_USER_TEMPLATE`.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Freeze the evaluation set. No gold answers: execution is the oracle."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from contract import CHARTIST_USER_TEMPLATE


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=300)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    out = Path("data/testset.jsonl")
    if out.is_file():
        raise SystemExit(
            f"{out} already exists and is frozen. Delete it deliberately if you really "
            "mean to rebuild the eval, and know that every prior eval number becomes "
            "incomparable."
        )

    schemas = {
        r["schema_id"]: r
        for r in (json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)
    }
    questions = [
        r
        for r in (json.loads(l) for l in Path("data/questions.jsonl").read_text(encoding="utf-8").splitlines() if l)
        if r["split"] == "test"
    ]

    import random

    random.Random(args.seed).shuffle(questions)
    # Spread across schemas: round-robin so no schema dominates the eval.
    by_schema: dict[str, list] = {}
    for q in questions:
        by_schema.setdefault(q["schema_id"], []).append(q)
    picked = []
    while len(picked) < args.size and any(by_schema.values()):
        for key in list(by_schema):
            if not by_schema[key]:
                continue
            picked.append(by_schema[key].pop())
            if len(picked) >= args.size:
                break

    rows = []
    for index, q in enumerate(picked):
        schema = schemas[q["schema_id"]]
        rows.append(
            {
                "test_id": f"t{index:04d}",
                "schema_id": q["schema_id"],
                "question": q["question"],
                "chart_bucket": q["chart_bucket"],
                "hard_case": q["hard_case"],
                "fixture_csv": schema["fixture_csv"],
                "prompt": CHARTIST_USER_TEMPLATE.format(
                    task=q["question"],
                    columns=schema["pandas_columns"],
                    dtypes=schema["pandas_dtypes"],
                    sample_rows=schema["sample_rows"],
                ),
            }
        )

    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    Path("data/testset.sha256").write_text(digest + "\n", encoding="utf-8")

    print(json.dumps(
        {
            "rows": len(rows),
            "distinct_schemas": len({r["schema_id"] for r in rows}),
            "by_bucket": dict(Counter(r["chart_bucket"] for r in rows).most_common()),
            "hard_cases": sum(1 for r in rows if r["hard_case"]),
            "sha256": digest[:16],
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python freeze_testset.py
```

Expected: 300 rows spread over ~60 schemas, bucket mix tracking the quota, ~120 hard cases.

- [ ] **Step 3: Prove no train schema leaked into it**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -c "
import json
test = {json.loads(l)['schema_id'] for l in open('data/testset.jsonl', encoding='utf-8')}
train = {json.loads(l)['schema_id'] for l in open('data/schemas.jsonl', encoding='utf-8') if json.loads(l)['split']=='train'}
assert not (test & train), f'LEAK: {test & train}'
print(f'clean: {len(test)} test schemas, 0 overlap with {len(train)} train schemas')
"
```

- [ ] **Step 4: Commit**

```bash
cd /Users/atukka/Desktop/BYD && git add chartist-finetune/freeze_testset.py chartist-finetune/data/testset.jsonl chartist-finetune/data/testset.sha256 && git commit -m "feat(finetune): freeze a 300-row schema-disjoint test set with no gold answers

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Generate code targets with best-of-k (Sonnet, ~$14.00)

The single biggest accuracy lever: **every training target is verified correct by execution**, not merely plausible. Generate 2 candidates per question, keep the one that executes *and* produces a trace type in the requested bucket; send a 3rd attempt only where both failed. At a ~70% per-candidate pass rate that is ~97% coverage at ~2.1 generations per row.

Effort is `low` for routine rows and `medium` for hard cases — the only place in this plan that pays for more thinking.

**Files:**
- Create: `chartist-finetune/gen_targets.py`
- Produces: `chartist-finetune/data/targets.jsonl`, `chartist-finetune/runs/targets_report.json`

**Interfaces:**
- Consumes: `data/schemas.jsonl`, `data/questions.jsonl` (train split only), `client.run_batch`, `executor.run_candidate`, `chart_types.TRACE_TYPES`.
- Produces: `{"schema_id", "question_id", "messages": [system, user, assistant], "fixture_csv", "chart_bucket", "hard_case", "figure_type", "attempt"}`.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Generate verified code targets with adaptive best-of-k.

Round 1 sends k candidates per question. Every candidate is executed against the
schema's real CSV; a candidate survives only if it runs, uses no unknown column,
and yields a trace type in the requested chart bucket. Questions with no survivor
get one extra attempt in round 2.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import chart_types
import client
from contract import CHARTIST_SYSTEM_PROMPT, CHARTIST_USER_TEMPLATE
from executor import run_candidate

CODE_SCHEMA = {
    "type": "object",
    "properties": {"code": {"type": "string"}},
    "required": ["code"],
    "additionalProperties": False,
}


def build_prompt(schema: dict, question: dict) -> str:
    return CHARTIST_USER_TEMPLATE.format(
        task=question["question"],
        columns=schema["pandas_columns"],
        dtypes=schema["pandas_dtypes"],
        sample_rows=schema["sample_rows"],
    )


def system_for(question: dict) -> str:
    """Same contract, plus the requested chart shape as a steer."""
    bucket = question["chart_bucket"]
    extra = f"\n\nFor this request, produce a {bucket.replace('_', ' ')} chart."
    if question.get("hard_case") == "missing_field":
        extra += (
            "\nThe request may name something absent from the schema. Do not invent a "
            "column: answer with the closest thing the schema actually provides."
        )
    return CHARTIST_SYSTEM_PROMPT + extra


def judge(code: str, question: dict, fixture: str) -> tuple[bool, object]:
    result = run_candidate(code, fixture)
    if not result.ok:
        return False, result
    allowed = chart_types.TRACE_TYPES.get(question["chart_bucket"], set())
    if allowed and result.figure_type not in allowed:
        return False, result
    return True, result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None, help="limit questions (pilot)")
    parser.add_argument("--max-spend", type=float, default=14.00)
    args = parser.parse_args()

    schemas = {
        r["schema_id"]: r
        for r in (json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)
    }
    questions = [
        r
        for r in (json.loads(l) for l in Path("data/questions.jsonl").read_text(encoding="utf-8").splitlines() if l)
        if r["split"] == "train"
    ]
    if args.limit:
        questions = questions[: args.limit]
    print(f"train questions: {len(questions)}, k={args.k}")

    index = {q["question_id"]: q for q in questions}
    spend = 0.0
    kept: dict[str, dict] = {}
    reasons: Counter[str] = Counter()

    def submit(pending: list[dict], attempt: int) -> None:
        nonlocal spend
        requests = []
        for question in pending:
            schema = schemas[question["schema_id"]]
            effort = "medium" if question.get("hard_case") else "low"
            for candidate in range(args.k if attempt == 1 else 1):
                requests.append(
                    client.json_request(
                        custom_id=f"{question['question_id']}#{attempt}#{candidate}",
                        model=client.SONNET,
                        system=system_for(question),
                        user=build_prompt(schema, question),
                        schema=CODE_SCHEMA,
                        max_tokens=3000,
                        effort=effort,
                    )
                )
        if not requests:
            return
        outcome = client.run_batch(requests, label=f"targets-a{attempt}")
        spend += client.record_spend(
            f"targets-a{attempt}", client.SONNET, outcome.usage, {"requests": len(requests)}
        )

        for custom_id, payload in outcome.payloads.items():
            question_id = custom_id.split("#", 1)[0]
            if question_id in kept:
                continue
            question = index[question_id]
            code = (payload.get("code") or "").strip()
            if not code:
                reasons["empty_code"] += 1
                continue
            fixture = schemas[question["schema_id"]]["fixture_csv"]
            good, result = judge(code, question, fixture)
            if not good:
                label = (
                    result.violations[0]
                    if getattr(result, "violations", None)
                    else "unknown_columns"
                    if getattr(result, "unknown_columns", None)
                    else "wrong_chart_type"
                    if getattr(result, "figure_type", None)
                    else "execution_failed"
                )
                reasons[label] += 1
                continue
            kept[question_id] = {
                "schema_id": question["schema_id"],
                "question_id": question_id,
                "messages": [
                    {"role": "system", "content": CHARTIST_SYSTEM_PROMPT},
                    {"role": "user", "content": build_prompt(schemas[question["schema_id"]], question)},
                    {"role": "assistant", "content": code},
                ],
                "fixture_csv": fixture,
                "chart_bucket": question["chart_bucket"],
                "hard_case": question["hard_case"],
                "figure_type": result.figure_type,
                "attempt": int(custom_id.split("#")[1]),
            }

    submit(questions, attempt=1)
    print(f"after round 1: kept {len(kept)}/{len(questions)}, spend ${spend:.2f}")

    retry = [q for q in questions if q["question_id"] not in kept]
    if retry and spend < args.max_spend:
        print(f"round 2: retrying {len(retry)} questions")
        submit(retry, attempt=2)
    elif retry:
        print(f"skipping round 2: spend ${spend:.2f} already at the ${args.max_spend} cap")

    out = Path("data/targets.jsonl")
    with out.open("w", encoding="utf-8") as handle:
        for row in kept.values():
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    report = {
        "train_questions": len(questions),
        "verified_targets": len(kept),
        "yield": round(len(kept) / max(1, len(questions)), 3),
        "spend_usd": round(spend, 4),
        "cost_per_verified_row": round(spend / max(1, len(kept)), 5),
        "rejection_reasons": dict(reasons.most_common()),
        "by_bucket": dict(Counter(r["chart_bucket"] for r in kept.values()).most_common()),
        "hard_case_share": round(
            sum(1 for r in kept.values() if r["hard_case"]) / max(1, len(kept)), 3
        ),
    }
    Path("runs/targets_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Pilot on 30 questions and get the real per-row cost**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python gen_targets.py --limit 30
```

**Gate.** Read `runs/targets_report.json` and multiply `cost_per_verified_row` by the full train-question count. **If the projection exceeds $14, stop and report it before the full run** — then either lower `--per-schema` in Task 4 or drop `--k` to 1 with a round 2.

Also read five kept targets by hand. They must use the schema's real column names, end with the JSON print, and actually match the question.

- [ ] **Step 3: Full run**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python gen_targets.py --max-spend 14.00 2>&1 | tee runs/targets.log
```

Expected: ~1,500-1,900 verified rows from ~1,920 train questions. The `rejection_reasons` breakdown is diagnostic: a lot of `wrong_chart_type` means the bucket steer is too weak; a lot of `unknown_columns` means Sonnet is ignoring the schema, which would be surprising and worth reading before spending more.

- [ ] **Step 4: Commit**

```bash
cd /Users/atukka/Desktop/BYD && git add chartist-finetune/gen_targets.py chartist-finetune/data/targets.jsonl chartist-finetune/runs/targets_report.json && git commit -m "feat(finetune): generate execution-verified code targets with best-of-k

Every training target runs against its schema's real CSV and must produce a
trace type in the requested chart bucket. Unverified candidates are discarded.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Docs rows as a base layer ($0.00)

The 970 scraped rows keep one real use: chart-type breadth that synthetic questions would never ask for. 522 carry a real dataframe in the code and 193 more carry literal `x=`/`y=` lists that lift into a two-column frame — a 715-row ceiling, so expect 400-550 after execution filtering. Deterministic, no model, no spend.

**Files:**
- Create: `chartist-finetune/rewrite_docs.py`, `chartist-finetune/tests/test_rewrite.py`
- Produces: `chartist-finetune/data/docs_rows.jsonl`

**Interfaces:**
- Consumes: `web-crawler/dataset/plotly_qwen_{train,val}.jsonl`, `run_candidate`.
- Produces: rows shaped like Task 6's, with `"schema_id": "docs-<page-slug>"` so the page is the leakage unit, and `"source": "docs"`.

- [ ] **Step 1: Write the failing test**

```python
# chartist-finetune/tests/test_rewrite.py
from rewrite_docs import ensure_json_print, split_data_loading, strip_show


def test_strip_show_removes_only_the_call():
    assert strip_show("fig = px.bar(df)\nfig.show()\n").strip() == "fig = px.bar(df)"


def test_strip_show_handles_arguments():
    assert "show" not in strip_show('fig = px.bar(df)\nfig.show(renderer="png")\n')


def test_ensure_json_print_is_idempotent():
    once = ensure_json_print("fig = px.bar(df)")
    assert once.endswith("print(fig.to_json())")
    assert ensure_json_print(once) == once


def test_split_data_loading_separates_loader_from_chart():
    code = (
        "import pandas as pd\nimport plotly.express as px\n"
        "df = pd.read_csv('https://example.com/x.csv')\n"
        "fig = px.bar(df, x='a', y='b')\nfig.show()\n"
    )
    loader, chart = split_data_loading(code)
    assert "read_csv" in loader and "read_csv" not in chart and "px.bar" in chart
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -m pytest tests/test_rewrite.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'rewrite_docs'`.

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
"""Rewrite scraped Plotly-docs examples into contract-compliant rows.

The docs code builds its own dataframe, renders with fig.show(), and never prints
figure JSON. Lift the embedded data into a CSV fixture, drop the loader, and the
row becomes a legitimate schema-conditioned example. Deterministic, no model.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

from contract import CHARTIST_SYSTEM_PROMPT, CHARTIST_USER_TEMPLATE
from executor import run_candidate

REPO = Path(__file__).resolve().parent.parent
SOURCES = [
    REPO / "web-crawler/dataset/plotly_qwen_train.jsonl",
    REPO / "web-crawler/dataset/plotly_qwen_val.jsonl",
]
MAPPING = REPO / "web-crawler/dataset/plotly_qwen_mapping.jsonl"

DATA_LOADING = re.compile(
    r"^\s*(?:df|data|dataset)\w*\s*=\s*(?:pd|pandas)\s*\.\s*read_\w+|"
    r"^\s*(?:df|data|dataset)\w*\s*=\s*px\s*\.\s*data\s*\.|"
    r"^\s*(?:df|data|dataset)\w*\s*=\s*(?:pd|pandas)\s*\.\s*DataFrame|"
    r"^\s*\w+\s*=\s*np\s*\.\s*(?:random|linspace|arange)"
)
SHOW_CALL = re.compile(r"^\s*fig\s*\.\s*show\s*\([^)]*\)\s*$", re.MULTILINE)

DUMP = """
import json, socket, sys
job = json.loads(sys.stdin.read())
def _deny(*a, **k):
    raise OSError("network disabled")
import pandas as pd, numpy as np
import plotly.express as px
ns = {"pd": pd, "np": np, "px": px}
exec(compile(job["loader"], "<loader>", "exec"), ns)
socket.socket = _deny
frame = None
for name in ("df", "data", "dataset"):
    v = ns.get(name)
    if isinstance(v, pd.DataFrame):
        frame = v
        break
if frame is None:
    sys.exit(3)
frame.head(240).to_csv(job["out"], index=False)
"""


def strip_show(code: str) -> str:
    return SHOW_CALL.sub("", code)


def ensure_json_print(code: str) -> str:
    text = code.rstrip()
    return text if text.endswith("print(fig.to_json())") else f"{text}\nprint(fig.to_json())"


def split_data_loading(code: str) -> tuple[str, str]:
    loader, chart = [], []
    for line in code.splitlines():
        if DATA_LOADING.match(line):
            loader.append(line.strip())
        elif re.match(r"^\s*(?:import |from )", line):
            loader.append(line.strip())
            chart.append(line)
        else:
            chart.append(line)
    return "\n".join(loader), "\n".join(chart)


def materialize(loader: str, fixture_dir: Path) -> Path | None:
    if not any(tok in loader for tok in ("read_", "DataFrame", "px.data.", "np.")):
        return None
    fixture_dir.mkdir(parents=True, exist_ok=True)
    out = fixture_dir / f"{uuid.uuid4().hex[:12]}.csv"
    try:
        done = subprocess.run(
            [sys.executable, "-I", "-c", DUMP],
            input=json.dumps({"loader": loader, "out": str(out)}),
            capture_output=True, text=True, timeout=40,
        )
    except subprocess.TimeoutExpired:
        return None
    return out if done.returncode == 0 and out.is_file() else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    pages = {}
    if MAPPING.is_file():
        for line in MAPPING.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            if row.get("kept"):
                pages.setdefault(row["source_url"], row.get("graph_type", "unknown"))

    rows = []
    for path in SOURCES:
        rows += [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l]
    if args.limit:
        rows = rows[: args.limit]

    page_slugs = list(pages.values()) or ["unknown"]
    fixture_dir = Path("data/fixtures_docs")
    import pandas as pd

    kept, reasons = [], Counter()
    for index, row in enumerate(rows):
        messages = row.get("messages") or []
        if len(messages) != 3:
            reasons["malformed"] += 1
            continue
        loader, chart = split_data_loading(messages[2]["content"])
        chart = ensure_json_print(strip_show(chart))
        try:
            ast.parse(chart)
        except SyntaxError:
            reasons["chart_syntax_error"] += 1
            continue
        fixture = materialize(loader, fixture_dir)
        if fixture is None:
            reasons["no_dataframe_recovered"] += 1
            continue
        frame = pd.read_csv(fixture)
        if frame.empty:
            reasons["empty_frame"] += 1
            continue
        prompt = CHARTIST_USER_TEMPLATE.format(
            task=messages[1]["content"].strip(),
            columns=list(frame.columns),
            dtypes={c: str(d) for c, d in frame.dtypes.items()},
            sample_rows=frame.head(2).to_dict(orient="records"),
        )
        verdict = run_candidate(chart, str(fixture))
        if not verdict.ok:
            reasons[f"exec:{verdict.violations[0] if verdict.violations else 'failed'}"] += 1
            continue
        kept.append(
            {
                "schema_id": f"docs-{page_slugs[index % len(page_slugs)]}",
                "question_id": f"docs-{index:04d}",
                "messages": [
                    {"role": "system", "content": CHARTIST_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": chart},
                ],
                "fixture_csv": str(fixture),
                "chart_bucket": None,
                "hard_case": None,
                "figure_type": verdict.figure_type,
                "source": "docs",
            }
        )
        if (index + 1) % 100 == 0:
            print(f"  {index + 1}/{len(rows)} kept {len(kept)}", flush=True)

    out = Path("data/docs_rows.jsonl")
    with out.open("w", encoding="utf-8") as handle:
        for item in kept:
            handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
    print(json.dumps({"input": len(rows), "kept": len(kept),
                      "drop_reasons": dict(reasons.most_common())}, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the unit tests, then a 40-row smoke test**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -m pytest tests/test_rewrite.py -v
```

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python rewrite_docs.py --limit 40
```

Expected: 4 unit tests PASS; the smoke test keeps a handful. If it keeps 0, read the top drop reason before the full run.

- [ ] **Step 5: Full run**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python rewrite_docs.py 2>&1 | tee runs/docs_rows.log
```

Expected: 400-550 kept of 970, with `no_dataframe_recovered` the dominant drop (~255 rows genuinely have no tabular form — geo, image, and 3D literals).

- [ ] **Step 6: Commit**

```bash
cd /Users/atukka/Desktop/BYD && git add chartist-finetune/rewrite_docs.py chartist-finetune/tests/test_rewrite.py chartist-finetune/data/docs_rows.jsonl && git commit -m "feat(finetune): rewrite docs rows into a contract-compliant base layer

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Merge and export mlx-lm splits ($0.00)

**Files:**
- Create: `chartist-finetune/export_mlx.py`
- Produces: `chartist-finetune/data/mlx/{train,valid}.jsonl`, `chartist-finetune/data/mlx/split_manifest.json`

**Interfaces:**
- Consumes: `data/targets.jsonl`, `data/docs_rows.jsonl`.
- Produces: mlx-lm chat-format JSONL. `test.jsonl` is deliberately **not** written here — the eval uses the frozen `data/testset.jsonl` instead.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Merge verified targets with the docs base layer and export schema-disjoint splits."""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", default=["data/targets.jsonl", "data/docs_rows.jsonl"])
    parser.add_argument("--out-dir", default="data/mlx")
    parser.add_argument("--valid-ratio", type=float, default=0.08)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    grouped: dict[str, list[dict]] = defaultdict(list)
    for name in args.inputs:
        path = Path(name)
        if not path.is_file():
            print(f"skipping missing {path}")
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                row = json.loads(line)
                grouped[row["schema_id"]].append(row)

    frozen_test = {
        json.loads(l)["schema_id"]
        for l in Path("data/testset.jsonl").read_text(encoding="utf-8").splitlines()
        if l
    }
    leaked = set(grouped) & frozen_test
    if leaked:
        raise SystemExit(f"LEAK: these schemas are in the frozen test set: {sorted(leaked)[:5]}")

    keys = sorted(grouped)
    random.Random(args.seed).shuffle(keys)
    n_valid = max(1, int(len(keys) * args.valid_ratio))
    splits = {"valid": keys[:n_valid], "train": keys[n_valid:]}

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"seed": args.seed, "counts": {}, "schema_ids": {}, "sources": {}}

    for split, split_keys in splits.items():
        rows = [row for key in split_keys for row in grouped[key]]
        random.Random(args.seed).shuffle(rows)
        with (out_dir / f"{split}.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps({"messages": row["messages"]}, ensure_ascii=False) + "\n")
        manifest["counts"][split] = len(rows)
        manifest["schema_ids"][split] = sorted(split_keys)
        manifest["sources"][split] = dict(Counter(r.get("source", "synthetic") for r in rows))

    (out_dir / "split_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"counts": manifest["counts"], "sources": manifest["sources"]}, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python export_mlx.py
```

Expected: ~2,000-2,400 train rows, ~180 valid, and the leak check silent.

- [ ] **Step 3: Verify the format and the token budget**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -c "
import json
rows = [json.loads(l) for l in open('data/mlx/train.jsonl', encoding='utf-8')]
assert all(set(r) == {'messages'} for r in rows)
assert all([m['role'] for m in r['messages']] == ['system','user','assistant'] for r in rows)
chars = sorted(sum(len(m['content']) for m in r['messages']) for r in rows)
n = len(chars)
print(f'rows={n} p50={chars[n//2]} p90={chars[int(n*0.9)]} max={chars[-1]}')
print(f'approx total tokens={sum(chars)//4:,}  steps/epoch at batch 2={n//2}')
print(f'rows over 2048 tokens: {sum(1 for c in chars if c/4 > 2048)}')
"
```

Use the printed `max` to pick `--max-seq-length` in Task 10, and `steps/epoch` to pick `--iters`.

- [ ] **Step 4: Commit**

```bash
cd /Users/atukka/Desktop/BYD && git add chartist-finetune/export_mlx.py chartist-finetune/data/mlx/ && git commit -m "feat(finetune): merge and export schema-disjoint mlx-lm splits

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Prepare the base model ($0.00, long download)

Qwen3.5-9B is a vision-language model and `mlx_lm.lora` is text-only. MLX text loaders skip vision weights and community text-only conversions of the Qwen3.5 line exist, but neither is verified for the 9B here — so verify before training.

**Files:**
- Produces: `chartist-finetune/models/qwen3.5-9b-4bit/`, README notes
- Modify: `chartist-finetune/README.md`

- [ ] **Step 1: Install mlx-lm into the project venv and confirm Metal**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -m pip install -q -U mlx-lm && .venv/bin/python -c "import mlx.core as mx; print('default device:', mx.default_device())"
```

Expected: a Metal device. A CPU device means stop — LoRA on CPU is not worth it here.

- [ ] **Step 2: Record the real CLI surface**

Guides disagree on `convert` and `fuse` flags across versions. Capture what this install accepts; **the help output wins over this plan.**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && for m in lora convert fuse generate; do echo "### mlx_lm.$m"; .venv/bin/python -m mlx_lm.$m --help 2>&1; done | tee runs/mlx_help.txt
```

Paste the flag lists into `README.md` under `## mlx-lm CLI (as installed)` with the version from `.venv/bin/python -m pip show mlx-lm | head -2`.

- [ ] **Step 3: Convert and quantize**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -m mlx_lm.convert --hf-path Qwen/Qwen3.5-9B --mlx-path models/qwen3.5-9b-4bit -q --q-bits 4
```

Expected: ~5-6 GB output; the bf16 download is transient and needs ~20 GB. If it fails on vision-tower weights, search Hugging Face for a `Qwen3.5-9B` MLX **text-only** conversion and pass that repo id to `--hf-path` (a 4-bit text-only 4B exists as `heykorshun/Qwen3.5-4B-MLX-4bit-text`, whose author notes MLX text loaders already skip vision weights). Record whichever path worked.

- [ ] **Step 4: Verify generation and note the speed**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -m mlx_lm.generate --model models/qwen3.5-9b-4bit --prompt "Write one line of Python that prints hello." --max-tokens 64
```

Record tokens/sec — the eval generates 300 times, so this sets its wall clock.

- [ ] **Step 5: Commit the notes**

```bash
cd /Users/atukka/Desktop/BYD && git add chartist-finetune/README.md && git commit -m "docs(finetune): record mlx-lm CLI surface and base model prep

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: Train ($0.00, hours)

- [ ] **Step 1: Train**

Use the step count and sequence length printed by Task 8 Step 3; `--iters` at roughly two epochs.

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -m mlx_lm.lora --model models/qwen3.5-9b-4bit --train --data data/mlx --adapter-path runs/lora-v1/adapters --batch-size 2 --max-seq-length 2048 --iters 2000 --steps-per-report 25 --steps-per-eval 200 --save-every 200 2>&1 | tee runs/lora-v1/train.log
```

QLoRA is automatic because `--model` is quantized. Use only flags from Task 9 Step 2.

- [ ] **Step 2: Read the validation loss, not the clock**

- Falls then flattens → let it finish.
- Falls then **rises** → overfitting; note the turn iteration, stop, re-run with `--iters` just below it.
- Training loss barely moves → add `--learning-rate 1e-4`.

If it OOMs, `sudo sysctl iogpu.wired_limit_mb=28000` (not persistent) and note it in the README.

- [ ] **Step 3: Confirm the adapter changed behavior**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -m mlx_lm.generate --model models/qwen3.5-9b-4bit --adapter-path runs/lora-v1/adapters --max-tokens 400 --prompt "$(.venv/bin/python -c "
import json
print(json.loads(open('data/testset.jsonl', encoding='utf-8').readline())['prompt'])
")"
```

Expected: Python ending in `print(fig.to_json())`, no `fig.show()`, no `pd.read_csv`, using only that schema's columns. If `fig.show()` survives, check the targets: `grep -c 'to_json' data/mlx/train.jsonl` must equal the row count.

- [ ] **Step 4: Commit the run notes**

```bash
cd /Users/atukka/Desktop/BYD && git add chartist-finetune/README.md && git commit -m "docs(finetune): record lora-v1 training run and losses

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: Evaluate, then serve

**Files:**
- Create: `chartist-finetune/evaluate.py`
- Modify: `backend/app/core/config.py`, `backend/app/services/qwen_slm.py`, `backend/app/services/agents/workflow.py`, `backend/requirements.txt`, `backend/.env.example`
- Produces: `chartist-finetune/data/eval_report.json`

- [ ] **Step 1: Write the eval**

```python
#!/usr/bin/env python3
"""Score a model on the frozen test set by executing everything it writes."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import chart_types
from executor import run_candidate


def generate(model: str, adapter: str | None, prompt: str, max_tokens: int = 600) -> str:
    cmd = [sys.executable, "-m", "mlx_lm.generate", "--model", model,
           "--max-tokens", str(max_tokens), "--prompt", prompt]
    if adapter and adapter != "none":
        cmd += ["--adapter-path", adapter]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=900).stdout


def strip_wrapper(raw: str) -> str:
    text = raw
    if "==========" in text:
        parts = text.split("==========")
        if len(parts) >= 3:
            text = parts[1]
    if "```" in text:
        chunks = text.split("```")
        if len(chunks) >= 2:
            text = chunks[1]
            if text.startswith("python"):
                text = text[len("python"):]
    return text.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/qwen3.5-9b-4bit")
    parser.add_argument("--adapter-path", default="none")
    parser.add_argument("--label", required=True)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    rows = [json.loads(l) for l in Path("data/testset.jsonl").read_text(encoding="utf-8").splitlines() if l]
    if args.limit:
        rows = rows[: args.limit]

    totals: Counter[str] = Counter()
    per_bucket: dict[str, Counter] = defaultdict(Counter)
    per_hard: dict[str, Counter] = defaultdict(Counter)
    failures = []

    for index, row in enumerate(rows):
        code = strip_wrapper(generate(args.model, args.adapter_path, row["prompt"]))
        verdict = run_candidate(code, row["fixture_csv"])
        bucket = row["chart_bucket"]
        allowed = chart_types.TRACE_TYPES.get(bucket, set())
        right_shape = bool(allowed) and verdict.figure_type in allowed

        totals["n"] += 1
        per_bucket[bucket]["n"] += 1
        per_hard[row["hard_case"] or "easy"]["n"] += 1
        if verdict.ok:
            totals["renders"] += 1
            per_bucket[bucket]["renders"] += 1
            per_hard[row["hard_case"] or "easy"]["renders"] += 1
            if right_shape:
                totals["right_shape"] += 1
                per_bucket[bucket]["right_shape"] += 1
        for violation in verdict.violations:
            totals[f"violation:{violation}"] += 1
        if verdict.unknown_columns:
            totals["hallucinated_columns"] += 1
        if not verdict.ok:
            failures.append({
                "test_id": row["test_id"], "bucket": bucket, "hard_case": row["hard_case"],
                "violations": verdict.violations, "unknown_columns": verdict.unknown_columns,
                "error": verdict.error, "code": code[:600],
            })
        if (index + 1) % 20 == 0:
            print(f"  {index + 1}/{len(rows)} renders={totals['renders']}", flush=True)

    n = max(1, totals["n"])
    report = {
        "label": args.label, "model": args.model, "adapter_path": args.adapter_path, "n": totals["n"],
        "render_rate": round(totals["renders"] / n, 4),
        "right_shape_rate": round(totals["right_shape"] / n, 4),
        "hallucinated_column_rate": round(totals["hallucinated_columns"] / n, 4),
        "violations": {k.split(":", 1)[1]: v for k, v in totals.items() if k.startswith("violation:")},
        "by_bucket": {k: {"n": v["n"], "render_rate": round(v["renders"] / max(1, v["n"]), 3),
                          "right_shape_rate": round(v["right_shape"] / max(1, v["n"]), 3)}
                      for k, v in sorted(per_bucket.items())},
        "by_hard_case": {k: {"n": v["n"], "render_rate": round(v["renders"] / max(1, v["n"]), 3)}
                         for k, v in sorted(per_hard.items())},
        "failures": failures[:25],
    }
    out = Path("data/eval_report.json")
    existing = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    existing[args.label] = report
    out.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "failures"}, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Score the base model, then the adapter, on the full 300**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python evaluate.py --label base --adapter-path none 2>&1 | tee runs/eval_base.log
```

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python evaluate.py --label lora-v1 --adapter-path runs/lora-v1/adapters 2>&1 | tee runs/eval_lora.log
```

Do not pass `--limit`: at n=300 a ~16pp gap is detectable; at n=40 only ≥31pp is.

- [ ] **Step 3: Decide, and spend the reserve on what the eval shows**

Read `data/eval_report.json`.

- Adapter `render_rate` clearly above base → ship it, go to Step 4.
- Adapter at or below base → do not ship. The `by_bucket` and `by_hard_case` breakdowns say where to spend the **$15 reserve**: one bucket far below the rest means generate more of that bucket in Task 4/6; `by_hard_case` far below `easy` means raise `HARD_CASE_SHARE` and regenerate those; concentrated `missing_json_print` means the targets are wrong, not the volume.
- Near-perfect for both → the test set is too easy; raise `HARD_CASE_SHARE` and re-freeze a v2 test set deliberately.

Write both runs' headline numbers and the reserve decision into `README.md`.

- [ ] **Step 4: Add an MLX serving backend**

In `backend/app/core/config.py`:

```python
    LLM_BACKEND: str = "ollama"  # "ollama" | "mlx"
    MLX_BASE_URL: str = "http://localhost:8080/v1"
    CHARTIST_MODEL: str = ""  # blank means use OLLAMA_MODEL for every role
```

In `backend/app/services/qwen_slm.py`:

```python
def build_chat_model(model: str | None = None, temperature: float = 0, format: str = ""):
    """Chat model for the configured backend. The MLX path talks to mlx_lm.server
    on localhost over an OpenAI-compatible API — nothing leaves the machine."""
    settings = get_settings()
    backend = os.getenv("LLM_BACKEND", settings.LLM_BACKEND).lower()
    if backend == "mlx":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model or settings.OLLAMA_MODEL,
            temperature=temperature,
            base_url=os.getenv("MLX_BASE_URL", settings.MLX_BASE_URL),
            api_key="not-used",
            timeout=settings.OLLAMA_TIMEOUT_SECONDS,
        )
    return LocalQwenChatModel(model=model, temperature=temperature, format=format)
```

Add `langchain-openai` to `backend/requirements.txt`.

- [ ] **Step 5: Give the chartist its own model, and only the chartist**

In `backend/app/services/agents/workflow.py` (requires the platform-correctness plan's Task 5):

```python
@lru_cache(maxsize=1)
def get_llms():
    """(planner_json, chartist, tool_caller).

    Only the chartist may point at the fine-tuned adapter. The tool-calling model
    stays on base instruct weights: the detective's two ReAct agents depend on
    tool calling, which this adapter is not trained for.
    """
    settings = get_settings()
    chartist_model = settings.CHARTIST_MODEL or model_name
    return (
        build_chat_model(model=model_name, format="json"),
        build_chat_model(model=chartist_model),
        build_chat_model(model=model_name),
    )
```

Document the three variables in `backend/.env.example`.

- [ ] **Step 6: Fuse, re-quantize, serve**

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -m mlx_lm.fuse --model models/qwen3.5-9b-4bit --adapter-path runs/lora-v1/adapters --save-path models/qwen3.5-9b-chartist --de-quantize
```

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -m mlx_lm.convert --hf-path models/qwen3.5-9b-chartist --mlx-path models/qwen3.5-9b-chartist-4bit -q --q-bits 4
```

```bash
cd /Users/atukka/Desktop/BYD/chartist-finetune && .venv/bin/python -m mlx_lm.server --model models/qwen3.5-9b-chartist-4bit --port 8080
```

`--de-quantize` matters: training was QLoRA against quantized weights, so fuse to full precision before re-quantizing. GGUF/Ollama is the alternative but often fails for non-Llama architectures — only attempt it if everything must live in Ollama.

- [ ] **Step 7: End-to-end check**

With the MLX server up, start the backend with `LLM_BACKEND=mlx`, sign in, upload `backend/data/sales.csv`, and generate `bar chart of value by category` from the canvas. A chart must render **and** the backend log must show no `[chartist] contract violations` warning — that warning firing contradicts the eval and needs investigating before this is called done.

- [ ] **Step 8: Commit**

```bash
cd /Users/atukka/Desktop/BYD && git add chartist-finetune/evaluate.py chartist-finetune/data/eval_report.json chartist-finetune/README.md backend/app/core/config.py backend/app/services/qwen_slm.py backend/app/services/agents/workflow.py backend/requirements.txt backend/.env.example && git commit -m "feat(finetune): execution-based eval on the frozen test set and MLX serving

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage.** Every element of the agreed direction maps to a task: schema-first generation (3-4), test set built first with no gold answers (5), best-of-k with the execution gate (6), Haiku/Sonnet split (3-4 vs 6), prompt caching and low/medium effort (`client.json_request`, Task 6), chart-type quota and 40% hard cases (`chart_types.py`, Task 4), docs rows demoted to a base layer (7), $30 allocation with a $15 reserve held for the post-eval decision (budget ledger, Task 11 Step 3), `CLAUDE_API_KEY` from `.env` (Task 2), venv throughout, and schema-disjoint splits enforced by assertions in Tasks 5, 8.

**Placeholder scan.** No "TBD", no "handle errors appropriately". Every script is complete. Four steps deliberately branch on a measured outcome with every branch spelled out: Task 3 Step 2 (name quality gate), Task 4 Step 2 (question quality gate), Task 6 Step 2 (cost projection gate), Task 10 Step 2 and Task 11 Step 3 (loss shape and eval delta). Task 9 Step 2 captures the installed CLI rather than hardcoding flags, and says the help output wins.

**Type consistency.** `CandidateResult` fields are defined in Task 2 and read with those names in Tasks 6, 7, 11. `client.run_batch` returns `BatchOutcome` with `payloads`/`usage`/`refusals`, consumed identically in Tasks 3, 4, 6. `client.json_request(custom_id, model, system, user, schema, max_tokens, effort)` is defined once and called with those keywords everywhere. Schema rows carry `schema_id`/`split`/`fixture_csv`/`pandas_columns`/`pandas_dtypes`/`sample_rows` from Task 3 and are read by exactly those names in Tasks 4, 5, 6. `chart_types.TRACE_TYPES` is used for the shape check in both Task 6 and Task 11. Target rows carry `schema_id`/`messages`/`fixture_csv`/`chart_bucket`/`hard_case` from Task 6, and Task 7 emits the same shape so Task 8 can merge them blind.

**Two real risks, stated.** First, Haiku's schema quality is the foundation: if it emits generic column names the whole dataset is worthless, which is why Task 3 Step 2 is a hard gate on reading the names before scaling. Second, `_unknown_columns` is a heuristic over quoted strings; a false positive silently discards a good target in Task 6 and understates the model in Task 11. Its `_NOT_COLUMNS` allow-list is the mitigation, and Task 6's `rejection_reasons` breakdown is where a systematic false positive would show up as an implausible `unknown_columns` count.
