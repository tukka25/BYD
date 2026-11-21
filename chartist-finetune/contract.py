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
