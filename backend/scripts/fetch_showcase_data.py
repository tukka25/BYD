#!/usr/bin/env python3
"""Download the landing page's file sources and record where each came from.

Run once from the repository root, after the owner has agreed to the downloads
(each file's name, source and size). The files go to backend/uploads/showcase/,
which git ignores, so no third-party data is committed:

    listings.xlsx       Inside Airbnb's Edinburgh listings summary, saved as Excel
    reviews.csv         Inside Airbnb's Edinburgh reviews summary, as published
    netflix_titles.csv  the Netflix catalogue, as TidyTuesday mirrors it
    manifest.json       each file's URL, licence, rows, bytes, sha256 and fetch time

The listings are saved as Excel so one dashboard is built from an Excel file and
a CSV, as a user's might be. No value changes on the way.

    backend/.venv/bin/python backend/scripts/fetch_showcase_data.py --airbnb-snapshot 2025-09-21
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

AIRBNB_FILE = "https://data.insideairbnb.com/united-kingdom/scotland/edinburgh/{snapshot}/visualisations/{name}"
AIRBNB_LICENCE = ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/")
NETFLIX_URL = (
    "https://raw.githubusercontent.com/rfordatascience/tidytuesday/main/data/2021/2021-04-20/netflix_titles.csv"
)
NETFLIX_LICENCE = ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/")
USER_AGENT = "promptdash-showcase/1.0"
SNAPSHOT = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def airbnb_urls(snapshot: str) -> dict[str, str]:
    """The two summary files of one Edinburgh snapshot, by file name."""
    if not SNAPSHOT.match(snapshot):
        raise ValueError(
            f"the snapshot is a date such as 2025-09-21, from insideairbnb.com/get-the-data; got {snapshot!r}"
        )
    return {name: AIRBNB_FILE.format(snapshot=snapshot, name=name) for name in ("listings.csv", "reviews.csv")}


def download(url: str, path: Path) -> None:
    """Fetch through a .part file, so an interrupted download leaves no file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as out:
        shutil.copyfileobj(response, out)
    partial.replace(path)


def excel_from_csv(csv_path: Path, xlsx_path: Path) -> tuple[int, list[str]]:
    """Save the listings as Excel, keeping every value. Returns the row count and
    the columns written as text.

    Excel stores numbers as doubles, which hold integers exactly only up to
    2**53: a 19-digit listing id would come back with other digits. Such a column
    is written as text, digit for digit, and the manifest says so.

    Stops if `price` is not numeric: cleaning it would be editing the data, and
    the page would have to say so. That is the owner's decision."""
    frame = pd.read_csv(csv_path, keep_default_na=False, na_values=[""])
    if "price" in frame.columns and not pd.api.types.is_numeric_dtype(frame["price"]):
        sample = frame["price"].dropna().astype(str).head(3).tolist()
        raise ValueError(f"price is not numeric in {csv_path.name} (for example {sample}); cleaning it would edit the data")
    as_text = [
        name for name in frame.columns
        if pd.api.types.is_integer_dtype(frame[name]) and frame[name].abs().max() > 2**53
    ]
    for name in as_text:
        frame[name] = frame[name].astype(str)
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_excel(xlsx_path, index=False)
    return len(frame), as_text


def entry(path: Path, url: str, licence: tuple[str, str], rows: int, note: str) -> dict:
    """One manifest line: where the file came from, under what licence, and what it holds."""
    return {
        "file": path.name,
        "url": url,
        "licence": licence[0],
        "licence_url": licence[1],
        "rows": rows,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": note,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the landing page's file sources.")
    parser.add_argument("--airbnb-snapshot", required=True, help="the Edinburgh snapshot date on insideairbnb.com")
    parser.add_argument("--out", default="backend/uploads/showcase")
    args = parser.parse_args()
    out = Path(args.out)
    raw = out / "raw"

    airbnb = airbnb_urls(args.airbnb_snapshot)
    for name, url in {**airbnb, "netflix_titles.csv": NETFLIX_URL}.items():
        print(f"downloading {name} from {url}", file=sys.stderr)
        download(url, raw / name)

    snapshot = f"Inside Airbnb, Edinburgh, snapshot {args.airbnb_snapshot}."
    listings_rows, as_text = excel_from_csv(raw / "listings.csv", out / "listings.xlsx")
    kept = f"; {', '.join(as_text)} stored as text to keep every digit" if as_text else ""
    shutil.copyfile(raw / "reviews.csv", out / "reviews.csv")
    shutil.copyfile(raw / "netflix_titles.csv", out / "netflix_titles.csv")
    manifest = [
        entry(out / "listings.xlsx", airbnb["listings.csv"], AIRBNB_LICENCE, listings_rows,
              f"{snapshot} Saved as Excel from the published CSV{kept}."),
        entry(out / "reviews.csv", airbnb["reviews.csv"], AIRBNB_LICENCE, len(pd.read_csv(out / "reviews.csv")),
              f"{snapshot} As published."),
        entry(out / "netflix_titles.csv", NETFLIX_URL, NETFLIX_LICENCE, len(pd.read_csv(out / "netflix_titles.csv")),
              "Netflix Movies and TV Shows by Shivam Bansal on Kaggle, as mirrored by TidyTuesday (2021-04-20)."),
    ]
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for item in manifest:
        print(f"{item['file']}: {item['rows']:,} rows, {item['bytes']:,} bytes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
