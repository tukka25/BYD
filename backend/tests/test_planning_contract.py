import json

from app.services.agents.planning_contract import (
    CHART_KINDS,
    DIRECTIONS_SCHEMA,
    KIND_TRACES,
    SPECS_SCHEMA,
    check_directions,
    check_specs,
    extract_json,
    render_directions,
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
