"""The planner's data tools: facts about the real data, always bounded."""
import json

import pandas as pd

from app.services.agents import architect
from app.services.agents.data_tools import (EXPLORER_TOOL_NAMES, MAX_PREVIEW_PLANS, PLANNER_TOOL_NAMES,
                                            RESULT_CHARS, ToolBox, _fit_lines, bounded, chart_shape, find_columns,
                                            inspect_column, preview, relationship, repeated_x, row_grain)
from app.services.agents.profiler import profile_table

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TRACKS = pd.DataFrame({
    "track_name": ["Poison"] * 3 + [f"Song {i}" for i in range(37)],
    "playlist_genre": ["pop", "rap", "rock", "edm"] * 10,
    "track_popularity": [10, 20, 30, 40] * 10,
    "released": ["2019-01-01"] * 10 + [f"2019-{1 + i % 9:02d}-{10 + i % 9}" for i in range(30)],
    "weekday": (DAYS * 6)[:40],
})


def test_find_columns_matches_names_and_values():
    by_name = find_columns({"tracks": TRACKS}, "genre")
    by_value = find_columns({"tracks": TRACKS}, "pop")
    assert by_name["matches"][0]["column"] == "playlist_genre"
    assert by_value["matches"][0]["column"] == "playlist_genre"


def test_find_columns_says_when_nothing_matches_and_offers_the_measures():
    found = find_columns({"tracks": TRACKS}, "listens")
    assert found["matches"] == [] and "No column matches 'listens'" in found["fact"]
    assert "tracks.track_popularity" in found["fact"]


def test_find_columns_caps_a_wide_table():
    wide = pd.DataFrame({f"metric_{i}": [1.0, 2.0] for i in range(400)})
    found = find_columns({"wide": wide}, "metric")
    assert len(found["matches"]) == 10 and found["total"] == 400
    assert len(bounded(found)) <= RESULT_CHARS


def test_inspect_reports_values_that_repeat():
    facts = inspect_column(TRACKS, "tracks", "track_name")
    assert facts["values_on_more_than_one_row"] == 1 and "up to 3 rows" in facts["fact"]


def test_inspect_flags_year_only_dates():
    facts = inspect_column(TRACKS, "tracks", "released")
    assert facts["on_1_january"] == 0.25 and "1 January" in facts["fact"]


def test_inspect_finds_a_natural_order():
    assert inspect_column(TRACKS, "tracks", "weekday")["natural_order"] == "Monday to Sunday"


def test_inspect_gives_quartiles_for_numbers():
    facts = inspect_column(TRACKS, "tracks", "track_popularity")
    assert (facts["median"], facts["p25"], facts["p75"]) == (25.0, 17.5, 32.5)


def test_bounded_marks_what_it_cut():
    text = bounded({"fact": "x", "values": ["v" * 30] * 1000})
    parsed = json.loads(text)
    assert len(text) <= RESULT_CHARS and parsed["truncated"] is True
    assert len(parsed["values"]) + parsed["omitted"]["values"] == 1000


def test_find_columns_matches_values_on_a_large_table():
    # 6,000 rows: the value match runs on the 2,000-row sample, and a value on half the rows is in it.
    big = pd.DataFrame({"city": ["Oslo", "Bergen"] * 3000, "amount": range(6000)})
    found = find_columns({"big": big}, "oslo")
    assert found["matches"][0]["column"] == "city"


def test_distinct_counts_the_whole_column_not_the_sample():
    # 5,000 unique codes on 6,000 rows: the sample holds fewer, but the reported count must be the true one.
    big = pd.DataFrame({"code": [f"c{i}" for i in range(5000)] + ["c0"] * 1000})
    found = find_columns({"big": big}, "code")
    assert found["matches"][0]["distinct"] == 5000




def toolbox(**frames):
    return ToolBox({name: {"type": "file", "name": name} for name in frames}, "",
                   loader=lambda source, data_dir: frames[source["name"]])


def test_relationship_between_two_numbers_is_a_correlation():
    frame = pd.DataFrame({"a": [1, 2, 3, 4, 5, 6], "b": [2, 4, 6, 8, 10, 13]})
    facts = relationship(frame, "t", "a", "b")
    assert facts["correlation"] > 0.99 and "strong correlation" in facts["fact"]


def test_relationship_between_a_category_and_a_number_is_a_mean_per_group():
    facts = relationship(TRACKS, "tracks", "playlist_genre", "track_popularity")
    assert facts["groups"] == 4 and len(facts["means"]) == 4


def test_preview_says_a_sum_adds_up_repeated_names():
    facts = preview(TRACKS, "tracks", "track_name", "track_popularity", "sum", top_n=5)
    assert facts["groups"] == 38 and facts["shown"] == 5
    assert facts["rows_per_x"] == {"min": 1, "max": 3} and "sums 1 to 3 rows" in facts["fact"]


def test_the_toolbox_teaches_when_a_column_is_wrong():
    box = toolbox(tracks=TRACKS)
    reply = json.loads(box.call("inspect_column", {"table": "tracks", "column": "genre"}))
    assert "not a column of 'tracks'" in reply["error"] and "playlist_genre" in reply["error"]


def test_the_toolbox_stops_at_its_budget():
    box = toolbox(tracks=TRACKS)
    for _ in range(3):
        box.call("find_columns", {"query": "genre"})
    reply = json.loads(box.call("find_columns", {"query": "genre"}))
    assert box.exhausted and "budget" in reply["error"] and len(box.calls) == 3


def test_validate_refuses_a_bar_per_row_and_accepts_it_cut_to_top_n():
    names = pd.DataFrame({"name": [f"n{i}" for i in range(60)], "v": range(60)})
    box = toolbox(t=names)
    bar = {"chart": "bar", "table": "t", "x": "name", "y": "v", "agg": "sum", "group": "", "top_n": 0, "grain": ""}
    assert "60 bars" in box.validate_spec(bar)[0]
    assert box.validate_spec({**bar, "top_n": 20}) == []


def test_validate_refuses_a_line_through_every_raw_row():
    rows = pd.DataFrame({"t": range(1500), "v": range(1500)})
    line = {"chart": "line", "table": "r", "x": "t", "y": "v", "agg": "none", "group": "", "top_n": 0, "grain": ""}
    assert "1,500 points" in toolbox(r=rows).validate_spec(line)[0]


def test_a_tool_that_cannot_load_its_table_reports_instead_of_raising():
    def broken(source, data_dir):
        raise OSError("connection refused")
    box = ToolBox({"t": {"type": "file", "name": "t"}}, "", loader=broken)
    reply = json.loads(box.call("inspect_column", {"table": "t", "column": "x"}))
    assert "connection refused" in reply["error"] and len(box.calls) == 1


def test_validate_counts_line_points_per_line_not_across_lines():
    months = pd.DataFrame({"m": list(range(150)) * 10, "s": [f"s{i}" for i in range(10) for _ in range(150)], "v": range(1500)})
    line = {"chart": "line", "table": "r", "x": "m", "y": "v", "agg": "sum", "group": "s", "top_n": 0, "grain": ""}
    assert toolbox(r=months).validate_spec(line) == []


WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOURS = pd.DataFrame({"weekday": [day for day in WEEK for _ in range(24)], "hourOfDay": list(range(24)) * 7,
                      "bounceRatePct": [30 + (i * 7) % 40 for i in range(168)]})
RAW_LINE = {"chart": "line", "table": "web", "x": "hourOfDay", "y": "bounceRatePct", "agg": "none", "group": "",
            "top_n": 0, "grain": ""}


def test_a_raw_line_whose_x_repeats_goes_back_in_plain_words():
    # 168 rows, one per weekday and hour, drawn over the hour alone: the line ran back and forth 7 times.
    assert toolbox(web=HOURS).validate_spec(RAW_LINE) == [
        "x 'hourOfDay' has 24 values over 168 rows (each appears 7 times), so one line would run back and "
        "forth: set agg (mean for rates, sum for totals) or a group"]


def test_the_line_is_fine_aggregated_or_split_by_its_other_key():
    box = toolbox(web=HOURS)
    assert box.validate_spec({**RAW_LINE, "agg": "mean"}) == []
    assert box.validate_spec({**RAW_LINE, "group": "weekday"}) == []


def test_a_grouped_line_that_still_repeats_names_its_group():
    problem = repeated_x(HOURS.assign(device=["desktop", "mobile"] * 84), "hourOfDay", "device")
    assert "(each appears 7 times within one 'device' line)" in problem and "or another group" in problem


def test_markers_may_repeat_x():
    assert toolbox(web=HOURS).validate_spec({**RAW_LINE, "chart": "scatter"}) == []


def test_the_shape_line_and_the_plan_check_give_one_answer():
    shape, problems = chart_shape(HOURS, RAW_LINE)
    assert problems == toolbox(web=HOURS).validate_spec(RAW_LINE)
    assert shape == "line bounceRatePct by hourOfDay: 168 points per line, x repeats within a line, values 30 to 69"
    bars = {**RAW_LINE, "chart": "bar", "x": "weekday", "agg": "mean"}
    assert chart_shape(HOURS, bars) == ("bar mean of bounceRatePct by weekday: 7 bars (limit 50), values 48.5 to 50.8", [])


DAYS7 = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
GRID = pd.DataFrame({"weekday": [day for day in DAYS7 for _ in range(24)], "hourOfDay": list(range(24)) * 7,
                     "sessions": [100 + (i * 37) % 900 for i in range(168)],
                     "bounceRatePct": [30.5 + (i * 7) % 40 for i in range(168)]})


def test_row_grain_names_the_columns_that_identify_a_row():
    assert row_grain(GRID, "web")["fact"] == (
        "web: one row per weekday × hourOfDay (168 rows); other columns describe the row")


def test_row_grain_takes_an_id_that_counts_the_rows():
    orders = pd.DataFrame({"order_id": range(1, 301), "region": ["N", "S", "E"] * 100,
                           "amount": [i * 1.5 for i in range(300)]})
    assert row_grain(orders, "orders")["key"] == ["order_id"]


def test_a_number_unique_by_chance_is_not_a_key():
    events = pd.DataFrame({"region": ["N", "S", "E", "W"] * 25, "sessions": [100 + 3 * i for i in range(100)]})
    assert row_grain(events, "events")["fact"] == (
        "events: no key found among the columns tried, alone or up to 3 together (100 rows)")


def test_a_key_the_sample_misses_is_caught_on_the_full_table(monkeypatch):
    # The first 2,000 rows (the sample here) never repeat shop and day; the last 200 do,
    # so that pair fails on the full table and the next candidate is tried.
    monkeypatch.setattr(architect, "spread_sample", lambda frame, rows: frame.head(rows))
    first = [{"shop": i // 200, "day": i % 200, "till": i % 3} for i in range(2000)]
    extra = [{"shop": 0, "day": i % 200, "till": 3} for i in range(200)]
    frame = pd.DataFrame(first + extra).assign(amount=[i * 0.5 for i in range(2200)])
    assert row_grain(frame, "t")["key"] == ["shop", "day", "till"]


def test_inspect_says_how_often_each_value_repeats():
    facts = inspect_column(GRID, "web", "hourOfDay")
    assert facts["rows_per_value"] == 7.0 and "each value appears about 7 times" in facts["fact"]


def test_row_grain_is_a_tool_only_where_it_is_offered():
    offered = ToolBox({"web": {"type": "file", "name": "web"}}, "", loader=lambda source, data_dir: GRID,
                      tools=EXPLORER_TOOL_NAMES + ("row_grain",))
    assert json.loads(offered.call("row_grain", {"table": "web"}))["key"] == ["weekday", "hourOfDay"]
    assert "no tool 'row_grain'" in json.loads(toolbox(web=GRID).call("row_grain", {"table": "web"}))["error"]


RAW = {"chart": "line", "table": "web", "x": "hourOfDay", "y": "bounceRatePct", "agg": "none"}


def planner_box(**frames):
    """A ToolBox as the planner holds it: its five tools, and the profile's kinds for the plan rules."""
    return ToolBox({name: {"type": "file", "name": name} for name in frames}, "",
                   loader=lambda source, data_dir: frames[source["name"]], tools=PLANNER_TOOL_NAMES,
                   kinds={name: profile_table(name, frame).kinds() for name, frame in frames.items()})


def test_preview_chart_gives_one_line_per_plan_with_the_checks_own_words():
    box = planner_box(web=GRID)
    plans = [RAW, {**RAW, "agg": "mean"}, {**RAW, "chart": "bar", "x": "weekday", "y": "sessions", "agg": "sum"}]
    lines = box.call("preview_chart", {"plans": plans}, compact=True).splitlines()
    assert len(lines) == 3 and len(box.calls) == 1
    assert lines[0].startswith("1. line bounceRatePct by hourOfDay: 168 points per line, x repeats within a line")
    assert lines[0].endswith("; problem: " + box.validate_spec({**RAW, "title": "t"})[0])
    assert lines[1].startswith("2. line mean of bounceRatePct by hourOfDay: 24 points per line, x once per line")
    assert lines[1].endswith("; ok")
    assert lines[2].startswith("3. bar sum of sessions by weekday: 7 bars (limit 50), values ") and lines[2].endswith("; ok")


def test_a_draft_without_agg_is_previewed_as_the_check_reads_it():
    box = planner_box(web=GRID)
    draft = {key: value for key, value in RAW.items() if key != "agg"}
    line = box.call("preview_chart", {"plans": [draft]}, compact=True)
    assert "x repeats within a line" in line
    assert line.endswith("; problem: " + box.validate_spec({**draft, "title": "t"})[0])


def test_a_bad_draft_gets_its_own_line_in_the_one_call():
    box = planner_box(web=GRID)
    plans = [{"chart": "pie", "table": "web", "x": "hourOfDay", "y": "sessions", "agg": "sum"},
             {"chart": "bar", "table": "web", "x": "nope", "y": "sessions", "agg": "sum"},
             "not a plan",
             {"chart": "kpi", "table": "web", "y": "sessions", "agg": "sum"}]
    lines = box.call("preview_chart", {"plans": plans}, compact=True).splitlines()
    assert len(lines) == 4 and len(box.calls) == 1
    assert "a pie needs a category column on x" in lines[0]
    assert "'nope' is not a column of 'web'" in lines[1]
    assert lines[2] == "3. not a chart plan: give chart, table, x, y, group, agg, grain, top_n"
    assert lines[3].startswith("4. kpi sum of sessions: one number, ") and lines[3].endswith("; ok")


def test_seven_long_plans_keep_a_line_each_within_the_cap():
    reply = planner_box(web=GRID).call("preview_chart", {"plans": [RAW] * 9})
    lines = json.loads(reply)["fact"].splitlines()
    assert len(reply) <= RESULT_CHARS and len(lines) == MAX_PREVIEW_PLANS + 1
    assert all(line.endswith("…") for line in lines[:MAX_PREVIEW_PLANS])
    assert lines[-1] == "(only the first 7 of 9 plans were previewed)"


def test_a_cut_line_keeps_what_the_planner_acts_on():
    lines = ["1. line y by x: " + "s" * 300 + "; problem: set agg", "2. bar y by x: 7 bars; ok"] * 4
    text = _fit_lines(lines, limit=400)
    assert len(text) <= 400 and len(text.splitlines()) == 8
    assert all(line.endswith("; problem: set agg") or line == "2. bar y by x: 7 bars; ok"
               for line in text.splitlines())


def test_compact_replies_are_the_fact_line_and_errors_stay_json():
    box = planner_box(web=GRID)
    assert box.call("inspect_column", {"table": "web", "column": "hourOfDay"}, compact=True).startswith(
        "web.hourOfDay: number, 24 distinct in 168 rows; each value appears about 7 times")
    reply = box.call("inspect_column", {"table": "web", "column": "hour"}, compact=True)
    assert "not a column of 'web'" in json.loads(reply)["error"]


def test_the_planner_and_the_explorer_get_their_own_tools():
    assert [t["function"]["name"] for t in planner_box(web=GRID).specs] == list(PLANNER_TOOL_NAMES)
    assert [t["function"]["name"] for t in toolbox(web=GRID).specs] == list(EXPLORER_TOOL_NAMES)


def test_preview_chart_takes_the_checking_turns_draft_numbers():
    box = planner_box(web=GRID)
    box.drafts = [RAW, {**RAW, "agg": "mean"}]
    lines = box.call("preview_chart", {"plans": [2, "1", 3]}, compact=True).splitlines()
    assert lines[0].startswith("2. line mean of bounceRatePct by hourOfDay: 24 points per line")
    assert lines[1].startswith("1. line bounceRatePct by hourOfDay: 168 points per line")
    assert lines[2] == "3. no draft plan 3; there are 2"
