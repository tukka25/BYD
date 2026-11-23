"""Foreign keys between a connection's tables: found, joined, offered to the planner."""
import pandas as pd
import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine

from app.services import db_sources
from app.services.db_sources import Link, links_on, load_joined_on

ORDERS_CUSTOMERS = Link("orders", ("customer_id",), "customers", ("id",))


def shop_engine():
    """customers <- orders -> products, plus one order whose customer does not exist."""
    engine = create_engine("sqlite://")
    meta = MetaData()
    customers = Table("customers", meta, Column("id", Integer, primary_key=True), Column("region", String))
    products = Table("products", meta, Column("id", Integer, primary_key=True), Column("category", String))
    orders = Table("orders", meta, Column("id", Integer, primary_key=True),
                   Column("customer_id", Integer, ForeignKey("customers.id")),
                   Column("product_id", Integer, ForeignKey("products.id")),
                   Column("revenue", Integer))
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(customers.insert(), [{"id": 1, "region": "North"}, {"id": 2, "region": "South"}])
        conn.execute(products.insert(), [{"id": 1, "category": "Books"}])
        conn.execute(orders.insert(), [{"id": i, "customer_id": 1 + i % 2, "product_id": 1, "revenue": 10 * i}
                                       for i in range(1, 6)])
        conn.execute(orders.insert(), [{"id": 6, "customer_id": 99, "product_id": 1, "revenue": 5}])
    return engine


def test_declared_foreign_keys_are_found():
    with shop_engine().connect() as conn:
        links = links_on(conn, ["customers", "orders", "products"])
    assert sorted(links, key=lambda l: l.parent) == [
        ORDERS_CUSTOMERS, Link("orders", ("product_id",), "products", ("id",))]


def test_a_key_to_a_table_outside_the_list_is_left_out():
    with shop_engine().connect() as conn:
        links = links_on(conn, ["orders", "customers"])
    assert links == [ORDERS_CUSTOMERS]


def test_a_link_survives_a_round_trip_through_a_dict():
    assert Link.from_dict(ORDERS_CUSTOMERS.to_dict()) == ORDERS_CUSTOMERS
    assert ORDERS_CUSTOMERS.label == "orders+customers"


def test_a_joined_table_has_one_row_per_child_row_and_named_parent_columns():
    with shop_engine().connect() as conn:
        frame = load_joined_on(conn, ORDERS_CUSTOMERS)
    assert len(frame) == 6  # every order, the one without a customer included
    assert list(frame.columns) == ["id", "customer_id", "product_id", "revenue", "customers.id", "customers.region"]
    assert frame.loc[frame["customer_id"] == 99, "customers.region"].isna().all()


def test_a_joined_table_over_the_row_limit_is_refused(monkeypatch):
    monkeypatch.setattr(db_sources, "MAX_ROWS", 3)
    with shop_engine().connect() as conn, pytest.raises(ValueError, match="row limit"):
        load_joined_on(conn, ORDERS_CUSTOMERS)


def test_a_schema_read_takes_only_a_few_rows():
    with shop_engine().connect() as conn:
        assert len(load_joined_on(conn, ORDERS_CUSTOMERS, limit=2)) == 2


def test_a_connection_offers_each_joined_table(monkeypatch):
    monkeypatch.setattr(db_sources, "tables_with_columns", lambda source, limit: [
        {"table": "customers", "columns": ["id", "region"]},
        {"table": "orders", "columns": ["id", "customer_id", "revenue"]}])
    monkeypatch.setattr(db_sources, "foreign_keys", lambda source, tables: [ORDERS_CUSTOMERS])
    source = type("Source", (), {"id": "s1", "display_name": "Shop"})()
    joined = [c for c in db_sources.candidates_for(source) if c.get("join")]
    assert [c["table"] for c in joined] == ["orders+customers"]
    assert joined[0]["columns"] == ["id", "customer_id", "revenue", "customers.id", "customers.region"]
    assert joined[0]["join"] == ORDERS_CUSTOMERS.to_dict() and joined[0]["id"] == "s1:orders+customers"


def test_load_frame_reads_a_joined_table(monkeypatch):
    from app.services.agents.architect import load_frame

    seen = {}

    def fake(source_id, link, limit=None):
        seen.update(source_id=source_id, link=link)
        return pd.DataFrame({"revenue": [1], "customers.region": ["North"]})

    monkeypatch.setattr(db_sources, "load_joined_by_id", fake)
    frame = load_frame({"type": "db", "source_id": "s1", "table": "orders+customers",
                        "join": ORDERS_CUSTOMERS.to_dict()}, "")
    assert list(frame.columns) == ["revenue", "customers.region"]
    assert seen == {"source_id": "s1", "link": ORDERS_CUSTOMERS}


def test_a_chart_runs_on_a_joined_table(monkeypatch):
    from app.services.agents.workflow import run_chart_code
    from app.utils.executor import SafeExecutor

    joined = pd.DataFrame({"revenue": [10, 20, 30], "customers.region": ["North", "South", "North"]})
    monkeypatch.setattr(db_sources, "load_joined_by_id", lambda source_id, link, limit=None: joined)
    code = ("import plotly.express as px\n"
            "d = df.groupby('customers.region', as_index=False)['revenue'].sum()\n"
            "fig = px.bar(d, x='customers.region', y='revenue')\n"
            "print(fig.to_json())\n")
    out = run_chart_code({"source_id": "s1", "table": "orders+customers", "join": ORDERS_CUSTOMERS.to_dict()},
                         code, SafeExecutor())
    assert out["execution_result"]["figure"]["data"][0]["type"] == "bar"
