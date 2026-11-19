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
