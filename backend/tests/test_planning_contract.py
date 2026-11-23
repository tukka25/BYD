import hashlib
import json

from app.services.agents.planning_contract import (
    ANALYST_SYSTEM_PROMPT,
    CHART_KINDS,
    DIRECTIONS_SCHEMA,
    EXPLORER_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    SPEC_RULES,
    KIND_TRACES,
    SPECS_SCHEMA,
    check_directions,
    check_specs,
    extract_json,
    render_directions,
    with_context,
)

TABLES = {
    "saas": {
        "snap_dt": "date",
        "cntry_cd": "category",
        "plan_tier": "category",
        "churn_cnt": "number",
        "mrr_usd": "number",
        "row_no": "id",
    }
}


def spec(**overrides):
    base = {
        "title": "Churn by country", "question": "Where is churn highest?", "chart": "bar",
        "table": "saas", "x": "cntry_cd", "y": "churn_cnt", "group": "", "agg": "sum",
        "grain": "", "sort": "desc", "top_n": 0,
    }
    base.update(overrides)
    return base


def test_extract_json_finds_the_object_wherever_it_sits():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Sure.\n</think>\n\n{"a": {"b": 2}} trailing') == {"a": {"b": 2}}
    assert extract_json("no json here") is None
    assert extract_json(None) is None


def test_directions_valid():
    payload = {"directions": [{"question": "Where is churn highest?", "why": "asked",
                               "table": "saas", "columns": ["cntry_cd", "churn_cnt"]}]}
    valid, errors = check_directions(payload, TABLES)
    assert errors == [] and valid[0]["columns"] == ["cntry_cd", "churn_cnt"]


def test_directions_name_the_real_columns_when_one_is_wrong():
    payload = {"directions": [{"question": "q", "why": "", "table": "saas", "columns": ["country"]}]}
    valid, errors = check_directions(payload, TABLES)
    assert valid == []
    assert "'country' not in table 'saas'" in errors[0]
    assert "cntry_cd" in errors[0]


def test_directions_unknown_table_and_repeats():
    payload = {"directions": [
        {"question": "q", "why": "", "table": "nope", "columns": ["x"]},
        {"question": "Same", "why": "", "table": "saas", "columns": ["mrr_usd"]},
        {"question": "same", "why": "", "table": "saas", "columns": ["mrr_usd"]},
    ]}
    valid, errors = check_directions(payload, TABLES)
    assert len(valid) == 1
    assert any("table 'nope' does not exist" in e for e in errors)
    assert any("repeats" in e for e in errors)


def test_directions_wrong_shape():
    assert check_directions({"items": []}, TABLES) == ([], ['Reply with {"directions": [...]}.'])


def test_specs_valid_bar():
    valid, errors = check_specs({"charts": [spec()]}, TABLES)
    assert errors == [] and valid[0]["chart"] == "bar"


def test_specs_kind_rules():
    cases = [
        spec(chart="kpi", x="cntry_cd"),                       # kpi has no x
        spec(chart="line", x="cntry_cd"),                      # line needs time or number on x
        spec(chart="line", x="snap_dt", agg="none"),           # trend needs an aggregation
        spec(chart="bar", y="cntry_cd", agg="mean"),           # mean of a category
        spec(chart="histogram", x="cntry_cd", y="", agg="none"),
        spec(grain="month"),                                   # grain on a non-date x
        spec(chart="sankey"),
        spec(x="country"),
    ]
    for case in cases:
        valid, errors = check_specs({"charts": [case]}, TABLES)
        assert valid == [] and errors, case


def test_specs_count_needs_no_measure():
    valid, errors = check_specs({"charts": [spec(chart="kpi", x="", y="", agg="count")]}, TABLES)
    assert errors == [] and valid[0]["agg"] == "count"


def test_specs_time_trend_with_grain():
    valid, errors = check_specs(
        {"charts": [spec(chart="line", x="snap_dt", grain="month", sort="")]}, TABLES
    )
    assert errors == [] and valid[0]["grain"] == "month"


def test_specs_duplicates_dropped():
    valid, errors = check_specs({"charts": [spec(), spec(title="Again")]}, TABLES)
    assert len(valid) == 1 and any("same chart" in e for e in errors)


def test_every_kind_has_traces_and_schemas_are_json():
    assert set(KIND_TRACES) == set(CHART_KINDS)
    json.dumps(DIRECTIONS_SCHEMA)
    json.dumps(SPECS_SCHEMA)


def test_render_directions():
    text = render_directions([{"question": "Where is churn highest?", "why": "asked for",
                               "table": "saas", "columns": ["cntry_cd", "churn_cnt"]}])
    assert text == "1. Where is churn highest? Why: asked for. Table: saas. Columns: cntry_cd, churn_cnt."


def test_group_must_add_a_dimension():
    valid, errors = check_specs({"charts": [spec(group="cntry_cd")]}, TABLES)
    assert valid == [] and any("group must be a different column" in e for e in errors)


def test_count_of_the_x_column_is_a_row_count():
    valid, errors = check_specs({"charts": [spec(y="cntry_cd", agg="count")]}, TABLES)
    assert errors == [] and valid[0]["y"] == ""


TRACKS = {"tracks": {"track_name": "text", "track_id": "id", "track_popularity": "number"}}


def top_tracks(**overrides):
    return spec(**{"title": "Most popular tracks", "question": "Which tracks are most popular?",
                   "table": "tracks", "x": "track_name", "y": "track_popularity", "agg": "mean",
                   "sort": "desc", "top_n": 10, **overrides})


def test_a_bar_over_a_text_column_passes_when_top_n_limits_it():
    # "Top 10 tracks" is the chart a "most listened songs" request needs; it was
    # refused three times on the Spotify table and dropped from the dashboard.
    valid, errors = check_specs({"charts": [top_tracks()]}, TRACKS)
    assert errors == []
    assert (valid[0]["x"], valid[0]["top_n"]) == ("track_name", 10)


def test_a_bar_over_a_text_column_still_needs_a_short_top_n():
    # Without a cut, a bar per track is thousands of bars; the message must say how to fix it.
    for case in (top_tracks(top_n=0), top_tracks(top_n=500)):
        valid, errors = check_specs({"charts": [case]}, TRACKS)
        assert valid == [] and "top_n" in errors[0] and "track_name" in errors[0], case


def test_a_bar_over_an_id_column_is_refused_even_with_top_n():
    valid, errors = check_specs({"charts": [top_tracks(x="track_id")]}, TRACKS)
    assert valid == [] and errors


SONGS = {"tracks": {"track_name": "text", "playlist_name": "text", "playlist_genre": "category",
                    "playlist_subgenre": "category", "track_popularity": "number", "year": "year",
                    "released": "date"}}


def test_grain_on_a_year_column_says_to_remove_it():
    # gapminder lost all three trend charts to this: grain=year on a year column, three tries
    case = spec(table="tracks", chart="line", x="year", y="track_popularity", agg="mean",
                grain="year", sort="", top_n=0)
    valid, errors = check_specs({"charts": [case]}, SONGS)
    assert valid == [] and "already a year column" in errors[0] and 'grain to ""' in errors[0]


def test_a_treemap_over_free_text_names_the_category_columns():
    case = spec(table="tracks", chart="treemap", x="playlist_genre", group="playlist_name",
                y="track_popularity", agg="sum", sort="", top_n=0)
    valid, errors = check_specs({"charts": [case]}, SONGS)
    assert valid == [] and "'playlist_name' is text" in errors[0] and "playlist_subgenre" in errors[0]


def test_a_bar_without_aggregation_says_which_to_use():
    case = spec(table="tracks", x="playlist_genre", y="track_popularity", agg="none")
    valid, errors = check_specs({"charts": [case]}, SONGS)
    assert valid == [] and "sum, mean or count" in errors[0]


def test_a_requested_kind_must_be_among_the_charts():
    valid, errors = check_specs({"charts": [spec()]}, TABLES, required_kinds=("treemap",))
    assert valid and any("asked for a treemap" in error for error in errors)


def test_a_requested_kind_that_is_there_passes():
    tree = spec(chart="treemap", x="cntry_cd", group="plan_tier", sort="", top_n=0)
    assert check_specs({"charts": [tree]}, TABLES, required_kinds=("treemap",))[1] == []


# sha256 of the prompts lora-v2 was trained on (and the explorer's), taken at dacbe60.
TRAINED = {
    "ANALYST_SYSTEM_PROMPT": "467c296ad922e5c1223427489111d41e272fafd29fb0430cc5d2ddb4ab305f96",
    "PLANNER_SYSTEM_PROMPT": "b0e3819ba2824d672c27feb80885b71055de2feea01236e2a92ce6c73cc980b3",
    "EXPLORER_SYSTEM_PROMPT": "f1c8f808f0c16544e8372d2dd1a7527dd51f56cf5ca7d421f3beb185bf535552",
    "SPEC_RULES": "bcb5e7882a0b6e0de19eafd2f20756fefa5c3ba81970fbba6309e8c29b941c9f",
}


def test_the_trained_prompts_are_byte_identical():
    # New context goes in appended user-message sections, never into these.
    texts = {"ANALYST_SYSTEM_PROMPT": ANALYST_SYSTEM_PROMPT, "PLANNER_SYSTEM_PROMPT": PLANNER_SYSTEM_PROMPT,
             "EXPLORER_SYSTEM_PROMPT": EXPLORER_SYSTEM_PROMPT, "SPEC_RULES": SPEC_RULES}
    assert {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in texts.items()} == TRAINED


def test_notes_come_last_and_empty_ones_are_left_out():
    text = with_context("T", facts="- f", links="L", notes=("", "N"))
    assert text == "T\n\nL\n\nFacts checked on the full data:\n- f\n\nN"
