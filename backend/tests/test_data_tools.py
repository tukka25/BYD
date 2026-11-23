"""The planner's data tools: facts about the real data, always bounded."""
import json

import pandas as pd

from app.services.agents.data_tools import RESULT_CHARS, bounded, find_columns, inspect_column

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


from app.services.agents.data_tools import ToolBox, preview, relationship


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
