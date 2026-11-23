"""A small shop database with declared foreign keys, for trying joined tables.

    docker exec -i promptdash-api python /app/scripts/make_relational_demo.py

Creates database `shop` on the app's Postgres if it is missing, then rebuilds
its four tables. Seeded, so every run makes the same rows. Touches nothing
outside `shop`. `visits` is wide on purpose (14 columns, a key to customers):
its joined table, visits+customers, has more columns than a one-chart
direction lists, so it shows whether the parent's columns still reach the planner.
"""
import sys

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, "/app")
from app.core.config import get_settings  # noqa: E402

admin = make_url(get_settings().DATABASE_URL)
with create_engine(admin, isolation_level="AUTOCOMMIT").connect() as conn:
    if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'shop'")).scalar():
        conn.execute(text("CREATE DATABASE shop"))

engine = create_engine(admin.set(database="shop"))
rng = np.random.default_rng(7)
customers = pd.DataFrame({
    "id": range(1, 201),
    "name": [f"Customer {i}" for i in range(1, 201)],
    "region": rng.choice(["North", "South", "East", "West"], 200),
    "segment": rng.choice(["Consumer", "SMB", "Enterprise"], 200, p=[0.6, 0.3, 0.1]),
})
products = pd.DataFrame({
    "id": range(1, 41),
    "name": [f"Product {i}" for i in range(1, 41)],
    "category": rng.choice(["Books", "Games", "Home", "Garden", "Tech"], 40),
    "unit_price": rng.uniform(5, 300, 40).round(2),
})
orders = pd.DataFrame({
    "id": range(1, 5001),
    "customer_id": rng.integers(1, 201, 5000),
    "product_id": rng.integers(1, 41, 5000),
    "order_date": pd.to_datetime("2024-01-01") + pd.to_timedelta(rng.integers(0, 730, 5000), unit="D"),
    "quantity": rng.integers(1, 6, 5000),
})
orders["revenue"] = (orders["quantity"] * products.set_index("id").loc[orders["product_id"], "unit_price"].to_numpy()).round(2)
wide = np.random.default_rng(11)  # its own seed, so the three tables above keep their rows
visits = pd.DataFrame({
    "id": range(1, 2001),
    "customer_id": wide.integers(1, 201, 2000),
    "visit_date": pd.to_datetime("2024-01-01") + pd.to_timedelta(wide.integers(0, 730, 2000), unit="D"),
    "channel": wide.choice(["web", "app", "email", "ads"], 2000),
    "device": wide.choice(["desktop", "mobile", "tablet"], 2000),
    "browser": wide.choice(["Chrome", "Safari", "Firefox", "Edge"], 2000),
    "country": wide.choice(["DE", "FR", "GB", "US", "ES"], 2000),
    "landing_page": wide.choice(["home", "search", "product", "cart", "blog"], 2000),
    "referrer": wide.choice(["google", "newsletter", "partner", "direct"], 2000),
    "pages": wide.integers(1, 21, 2000),
    "minutes": wide.gamma(2.0, 3.0, 2000).round(1),
    "bounced": wide.random(2000) < 0.3,
    "cart_value": wide.uniform(0, 400, 2000).round(2),
    "coupon_used": wide.random(2000) < 0.15,
})

with engine.begin() as conn:
    conn.execute(text("DROP TABLE IF EXISTS visits; DROP TABLE IF EXISTS orders; DROP TABLE IF EXISTS products; "
                      "DROP TABLE IF EXISTS customers"))
    conn.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                      "region TEXT NOT NULL, segment TEXT NOT NULL)"))
    conn.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                      "category TEXT NOT NULL, unit_price NUMERIC(10,2) NOT NULL)"))
    conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, "
                      "customer_id INTEGER NOT NULL REFERENCES customers(id), "
                      "product_id INTEGER NOT NULL REFERENCES products(id), "
                      "order_date DATE NOT NULL, quantity INTEGER NOT NULL, revenue NUMERIC(12,2) NOT NULL)"))
    conn.execute(text("CREATE TABLE visits (id INTEGER PRIMARY KEY, "
                      "customer_id INTEGER NOT NULL REFERENCES customers(id), visit_date DATE NOT NULL, "
                      "channel TEXT NOT NULL, device TEXT NOT NULL, browser TEXT NOT NULL, country TEXT NOT NULL, "
                      "landing_page TEXT NOT NULL, referrer TEXT NOT NULL, pages INTEGER NOT NULL, "
                      "minutes NUMERIC(6,1) NOT NULL, bounced BOOLEAN NOT NULL, cart_value NUMERIC(10,2) NOT NULL, "
                      "coupon_used BOOLEAN NOT NULL)"))
customers.to_sql("customers", engine, if_exists="append", index=False)
products.to_sql("products", engine, if_exists="append", index=False)
orders.to_sql("orders", engine, if_exists="append", index=False)
visits.to_sql("visits", engine, if_exists="append", index=False)
print(f"shop: {len(customers)} customers, {len(products)} products, {len(orders)} orders, "
      f"{len(visits)} visits ({len(visits.columns)} columns)")
