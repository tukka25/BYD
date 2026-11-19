from contract import BACKEND_CONTRACT, CHARTIST_SYSTEM_PROMPT, validate_chart_code


def test_backend_contract_is_reachable():
    assert BACKEND_CONTRACT.is_file(), f"{BACKEND_CONTRACT} missing — run Task 1 first"


def test_contract_loads_and_works():
    assert "print(fig.to_json())" in CHARTIST_SYSTEM_PROMPT
    assert validate_chart_code("fig = 1\nprint(fig.to_json())\n") == []
