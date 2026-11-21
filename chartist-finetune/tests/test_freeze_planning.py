import freeze_planning_testset as freeze


def test_keeps_one_written_and_one_empty_request_per_test_schema():
    rows = [
        {"request_id": "a1", "schema_id": "s1", "split": "test", "request": "churn by country"},
        {"request_id": "a2", "schema_id": "s1", "split": "test", "request": "is revenue growing"},
        {"request_id": "a3", "schema_id": "s1", "split": "test", "request": ""},
        {"request_id": "b1", "schema_id": "s2", "split": "train", "request": "x"},
    ]
    kept = freeze.select(rows)
    assert [r["request_id"] for r in kept] == ["a1", "a3"]
