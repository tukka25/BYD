import importlib.util
import re
from pathlib import Path

import pytest

from contract import BACKEND_CONTRACT, CHARTIST_SYSTEM_PROMPT, ContractViolation, validate_chart_code

PRODUCTION = BACKEND_CONTRACT.parents[2] / "utils/executor.py"
OK_TAIL = "\nprint(fig.to_json())\n"


def _production():
    spec = importlib.util.spec_from_file_location("production_executor", PRODUCTION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SafeExecutor()


# One concrete snippet per production pattern.
_SNIPPETS = {
    r"\bimport\s+os\b": "import os",
    r"\bimport\s+subprocess\b": "import subprocess",
    r"\bfrom\s+os\s+import\b": "from os import path",
    r"\bfrom\s+subprocess\s+import\b": "from subprocess import run",
    r"\bopen\(": "x = open('f')",
    r"\beval\(": "x = eval('1')",
    r"\bexec\(": "exec('x=1')",
    r"\b__import__\(": "np = __import__('numpy')",
}


def test_backend_contract_is_reachable():
    assert BACKEND_CONTRACT.is_file(), f"{BACKEND_CONTRACT} missing — run Task 1 first"


def test_contract_loads_and_works():
    assert "print(fig.to_json())" in CHARTIST_SYSTEM_PROMPT
    assert validate_chart_code("fig = 1\nprint(fig.to_json())\n") == []


def test_every_production_blocked_pattern_has_a_snippet():
    assert set(_production().blocked_patterns) == set(_SNIPPETS)


@pytest.mark.parametrize("pattern", sorted(_SNIPPETS))
def test_contract_rejects_every_production_blocked_pattern(pattern):
    code = "fig = 1\n" + _SNIPPETS[pattern] + OK_TAIL
    assert ContractViolation.BLOCKED_IMPORT in validate_chart_code(code)
    # and the snippet really is what production blocks
    assert re.search(pattern, code.lower())


def test_oracle_exec_globals_match_production_allowed_modules():
    allowed = _production().allowed_modules
    runner = (Path(__file__).resolve().parent.parent / "_candidate_runner.py").read_text()
    m = re.search(r"exec\(code, (\{.*?\})\)", runner)
    assert m, "cannot find exec globals in _candidate_runner.py"
    oracle_names = {k.strip("\"'") for k in re.findall(r"[\"'](\w+)[\"']\s*:", m.group(1))} - {"df"}
    # production also registers dotted aliases for the same objects
    assert oracle_names == {k for k in allowed if "." not in k}


def test_exactly_one_terminal_json_print_is_required():
    assert validate_chart_code("fig = 1\nprint(fig.to_json())\n") == []
    assert ContractViolation.EXTRA_PRINT in validate_chart_code("fig = 1\nprint(df)\nprint(fig.to_json())\n")
    assert ContractViolation.NO_JSON_PRINT in validate_chart_code("fig = 1\nprint(fig.to_json())\nprint(fig.to_json())\n")
    assert ContractViolation.NO_JSON_PRINT in validate_chart_code("fig = 1\nprint(fig.to_json())\nx = 2\n")
