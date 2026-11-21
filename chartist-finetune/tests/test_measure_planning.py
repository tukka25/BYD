from measure_planning import plan_matches, summarize


def test_plan_matches_uses_traces_and_the_area_tie_break():
    assert plan_matches("bar", "bar", "")
    assert not plan_matches("pie", "bar", "")
    assert plan_matches("area", "scatter", "fig = px.area(d)")
    assert not plan_matches("line", "scatter", "fig = px.area(d)")
    assert not plan_matches("bar", None, "")


def test_summarize_counts_each_stage():
    rows = [
        {"directions": 5, "direction_errors": 0, "charts": 4, "chart_errors": 1, "analyst_attempts": 1,
         "planner_attempts": 2, "drawn": [{"ok": True, "match": True}, {"ok": False, "match": False}]},
        {"directions": 0, "direction_errors": 2, "charts": 0, "chart_errors": 0, "analyst_attempts": 3,
         "planner_attempts": 0, "drawn": []},
    ]
    s = summarize(rows)
    assert s["analyst_ok_rate"] == 0.5 and s["planner_ok_rate"] == 1.0
    assert s["render_rate"] == 0.5 and s["plan_match_rate"] == 1.0 and s["right_chart_rate"] == 0.5
