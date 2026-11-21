import pandas as pd

from app.services.agents.profiler import (
    columns_by_table,
    profile_column,
    profile_table,
    render_profiles,
)


def _saas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "snap_dt": ["2024-01-09", "2025-01-03", "2024-06-30", "2024-03-01"] * 10,
            "cntry_cd": ["DE", "US", "BR", "AU"] * 10,
            "mrr_usd": [2224859.79, 1458369.58, 7799.0, 99.5] * 10,
            "yr": [2021, 2022, 2023, 2024] * 10,
            "row_no": list(range(1, 41)),
            "note": [f"free text number {i}" for i in range(40)],
        }
    )


def test_text_dates_are_found_from_values_not_names():
    column = profile_column("snap_dt", _saas()["snap_dt"])
    assert column.kind == "date"
    assert (column.low, column.high) == ("2024-01-09", "2025-01-03")


def test_codes_are_a_category_with_examples():
    column = profile_column("cntry_cd", _saas()["cntry_cd"])
    assert column.kind == "category"
    assert column.distinct == 4
    assert column.examples == ["AU", "BR", "DE", "US"]


def test_numbers_years_and_ids():
    frame = _saas()
    assert profile_column("mrr_usd", frame["mrr_usd"]).kind == "number"
    assert profile_column("yr", frame["yr"]).kind == "year"
    assert profile_column("row_no", frame["row_no"]).kind == "id"
    assert profile_column("note", frame["note"]).kind == "id"


def test_numbers_stored_as_text_are_not_dates():
    assert profile_column("code", pd.Series(["101", "202", "303"] * 5)).kind == "category"


def test_render_lists_every_column_with_its_kind():
    text = render_profiles([profile_table("saas_metrics", _saas())])
    assert text.startswith("table: saas_metrics (40 rows in sample)")
    assert "snap_dt" in text and "date" in text
    assert "4 values: AU, BR, DE, US" in text


def test_columns_by_table():
    tables = columns_by_table([profile_table("saas_metrics", _saas())])
    assert tables["saas_metrics"]["mrr_usd"] == "number"
    assert tables["saas_metrics"]["snap_dt"] == "date"
