"""The planner is told what each joined table is, in a line each."""
import pandas as pd

from app.services import db_sources
from app.services.agents.dashboard_flow import build_dashboard
from app.services.agents.links import render_links
from app.services.agents.planning_contract import with_context

LINK = {"child": "orders", "child_columns": ["customer_id"], "parent": "customers", "parent_columns": ["id"]}


class Recorder:
    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def invoke(self, messages):
        self.seen.append(list(messages))
        return type("Reply", (), {"content": self.replies.pop(0)})()


def test_each_join_is_one_line_naming_its_key_and_how_columns_are_named():
    text = render_links([LINK])
    assert "orders+customers" in text and "orders.customer_id = customers.id" in text
    assert "customers.<column>" in text


def test_no_links_adds_nothing():
    assert render_links([]) == "" and with_context("Tables: t", links="") == "Tables: t"


def test_links_come_right_after_the_tables():
    message = with_context("Tables:\n...", facts="- a fact", links=render_links([LINK]))
    assert message.index("Tables:") < message.index("Joined tables") < message.index("Facts checked")


def test_the_analyst_is_told_about_a_joined_table(monkeypatch):
    joined = pd.DataFrame({"revenue": [10, 20], "customers.region": ["North", "South"]})
    monkeypatch.setattr(db_sources, "load_joined_by_id", lambda source_id, link, limit=None: joined)
    source = {"type": "db", "source_id": "s1", "table": "orders+customers",
              "name": "orders+customers · Shop", "join": LINK}
    analyst = Recorder("{}", "{}", "{}")  # unusable on purpose: only the first message matters
    list(build_dashboard("revenue by region", [source], "", analyst, Recorder(), None))
    assert "Joined tables you can use" in analyst.seen[0][-1].content
