from gen_v2_targets import BUCKET_OF_KIND, assign


def test_assign_spreads_kinds_over_train_schemas_only():
    schemas = [{"schema_id": f"s{i}", "split": "test" if i % 3 == 0 else "train"} for i in range(9)]
    pairs = assign({"funnel": 4, "kpi": 2}, schemas)
    assert len(pairs) == 6
    assert all(s["split"] == "train" for _, s in pairs)
    assert {s["schema_id"] for k, s in pairs if k == "funnel"} == {"s1", "s2", "s4", "s5"}


def test_new_kinds_map_to_the_old_buckets():
    assert BUCKET_OF_KIND["waterfall"] == "treemap_funnel_waterfall"
    assert BUCKET_OF_KIND["kpi"] == "gauge_or_indicator"
