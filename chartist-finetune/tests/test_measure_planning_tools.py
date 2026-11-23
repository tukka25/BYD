from measure_planning_tools import REPEATED_X_FIX, compare, compare_planner, draw_first, sign_test_p, summarize


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


def _drawn(rendered=True, kind_ok=True, repairs=0, repeated_x=0):
    return {"chart": "line", "rendered": rendered, "kind_ok": kind_ok, "repairs": repairs,
            "repeated_x": repeated_x, "error": "", "seconds": 5.0}


def test_summarize_adds_draw_scores_only_when_charts_were_drawn():
    assert "render_rate" not in summarize([_row("a")])
    rows = [{**_row("a"), "drawn": [_drawn(), _drawn(rendered=False, kind_ok=False, repairs=2)], "draw_seconds": 20.0},
            {**_row("b"), "drawn": [_drawn(kind_ok=False, repairs=1, repeated_x=1)], "draw_seconds": 10.0}]
    s = summarize(rows)
    assert s["charts_drawn"] == 3 and s["render_rate"] == 2 / 3 and s["planned_kind_rate"] == 0.5
    assert s["repairs_per_chart"] == 1.0 and s["repeated_x_per_dashboard"] == 0.5 and s["median_draw_seconds"] == 15.0


def test_draw_first_scores_each_chart_and_counts_lines_drawn_back_and_forth():
    loopy = "the line 'x' has 168 points but only 24 x values, so it runs back and forth: " + REPEATED_X_FIX

    def run(spec, source, chartist, data_dir):
        if spec["chart"] == "line":
            return {"execution_result": {"figure": {"data": [{"type": "scatter", "mode": "lines"}]}}, "error": "",
                    "code": "fig = px.line(d)", "repairs": 1, "repair_reasons": [loopy]}
        return {"execution_result": {}, "error": "The model could not draw this chart: " + loopy, "code": "",
                "repairs": 2, "repair_reasons": [loopy, loopy]}

    drawn = draw_first([{"chart": "line"}, {"chart": "area"}, {"chart": "bar"}], {}, None, "", 2, run=run)
    assert [(d["rendered"], d["kind_ok"], d["repairs"], d["repeated_x"]) for d in drawn] == [
        (True, True, 1, 1), (False, False, 2, 3)]


def _draw_arms():
    on, planner = [], []
    for rid in "abcd":
        on.append({**_row(rid, planner_attempts=2, seconds=60.0), "drawn": [_drawn(repeated_x=1)], "draw_seconds": 9.0})
        planner.append({**_row(rid, planner_attempts=1, seconds=75.0), "drawn": [_drawn()], "draw_seconds": 8.0,
                        "tool_calls": ["preview_chart"]})
    return on, planner


def test_compare_planner_applies_the_default_rule():
    on, planner = _draw_arms()
    result = compare_planner(on, planner)
    assert result["paired_rows"] == 4 and result["first_try"]["planner_better"] == 4
    assert result["decision"] == {"render_not_lower": True, "first_try_not_lower": True,
                                  "planned_kind_not_lower": True, "repeated_x_not_higher": True,
                                  "median_seconds_rise_under_30": True, "planner_uses_tools": True,
                                  "planner_by_default": True}


def test_compare_planner_keeps_on_when_the_planner_is_slow_or_draws_more_loops():
    on, planner = _draw_arms()
    slow = [{**r, "seconds": r["seconds"] + 30.0} for r in planner]
    assert compare_planner(on, slow)["decision"]["planner_by_default"] is False
    loopy = [{**r, "drawn": [_drawn(repeated_x=2)]} for r in planner]
    decision = compare_planner(on, loopy)["decision"]
    assert decision["repeated_x_not_higher"] is False and decision["planner_by_default"] is False


def test_compare_planner_keeps_on_when_the_planner_calls_no_tool():
    on, planner = _draw_arms()
    decision = compare_planner(on, [{**r, "tool_calls": []} for r in planner])["decision"]
    assert decision["planner_uses_tools"] is False and decision["planner_by_default"] is False
