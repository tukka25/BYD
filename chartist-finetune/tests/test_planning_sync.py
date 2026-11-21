import json
from pathlib import Path

import pandas as pd

import contract


def test_profiles_and_checks_load_from_the_backend():
    frame = pd.read_csv("data/fixtures/s0016.csv")
    profile = contract.profile_table("str_watch_sess", frame)
    assert profile.kinds()["sess_dt"] == "date"
    tables = contract.columns_by_table([profile])
    spec = {"title": "Sessions by country", "question": "q", "chart": "bar", "table": "str_watch_sess",
            "x": "cntry_cd", "y": "sess_cnt", "group": "", "agg": "sum",
            "grain": "", "sort": "", "top_n": 0}
    valid, errors = contract.check_specs({"charts": [spec]}, tables)
    assert errors == [] and contract.render_spec(valid[0]).startswith("q\n\nChart plan:")


def test_every_time_column_in_the_fixtures_is_found_from_values():
    """The rule-based architect missed the date in 57 of these 180 tables."""
    missed = []
    for line in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines():
        schema = json.loads(line)
        kinds = contract.profile_table(schema["table_name"], pd.read_csv(schema["fixture_csv"])).kinds()
        for column in schema["columns"]:
            if column.get("role") == "time" and kinds.get(column["name"]) not in ("date", "year"):
                missed.append((schema["schema_id"], column["name"], kinds.get(column["name"])))
    assert not missed, missed[:10]


def test_prompts_are_the_backend_strings():
    assert "Return JSON" in contract.ANALYST_SYSTEM_PROMPT
    assert contract.SPEC_RULES in contract.PLANNER_SYSTEM_PROMPT
    assert set(contract.KIND_TRACES) == set(contract.CHART_KINDS)
