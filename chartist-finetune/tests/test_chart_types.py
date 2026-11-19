import json
from pathlib import Path

from chart_types import QUOTA, TRACE_TYPES, allocate, is_area_figure


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


def test_is_area_figure_separates_area_from_scatter_family_on_committed_data():
    rows = [json.loads(l) for l in Path("data/targets.jsonl").read_text().splitlines() if l]
    area = [r for r in rows if r["chart_bucket"] == "area"]
    others = [r for r in rows if r["chart_bucket"] in {"line", "scatter", "time_series"}]
    assert len(area) > 100 and len(others) > 100
    assert all(is_area_figure(r["messages"][-1]["content"]) for r in area)
    assert not any(is_area_figure(r["messages"][-1]["content"]) for r in others)
