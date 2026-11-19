#!/usr/bin/env python3
"""Synthesize business table schemas with Haiku, then materialize a CSV per schema."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd

import client

DOMAINS = [
    "retail store sales", "e-commerce orders", "SaaS subscription revenue",
    "SaaS churn and retention", "HR headcount and attrition", "recruiting pipeline",
    "marketing campaign performance", "web traffic and conversion",
    "customer support tickets", "call centre staffing", "warehouse inventory",
    "freight and logistics shipments", "delivery fleet telemetry",
    "manufacturing line output", "quality control defects", "energy consumption by site",
    "utility billing", "hospital clinic throughput", "patient appointment scheduling",
    "pharmacy dispensing", "school enrolment and attendance", "university course grades",
    "municipal service requests", "public transport ridership", "traffic incidents",
    "real estate listings and sales", "property rental yields", "construction project costs",
    "bank transaction volumes", "loan portfolio performance", "insurance claims",
    "credit card fraud flags", "restaurant orders and covers", "hotel occupancy and ADR",
    "airline on-time performance", "cargo port throughput", "agricultural yield by plot",
    "water usage by district", "waste collection routes", "telecom network usage",
    "mobile app engagement", "game session analytics", "streaming content watch time",
    "advertising spend and ROAS", "supply chain supplier scorecards",
]

NAMING_STYLES = [
    "snake_case, spelled out (order_date, total_revenue)",
    "snake_case, abbreviated (ord_dt, tot_rev)",
    "camelCase (orderDate, totalRevenue)",
    "Title Case With Spaces (Order Date, Total Revenue)",
    "UPPER_SNAKE legacy warehouse style (ORDER_DT, TOT_REV_AMT)",
    "prefixed by entity (sales_order_date, sales_total_amount)",
]

SYSTEM = """You design realistic database table schemas for business dashboards.

Return one table schema. Requirements:
- 5 to 10 columns.
- Exactly one date/time column, 2 to 4 categorical dimensions, 2 to 5 numeric measures.
- Column names must follow the requested naming style EXACTLY and consistently.
- Names must be plausible for the domain, never generic placeholders like "col1", "value", "x", "data".
- For each category column give 3 to 8 realistic category values.
- For each numeric column give a realistic min and max for the domain.
- dtype is one of: date, int, float, category, bool
- role is one of: time, dimension, measure"""

SCHEMA = {
    "type": "object",
    "properties": {
        "table_name": {"type": "string"},
        "columns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "dtype": {"type": "string", "enum": ["date", "int", "float", "category", "bool"]},
                    "role": {"type": "string", "enum": ["time", "dimension", "measure"]},
                    "categories": {"type": "array", "items": {"type": "string"}},
                    "min": {"type": "number"},
                    "max": {"type": "number"},
                },
                "required": ["name", "dtype", "role"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["table_name", "columns"],
    "additionalProperties": False,
}


def materialize(schema: dict, out_path: Path, n_rows: int, seed: int) -> None:
    """Build a real CSV from the declared schema. Deterministic given the seed."""
    rng = np.random.default_rng(seed)
    data: dict[str, object] = {}
    for col in schema["columns"]:
        name, dtype = col["name"], col["dtype"]
        if dtype == "date":
            start = pd.Timestamp("2024-01-01")
            data[name] = pd.to_datetime(
                start + pd.to_timedelta(rng.integers(0, 540, n_rows), unit="D")
            ).strftime("%Y-%m-%d")
        elif dtype == "category":
            cats = col.get("categories") or [f"{name}_{i}" for i in range(4)]
            data[name] = rng.choice(cats, n_rows)
        elif dtype == "bool":
            data[name] = rng.choice([True, False], n_rows)
        else:
            low = float(col.get("min", 0))
            high = float(col.get("max", max(low + 1, 1000)))
            if high <= low:
                high = low + 1000
            values = rng.uniform(low, high, n_rows)
            data[name] = values.round(0).astype(int) if dtype == "int" else values.round(2)
    pd.DataFrame(data).to_csv(out_path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--total", type=int, default=180)
    parser.add_argument("--test-schemas", type=int, default=60)
    parser.add_argument("--rows-per-fixture", type=int, default=240)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    per_domain = args.total // len(DOMAINS)
    if per_domain * len(DOMAINS) != args.total or args.test_schemas % per_domain:
        raise SystemExit("--total must be a multiple of the domain count and --test-schemas a multiple of schemas per domain")
    domains = list(DOMAINS)
    rng.shuffle(domains)
    n_test_domains = args.test_schemas // per_domain
    test_domains = set(domains[:n_test_domains])
    plan = []
    for domain in domains:
        # distinct naming styles within a domain, so no (domain, style) pair repeats
        for style in rng.sample(NAMING_STYLES, per_domain):
            plan.append(
                {
                    "domain": domain,
                    "naming_style": style,
                    "split": "test" if domain in test_domains else "train",
                }
            )
    rng.shuffle(plan)
    for i, item in enumerate(plan):
        item["schema_id"] = f"s{i:04d}"

    requests = [
        client.json_request(
            custom_id=item["schema_id"],
            model=client.HAIKU,
            system=SYSTEM,
            user=(
                f"Domain: {item['domain']}\n"
                f"Naming style: {item['naming_style']}\n"
                "Design the table schema."
            ),
            schema=SCHEMA,
            max_tokens=2048,
            effort="low",
        )
        for item in plan
    ]

    outcome = client.run_batch(requests, label="schemas")
    client.record_spend(
        "schemas", client.HAIKU, outcome.usage, {"requests": len(requests)}
    )

    fixture_dir = Path("data/fixtures")
    fixture_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, item in enumerate(plan):
        payload = outcome.payloads.get(item["schema_id"])
        if not payload or not payload.get("columns"):
            continue
        names = [c["name"] for c in payload["columns"]]
        if len(set(names)) != len(names):
            continue
        fixture = fixture_dir / f"{item['schema_id']}.csv"
        try:
            materialize(payload, fixture, args.rows_per_fixture, args.seed + index)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {item['schema_id']}: {exc}")
            continue
        frame = pd.read_csv(fixture)
        rows.append(
            {
                **item,
                "table_name": payload["table_name"],
                "columns": payload["columns"],
                "fixture_csv": str(fixture),
                "pandas_columns": list(frame.columns),
                "pandas_dtypes": {c: str(d) for c, d in frame.dtypes.items()},
                "sample_rows": frame.head(2).to_dict(orient="records"),
            }
        )

    out = Path("data/schemas.jsonl")
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    by_split = {"test": 0, "train": 0}
    for row in rows:
        by_split[row["split"]] += 1
    print(json.dumps({"schemas_kept": len(rows), "by_split": by_split,
                      "refusals": outcome.refusals, "unparsed": outcome.unparsed}, indent=2))
    leakage_guard(rows)


def leakage_guard(rows: list[dict], threshold: float = 0.7) -> None:
    """Fail loudly if the test split can leak into train."""
    test = [r for r in rows if r["split"] == "test"]
    train = [r for r in rows if r["split"] == "train"]

    shared = {r["domain"] for r in test} & {r["domain"] for r in train}
    print(f"guard 1: test/train domain overlap = {sorted(shared)}")
    assert not shared, f"domains appear in both splits: {sorted(shared)}"

    pairs = [(r["domain"], r["naming_style"]) for r in rows]
    dupes = {p for p in pairs if pairs.count(p) > 1}
    print(f"guard 2: repeated (domain, style) pairs = {len(dupes)}")
    assert not dupes, f"repeated (domain, style) pairs: {sorted(dupes)[:5]}"

    worst, worst_pair = 0.0, None
    for a in test:
        sa = set(a["pandas_columns"])
        for b in train:
            sb = set(b["pandas_columns"])
            score = len(sa & sb) / len(sa | sb)
            if score > worst:
                worst, worst_pair = score, (a["schema_id"], b["schema_id"])
    print(f"guard 3: worst cross-split column Jaccard = {worst:.3f} {worst_pair} (threshold {threshold})")
    assert worst < threshold, f"cross-split near-duplicate schemas {worst_pair}: Jaccard {worst:.3f}"

if __name__ == "__main__":
    main()
