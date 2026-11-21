"""Loads the backend chartist contract by path, so there is no copy to drift."""
from __future__ import annotations

import importlib.util
import sys
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
# Re-exported so a dataset built with a chart-type hint uses the SAME wording
# the live call sends. If these two ever diverge, the model is served a prompt
# shape it was not trained on and the eval numbers stop meaning anything.
CHART_TYPE_PHRASE = _backend.CHART_TYPE_PHRASE
CHART_TYPE_LABEL = _backend.CHART_TYPE_LABEL
chart_type_hint = _backend.chart_type_hint
names_a_chart = _backend.names_a_chart
# The generation cap the live chartist call uses, so an eval cannot fail a long
# answer the app would have accepted.
CHARTIST_MAX_TOKENS = _backend.CHARTIST_MAX_TOKENS
render_spec = _backend.render_spec

# The dashboard planner's prompts, checks and table descriptions. Loaded by path
# for the same reason as the chartist contract: a training row and a live call
# must describe a table and ask for a plan with byte-identical text.
_AGENTS = BACKEND_CONTRACT.parent


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(f"backend_{name}", _AGENTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {_AGENTS / (name + '.py')}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


_profiler = _load_module("profiler")
_planning = _load_module("planning_contract")

profile_table = _profiler.profile_table
render_profiles = _profiler.render_profiles
columns_by_table = _profiler.columns_by_table

for _name in (
    "CHART_KINDS", "KIND_TRACES", "NO_REQUEST", "SPEC_RULES",
    "ANALYST_SYSTEM_PROMPT", "ANALYST_USER_TEMPLATE",
    "PLANNER_SYSTEM_PROMPT", "PLANNER_USER_TEMPLATE", "FIX_PROMPT",
    "ANALYST_MAX_TOKENS", "PLANNER_MAX_TOKENS",
    "DIRECTIONS_SCHEMA", "SPEC_SCHEMA", "SPECS_SCHEMA",
    "extract_json", "check_directions", "check_spec", "check_specs", "render_directions",
):
    globals()[_name] = getattr(_planning, _name)
