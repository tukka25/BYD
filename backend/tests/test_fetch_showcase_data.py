import sys
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_showcase_data import airbnb_urls, entry, excel_from_csv  # noqa: E402

CC_BY = ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/")


def test_airbnb_urls_point_at_one_snapshot():
    urls = airbnb_urls("2025-09-21")
    assert urls["listings.csv"] == (
        "https://data.insideairbnb.com/united-kingdom/scotland/edinburgh/2025-09-21/visualisations/listings.csv"
    )
    assert urls["reviews.csv"].endswith("/2025-09-21/visualisations/reviews.csv")


def test_a_snapshot_must_be_a_date():
    with pytest.raises(ValueError, match="2025-09-21"):
        airbnb_urls("latest")


def test_the_excel_copy_keeps_every_value(tmp_path):
    source = tmp_path / "listings.csv"
    pd.DataFrame({
        "id": [1234567890123456789, 42],
        "room_type": ["Entire home/apt", "Private room"],
        "price": [120.0, None],
    }).to_csv(source, index=False)
    rows, as_text = excel_from_csv(source, tmp_path / "listings.xlsx")
    back = pd.read_excel(tmp_path / "listings.xlsx")
    assert rows == 2
    # Excel stores numbers as doubles, exact only up to 2**53, so a 19-digit id
    # is stored as a text cell, and pandas reads every digit back.
    assert as_text == ["id"]
    sheet = load_workbook(tmp_path / "listings.xlsx").active
    assert [sheet["A2"].value, sheet["A3"].value] == ["1234567890123456789", "42"]
    assert back["id"].astype(str).tolist() == ["1234567890123456789", "42"]
    assert back["room_type"].tolist() == ["Entire home/apt", "Private room"]
    assert back["price"].iloc[0] == 120.0 and pd.isna(back["price"].iloc[1])


def test_a_price_stored_as_text_stops_the_conversion(tmp_path):
    source = tmp_path / "listings.csv"
    pd.DataFrame({"price": ["$120.00", "$95.00"]}).to_csv(source, index=False)
    with pytest.raises(ValueError, match="price is not numeric"):
        excel_from_csv(source, tmp_path / "listings.xlsx")


def test_a_manifest_entry_records_where_a_file_came_from(tmp_path):
    path = tmp_path / "reviews.csv"
    path.write_text("listing_id,date\n1,2024-01-01\n", encoding="utf-8")
    item = entry(path, "https://example.org/reviews.csv", CC_BY, 1, "As published.")
    assert item["file"] == "reviews.csv" and item["rows"] == 1 and item["bytes"] == path.stat().st_size
    assert item["licence"] == "CC BY 4.0" and item["url"] == "https://example.org/reviews.csv"
    assert len(item["sha256"]) == 64 and item["fetched_at"].endswith("Z")
