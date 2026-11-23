from measure_planning_tools import compare, sign_test_p, summarize


def _row(rid, directions=5, charts=5, planner_attempts=1, analyst_attempts=1, seconds=10.0):
    return {"request_id": rid, "directions": directions, "charts": charts,
            "planner_attempts": planner_attempts, "analyst_attempts": analyst_attempts,
            "dropped": 0, "tool_calls": [], "seconds": seconds}


def test_summarize_keeps_the_old_keys_and_values():
    rows = [
        {**_row("a", directions=5, charts=4, planner_attempts=2, analyst_attempts=1), "dropped": 1,
         "tool_calls": ["inspect_column"], "seconds": 10.0},
        _row("b", directions=0, charts=0, planner_attempts=0, analyst_attempts=3, seconds=30.0),
    ]
    s = summarize(rows)
    assert s["rows"] == 2
    assert s["analyst_usable_rate"] == 0.5
    assert s["analyst_retry_rate"] == 0.5
    assert s["planner_first_try_rate"] == 0.0
    assert s["mean_charts"] == 4.0
    assert s["dropped_per_dashboard"] == 1.0
    assert s["tool_calls_per_dashboard"] == 0.5
    assert s["median_seconds"] == 20.0


def test_summarize_counts_a_zero_chart_dashboard_as_a_miss():
    rows = [
        _row("a", directions=4, charts=4, planner_attempts=1),
        _row("b", directions=3, charts=0, planner_attempts=2),
        _row("c", directions=0, charts=0, planner_attempts=0),
    ]
    s = summarize(rows)
    assert s["asked_rows"] == 2
    assert s["first_try_rate_counting_failures"] == 0.5
    assert s["total_failure_rate"] == 0.5
    assert s["charts_dropped_per_dashboard"] == 1.5
    # the old rate still leaves the zero-chart dashboard out
    assert s["planner_first_try_rate"] == 1.0


def test_sign_test_known_cases():
    assert sign_test_p(2, 2) == 1.0
    assert sign_test_p(5, 0) == 0.0625
    assert sign_test_p(0, 0) == 1.0


def _paired_arms():
    # five rows where tools-on planned first try and kept every chart,
    # one row with no directions in either arm, one row only in the off arm
    off, on = [], []
    for rid in "abcde":
        off.append(_row(rid, directions=5, charts=3, planner_attempts=2, seconds=10.0))
        on.append(_row(rid, directions=5, charts=5, planner_attempts=1, seconds=12.0))
    off.append(_row("f", directions=0, charts=0, planner_attempts=0, seconds=10.0))
    on.append(_row("f", directions=0, charts=0, planner_attempts=0, seconds=14.0))
    off.append(_row("only-off", directions=5, charts=5, planner_attempts=1))
    return off, on


def test_compare_pairs_rows_and_counts_both_metrics():
    off, on = _paired_arms()
    c = compare(off, on)
    assert c["paired_rows"] == 6
    assert c["first_try"]["on_better"] == 5 and c["first_try"]["off_better"] == 0
    assert c["first_try"]["p"] == 0.0625
    assert c["charts_dropped"]["on_fewer"] == 5 and c["charts_dropped"]["off_fewer"] == 0
    assert c["charts_dropped"]["p"] == 0.0625
    assert c["median_seconds_delta"] == 2.0


def test_compare_decision_applies_the_no_harm_rule():
    off, on = _paired_arms()
    d = compare(off, on)["decision"]
    assert d == {"first_try_not_lower": True, "dropped_not_higher": True,
                 "analyst_usable_not_lower": True, "median_seconds_rise_under_30": True,
                 "tools_on_by_default": True}


def test_compare_decision_turns_off_when_on_is_slow():
    off, on = _paired_arms()
    for r in on:
        r["seconds"] += 40.0
    d = compare(off, on)["decision"]
    assert d["median_seconds_rise_under_30"] is False
    assert d["tools_on_by_default"] is False
