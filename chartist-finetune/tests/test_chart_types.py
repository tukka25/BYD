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
