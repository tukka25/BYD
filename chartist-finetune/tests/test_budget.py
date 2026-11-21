import json

import pytest

import client


def _ledger(tmp_path, rows):
    path = tmp_path / "spend.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_phase_spend_counts_only_that_phase(tmp_path):
    path = _ledger(tmp_path, [{"cost_usd": 5.0}, {"cost_usd": 1.25, "phase": "v2"}, {"cost_usd": 0.5, "phase": "v2"}])
    assert client.phase_spend("v2", path) == 1.75


def test_guard_refuses_past_the_cap(tmp_path):
    path = _ledger(tmp_path, [{"cost_usd": 34.0, "phase": "v2"}])
    client.guard("ok", 0.5, cap=35.0, ledger=path)
    with pytest.raises(SystemExit):
        client.guard("too much", 2.0, cap=35.0, ledger=path)


def test_worst_case_is_batched_and_uses_output_price():
    # 10 requests x (1,000 in at $4 + 16,000 out at $20) / 1M x 0.5
    assert client.worst_case_cost(client.OPUS, 10, 1000, 16000) == pytest.approx(1.62)
