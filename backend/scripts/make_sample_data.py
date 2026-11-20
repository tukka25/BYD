#!/usr/bin/env python3
"""Generate sample CSVs so the dashboard can be tested without real data.

Written rather than downloaded on purpose: it is reproducible (seeded), needs no
network, and the schemas are chosen to exercise different chart types — a time
series, a categorical breakdown, a numeric relationship, and a two-key grid.

Column naming follows the same business style as the chartist's training data
(camelCase, abbreviations, mixed dtypes), so the schema block the model sees here
looks like the ones it was fine-tuned on.

    python3 scripts/make_sample_data.py --out uploads
"""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SEED = 42


def saas_revenue() -> pd.DataFrame:
    """Monthly SaaS metrics. Suits line, area, bar, indicator."""
    rng = random.Random(SEED)
    rows = []
    start = date(2024, 1, 1)
    for tier in ("Free", "Pro", "Enterprise"):
        base = {"Free": 1200.0, "Pro": 18000.0, "Enterprise": 64000.0}[tier]
        for month in range(24):
            day = (start + timedelta(days=31 * month)).replace(day=1)
            growth = 1.0 + 0.021 * month + rng.uniform(-0.04, 0.05)
            mrr = round(base * growth, 2)
            seats = int(mrr / rng.uniform(28, 46))
            rows.append(
                {
                    "snapshotMonth": day.isoformat(),
                    "planTier": tier,
                    "region": rng.choice(["EMEA", "APAC", "NA", "LATAM"]),
                    "mrrUsd": mrr,
                    "activeSeats": seats,
                    "churnedSeats": int(seats * rng.uniform(0.004, 0.038)),
                    "nrrPct": round(rng.uniform(94.0, 121.0), 1),
                }
            )
    return pd.DataFrame(rows)


def ecommerce_orders() -> pd.DataFrame:
    """Order lines. Suits bar, pie, histogram, box."""
    rng = random.Random(SEED + 1)
    categories = {
        "Electronics": (80, 1400),
        "Home & Kitchen": (15, 260),
        "Apparel": (12, 180),
        "Sports": (20, 420),
        "Books": (6, 48),
    }
    rows = []
    start = date(2025, 1, 1)
    for i in range(1800):
        category = rng.choice(list(categories))
        low, high = categories[category]
        price = round(rng.uniform(low, high), 2)
        qty = rng.choice([1, 1, 1, 2, 2, 3, 5])
        rows.append(
            {
                "orderId": f"SO-{100000 + i}",
                "orderDate": (start + timedelta(days=rng.randint(0, 364))).isoformat(),
                "category": category,
                "channel": rng.choice(["web", "web", "mobile", "marketplace", "store"]),
                "countryCode": rng.choice(["AE", "SA", "GB", "DE", "US", "IN"]),
                "unitPriceUsd": price,
                "quantity": qty,
                "lineTotalUsd": round(price * qty, 2),
                "discountPct": rng.choice([0, 0, 0, 5, 10, 15, 25]),
                "isReturned": rng.random() < 0.046,
            }
        )
    return pd.DataFrame(rows)


def property_sales() -> pd.DataFrame:
    """Property transactions. Suits scatter, box, heatmap."""
    rng = random.Random(SEED + 2)
    rows = []
    start = date(2023, 6, 1)
    for i in range(900):
        sqft = rng.randint(480, 4200)
        beds = max(1, min(6, round(sqft / 620 + rng.uniform(-0.7, 0.7))))
        zone = rng.choice(["Marina", "Downtown", "Hills", "Riverside", "Old Town"])
        premium = {"Marina": 1.34, "Downtown": 1.22, "Hills": 1.11, "Riverside": 0.95, "Old Town": 0.84}[zone]
        rows.append(
            {
                "saleDate": (start + timedelta(days=rng.randint(0, 760))).isoformat(),
                "propertyType": rng.choice(["Apartment", "Apartment", "Villa", "Townhouse"]),
                "neighborhoodZone": zone,
                "listingStatus": rng.choice(["Sold", "Sold", "Sold", "Withdrawn"]),
                "bedroomCount": beds,
                "squareFootage": sqft,
                "salePrice": round(sqft * rng.uniform(180, 340) * premium, 2),
                "daysOnMarket": max(1, int(rng.gauss(58, 34))),
            }
        )
    return pd.DataFrame(rows)


def web_traffic() -> pd.DataFrame:
    """Sessions by weekday and hour — a natural two-key grid for a heatmap."""
    rng = random.Random(SEED + 3)
    rows = []
    for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        weekend = day in ("Sat", "Sun")
        for hour in range(24):
            # Two humps on weekdays, one flat afternoon rise at weekends.
            peak = 1.0 if weekend else (2.3 if hour in range(8, 11) or hour in range(18, 22) else 1.0)
            base = 240 if weekend else 420
            rows.append(
                {
                    "weekday": day,
                    "hourOfDay": hour,
                    "sessions": int(base * peak * rng.uniform(0.72, 1.3)),
                    "bounceRatePct": round(rng.uniform(28.0, 71.0), 1),
                    "avgSessionSeconds": int(rng.gauss(188, 62)),
                    "deviceClass": rng.choice(["desktop", "mobile", "mobile", "tablet"]),
                }
            )
    return pd.DataFrame(rows)


DATASETS = {
    "saas_revenue.csv": saas_revenue,
    "ecommerce_orders.csv": ecommerce_orders,
    "property_sales.csv": property_sales,
    "web_traffic.csv": web_traffic,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="uploads")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, build in DATASETS.items():
        df = build()
        df.to_csv(out / name, index=False)
        print(f"  {name:24s} {len(df):5d} rows x {len(df.columns)} cols  {list(df.columns)}")
    print(f"\nwrote {len(DATASETS)} files to {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
