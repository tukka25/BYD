import base64
import json

import numpy as np
import pandas as pd

from ab_agg_rule import (
    breakdown, compare, drawn_bar_values, expected_bar_values, frozen_decision, frozen_items, live_decision,
    live_items, points_drawn, score, summarize, values_ok,
)

WEB = pd.DataFrame({
    "weekday": ["Mon", "Mon", "Mon", "Tue", "Tue", "Tue"],
    "rate": [40.0, 50.0, 60.0, 10.0, 20.0, 30.0],
    "sessions": [1, 2, 3, 4, 5, 6],
})
BAR_MEAN = {"chart": "bar", "x": "weekday", "y": "rate", "agg": "mean", "group": "", "grain": "", "top_n": 0}
RAW_BARS = {"data": [{"type": "bar", "x": ["Mon"] * 3 + ["Tue"] * 3, "y": [40, 50, 60, 10, 20, 30]}]}


def typed(values):
    return {"dtype": "f8", "bdata": base64.b64encode(np.array(values, dtype="f8").tobytes()).decode()}


def result(figure, error="", reasons=()):
    return {"code": "fig = px.bar(df)", "execution_result": {"figure": figure} if figure else {},
            "error": error, "repairs": len(reasons), "repair_reasons": list(reasons)}


def test_expected_values_are_the_plans_own_groupby():
    assert expected_bar_values(WEB, BAR_MEAN) == [[50.0, 20.0]]
    assert expected_bar_values(WEB, {**BAR_MEAN, "agg": "sum", "y": "sessions"}) == [[6.0, 15.0]]


def test_a_group_gives_one_value_per_pair():
    frame = WEB.assign(device=["a", "b", "a", "a", "b", "b"])
    assert sorted(expected_bar_values(frame, {**BAR_MEAN, "group": "device"})[0]) == [10.0, 25.0, 50.0, 50.0]


def test_a_count_accepts_rows_or_non_empty_values():
    frame = WEB.assign(rate=[40.0, None, 60.0, 10.0, 20.0, 30.0])
    assert expected_bar_values(frame, {**BAR_MEAN, "agg": "count"}) == [[3.0, 3.0], [2.0, 3.0]]
    assert expected_bar_values(WEB, {**BAR_MEAN, "agg": "count"}) == [[3.0, 3.0]]
    assert expected_bar_values(WEB, {**BAR_MEAN, "agg": "count", "y": ""}) == [[3.0, 3.0]]


def test_not_checked_with_a_time_grain_a_missing_column_or_another_kind():
    assert expected_bar_values(WEB, {**BAR_MEAN, "grain": "month"}) is None
    assert expected_bar_values(WEB, {**BAR_MEAN, "y": "nope"}) is None
    assert expected_bar_values(WEB, {**BAR_MEAN, "chart": "line"}) is None
    assert expected_bar_values(WEB, {**BAR_MEAN, "agg": "none"}) is None


def test_drawn_values_sum_each_traces_rows_per_category_as_plotly_stacks_them():
    assert drawn_bar_values(RAW_BARS) == [150.0, 60.0]
    horizontal = {"data": [{"type": "bar", "orientation": "h", "y": ["Mon", "Tue"], "x": [50, 20]}]}
    assert drawn_bar_values(horizontal) == [50.0, 20.0]
    per_colour = {"data": [{"type": "bar", "name": d, "x": [d] * 3, "y": v}
                           for d, v in (("Mon", [40, 50, 60]), ("Tue", [10, 20, 30]))]}
    assert drawn_bar_values(per_colour) == [150.0, 60.0]
    assert drawn_bar_values({"data": [{"type": "scatter", "x": [1], "y": [2]}]}) is None


def test_values_ok_allows_rounding_and_respects_top_n():
    assert values_ok([[50.0, 20.0]], [50.0, 20.0], 0) is True
    assert values_ok([[49.43, 20.0]], [49.4, 20.0], 0) is True
    assert values_ok([[50.0, 20.0]], [150.0, 60.0], 0) is False
    assert values_ok([[50.0, 20.0, 5.0]], [50.0, 20.0], 2) is True
    assert values_ok([[50.0, 20.0, 5.0]], [50.0], 0) is False
    assert values_ok([[3.0, 3.0], [2.0, 3.0]], [2.0, 3.0], 0) is True
    assert values_ok(None, [1.0], 0) is None
    assert values_ok([[1.0]], None, 0) is None


def test_points_drawn_counts_the_longest_axis_of_every_trace():
    figure = {"data": [{"type": "scatter", "x": [1, 2, 3], "y": [1, 2, 3]}, {"type": "box", "y": [1, 2]}]}
    assert points_drawn(figure) == 5


def test_score_reads_a_run_like_the_app_shows_it():
    raw = score(BAR_MEAN, WEB, result(RAW_BARS))
    assert raw["rendered"] and raw["kind_ok"]
    assert raw["raw_bars"] == 1 and raw["values_ok"] is False
    good = score(BAR_MEAN, WEB, result({"data": [{"type": "bar", "x": ["Mon", "Tue"], "y": typed([50.0, 20.0])}]}))
    assert good["raw_bars"] == 0 and good["values_ok"] is True
    failed = score(BAR_MEAN, WEB, result(None, error="boom"))
    assert not failed["rendered"] and failed["values_ok"] is False
    as_pie = score(BAR_MEAN, WEB, result({"data": [{"type": "pie", "labels": ["Mon", "Tue"], "values": [50, 20]}]}))
    assert as_pie["rendered"] and not as_pie["kind_ok"] and as_pie["values_ok"] is False


def test_score_records_points_only_for_raw_kinds_and_counts_line_repairs():
    scatter = {"chart": "scatter", "x": "rate", "y": "sessions", "agg": "none", "group": "", "grain": ""}
    drawn = score(scatter, WEB, result({"data": [{"type": "scatter", "mode": "markers", "x": list(range(6)),
                                                   "y": list(range(6))}]}))
    assert drawn["points"] == 6 and drawn["values_ok"] is None
    assert score(BAR_MEAN, WEB, result(RAW_BARS))["points"] is None
    from app.services.agents.chartist_contract import REPEATED_X_FIX
    line = score({"chart": "line", "x": "weekday", "y": "rate", "agg": "mean", "group": "", "grain": ""}, WEB,
                 result({"data": [{"type": "scatter", "mode": "lines", "x": ["Mon", "Tue"], "y": [50, 20]}]},
                        reasons=[f"the line 'x' ...: {REPEATED_X_FIX}"]))
    assert line["repeated_x"] == 1 and line["repairs"] == 1


def test_score_and_summary_count_bars_the_drawing_check_sent_back():
    from app.services.agents.chartist_contract import REPEATED_BAR_FIX
    stacked = ("the bar series 'trace 1' has 6 bars on 2 categories, and Plotly stacks bars that share a category: "
               + REPEATED_BAR_FIX)
    good = {"data": [{"type": "bar", "x": ["Mon", "Tue"], "y": typed([50.0, 20.0])}]}
    scored = score(BAR_MEAN, WEB, result(good, reasons=[stacked]))
    assert scored["repeated_bars"] == 1 and scored["repeated_x"] == 0 and scored["values_ok"] is True
    failed = score(BAR_MEAN, WEB, result(None, error="The model could not draw this chart: " + stacked,
                                         reasons=[stacked, stacked]))
    assert failed["repeated_bars"] == 3
    # Rows saved before the count existed count none.
    rows = [_row("a", on={"repeated_bars": 2}), _row("b")]
    assert summarize(rows, "on")["bars_sent_back"] == 2 and summarize(rows, "off")["bars_sent_back"] == 0


def _row(item, chart="bar", agg="mean", off=None, on=None, group=""):
    base = {"rendered": True, "kind_ok": True, "repairs": 0, "repeated_x": 0, "raw_bars": 0, "values_ok": True,
            "points": None, "seconds": 1.0, "error": ""}
    return {"item_id": item, "spec": {"chart": chart, "agg": agg, "group": group, "title": item.upper()},
            "arms": {"off": {**base, **(off or {})}, "on": {**base, **(on or {})}}}


def test_summarize_counts_one_arm():
    rows = [_row("a", off={"raw_bars": 2, "values_ok": False}), _row("b", chart="line", off={"values_ok": None})]
    s = summarize(rows, "off")
    assert s["charts"] == 2 and s["render_rate"] == 1.0
    assert s["raw_row_bar_charts"] == 1
    assert s["bar_values_checked"] == 1 and s["bar_values_ok"] == 0


def test_live_passes_only_when_on_fixes_the_raw_bars_and_loses_nothing():
    rows = [_row("a", off={"raw_bars": 1, "values_ok": False}), _row("b")]
    decision = live_decision(rows)
    assert decision["passes"] and decision["off_draws_raw_row_bars"] and decision["on_draws_no_raw_row_bars"]
    assert not live_decision(rows + [_row("c", chart="line", on={"rendered": False, "kind_ok": False})])["passes"]
    assert not live_decision([_row("a", off={"raw_bars": 1}, on={"raw_bars": 1})])["passes"]
    # The off arm never failed: the harness is not the app's path.
    assert not live_decision([_row("a")])["passes"]


def test_frozen_is_a_no_harm_rule():
    rows = [_row("a"), _row("b", off={"raw_bars": 1, "values_ok": False})]
    assert frozen_decision(rows)["passes"]
    worse = rows + [_row("c", on={"values_ok": False}), _row("d", on={"values_ok": False})]
    assert not frozen_decision(worse)["bar_values_not_fewer"]
    assert not frozen_decision(rows + [_row("e", on={"rendered": False, "kind_ok": False})])["passes"]


def test_breakdown_splits_grouped_bars_and_names_every_chart_one_arm_lost():
    failed = {"rendered": False, "kind_ok": False, "values_ok": False}
    rows = [
        _row("plain"),
        _row("lost", group="device", on={**failed, "error": "boom"}),
        _row("fixed", group="device", off={"values_ok": False}),
        _row("broke", on={"values_ok": False}),
        _row("gained", chart="line", agg="none", off={**failed, "values_ok": None}, on={"values_ok": None}),
    ]
    b = breakdown(rows)
    assert b["bars"]["grouped"]["off"] == {"plans": 2, "rendered": 2, "values_checked": 2, "values_ok": 1,
                                           "raw_row_bar_charts": 0}
    assert b["bars"]["grouped"]["on"] == {"plans": 2, "rendered": 1, "values_checked": 2, "values_ok": 1,
                                          "raw_row_bar_charts": 0}
    assert b["bars"]["ungrouped"]["on"]["values_ok"] == 1
    assert b["lost_on"] == [{"item_id": "lost", "chart": "bar", "group": "device", "title": "LOST",
                             "error": "boom"}]
    assert [x["item_id"] for x in b["gained_on"]] == ["gained"]
    # A value change counts only where both arms drew; a lost chart is listed once, as lost.
    assert [x["item_id"] for x in b["values_better_on"]] == ["fixed"]
    assert [x["item_id"] for x in b["values_worse_on"]] == ["broke"]
    assert b["by_kind"]["line"] == {"off": {"plans": 1, "rendered": 0, "kind_ok": 0},
                                    "on": {"plans": 1, "rendered": 1, "kind_ok": 1}}


def test_a_collapse_is_a_raw_chart_drawn_with_under_half_the_other_arms_points():
    rows = [_row("s", chart="scatter", agg="none", off={"points": 100, "values_ok": None},
                 on={"points": 7, "values_ok": None})]
    assert compare(rows)["collapsed"] == {"on_collapsed": 1, "off_collapsed": 0}
    assert not frozen_decision(rows)["collapsed_not_more"]


def test_frozen_items_take_every_distinct_bar_and_a_seeded_few_of_each_other_kind(tmp_path):
    schemas, rows = tmp_path / "schemas.jsonl", tmp_path / "rows.jsonl"
    schemas.write_text(json.dumps({"schema_id": "s1", "fixture_csv": "data/f.csv"}) + "\n")

    def spec(chart, x):
        return {"chart": chart, "table": "t", "x": x, "y": "v", "group": "", "agg": "mean", "grain": "", "sort": "",
                "top_n": 0, "title": x, "question": x}

    specs = [spec("bar", "a"), spec("bar", "a"), spec("bar", "b")] + [spec("line", str(i)) for i in range(5)]
    rows.write_text(json.dumps({"request_id": "r1", "schema_id": "s1", "specs": specs}) + "\n")
    items = frozen_items(rows, schemas, per_kind=2, seed=1)
    kinds = [item["spec"]["chart"] for item in items]
    assert kinds.count("bar") == 2 and kinds.count("line") == 2
    assert items == frozen_items(rows, schemas, per_kind=2, seed=1)
    assert all(item["csv"].endswith("data/f.csv") for item in items)


def test_live_items_are_the_saved_plans():
    items = live_items()
    assert len(items) == 23 and items[0]["item_id"] == "live-01"
    assert {"live-10", "live-22"} <= {item["item_id"] for item in items if item["spec"]["chart"] == "bar"}
