"""Foreign keys between a connection's tables: found, joined, offered to the planner."""
import pandas as pd
import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine

from app.services import db_sources
from app.services.db_sources import Link, links_on

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
