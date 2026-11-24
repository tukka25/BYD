from check_bar_repairs import PROBE_PLANS, bar_check_decision, probe_decision, unchanged


def test_the_probe_plans_group_bars_by_a_number_and_pass_only_if_all_draw_the_planned_values():
    assert [spec["group"] for _, spec in PROBE_PLANS] == ["bedroomCount", "year"]
    good = {"rendered": True, "values_ok": True}
    assert probe_decision([good, good])["passes"]
    assert not probe_decision([good, {"rendered": True, "values_ok": False}])["passes"]
    assert not probe_decision([good, {"rendered": False, "values_ok": False}])["passes"]


def _pair(item, before=None, after=None, code_after="same"):
    base = {"rendered": True, "kind_ok": True, "repairs": 0, "repeated_x": 0, "raw_bars": 0, "values_ok": True,
            "points": None, "seconds": 1.0, "error": "", "code": "same"}
    return {"item_id": item, "spec": {"chart": "bar", "agg": "mean"},
            "arms": {"before": {**base, **(before or {})},
                     "after": {**base, "repeated_bars": 0, "code": code_after, **(after or {})}}}


RAW = {"raw_bars": 1, "values_ok": False}


def test_passes_when_the_check_fixes_every_raw_row_bar_and_loses_nothing():
    rows = [_pair("a", before=RAW, after={"repeated_bars": 1, "repairs": 1}, code_after="grouped"), _pair("b")]
    decision = bar_check_decision(rows)
    assert decision["passes"] and decision["baseline_drew_raw_bars"] and decision["raw_bars_fixed_by_a_bar_repair"]


def test_fails_when_a_raw_row_bar_is_not_fixed_by_a_bar_repair():
    still_wrong = _pair("a", before=RAW, after={"repeated_bars": 1, "values_ok": False})
    assert not bar_check_decision([still_wrong])["passes"]
    # Right the first time is not the check's doing: it was never exercised.
    no_repair = _pair("a", before=RAW, code_after="grouped")
    assert not bar_check_decision([no_repair])["raw_bars_fixed_by_a_bar_repair"]


def test_fails_when_a_chart_that_drew_before_fails_now_or_values_drop():
    fixed = _pair("a", before=RAW, after={"repeated_bars": 1})
    lost = _pair("c", after={"rendered": False, "kind_ok": False, "values_ok": False})
    assert not bar_check_decision([fixed, lost])["no_chart_lost"]
    worse = _pair("d", after={"values_ok": False})
    assert not bar_check_decision([fixed, worse, _pair("e", after={"values_ok": False})])["values_not_fewer"]


def test_a_baseline_without_raw_row_bars_never_tested_the_check():
    assert not bar_check_decision([_pair("b")])["passes"]


def test_unchanged_counts_plans_whose_code_is_the_same_before_and_after():
    assert unchanged([_pair("a"), _pair("b", code_after="other")]) == 1
