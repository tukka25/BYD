"""A chart in the kind picked with "/": planned as that kind, drawn by the model."""
import json

import pandas as pd
import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.blocks import DashboardBriefRequest, GenerateBlockRequest
from app.services import db_sources
from app.services.agents.chartist import ChartistAgent
from app.services.agents.kind_request import run_kind_request

TREEMAP_CODE = ("import plotly.express as px\n"
                "fig = px.treemap(df, path=['cntry_cd'], values='churn_cnt')\n"
                "print(fig.to_json())\n")
LINK = {"child": "orders", "child_columns": ["customer_id"], "parent": "customers", "parent_columns": ["id"]}


class Recorder:
    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def invoke(self, messages):
        self.seen.append(list(messages))
        return type("Reply", (), {"content": self.replies.pop(0)})()


class Fixed:
    def __init__(self, code):
        self.code = code

    def invoke(self, variables):
        return self.code


def _source(tmp_path):
    path = tmp_path / "saas.csv"
    pd.DataFrame({"cntry_cd": ["DE", "US"] * 5, "churn_cnt": range(10)}).to_csv(path, index=False)
    return {"id": "saas.csv", "type": "file", "name": "saas.csv", "path": str(path)}


def plan(chart):
    return json.dumps({"charts": [{"title": "Churn by country", "question": "q", "chart": chart, "table": "saas.csv",
                                   "x": "cntry_cd", "y": "churn_cnt", "group": "", "agg": "sum", "grain": "",
                                   "sort": "", "top_n": 0}]})


def test_the_picked_kind_is_planned_and_drawn_by_the_model(tmp_path):
    source = _source(tmp_path)
    planner = Recorder(plan("bar"), plan("treemap"))
    chartist = ChartistAgent(llm=None, generator=Fixed(TREEMAP_CODE), chart_type_hint_style="off")
    result = run_kind_request("churn by country", "treemap", [source], "", planner, chartist, str(tmp_path),
                              detect=lambda state: {"source_decision": {"selected": source}})
    assert result["plan"] == {"visualization_type": "treemap", "chart_type_source": "user"}
    assert result["spec"]["chart"] == "treemap"
    assert result["execution_result"]["figure"]["data"][0]["type"] == "treemap"
    assert "asked for a treemap" in planner.seen[1][-1].content
    # Told up front too, in the dashboard's words, so a retry is the exception.
    assert planner.seen[0][-1].content.endswith("Include these chart kinds: Treemap.")


def test_a_kind_the_model_will_not_plan_is_an_error_not_a_different_chart(tmp_path):
    source = _source(tmp_path)
    result = run_kind_request("churn by country", "treemap", [source], "", Recorder(*[plan("bar")] * 3), None,
                              str(tmp_path), detect=lambda state: {"source_decision": {"selected": source}})
    assert "could not plan a treemap" in result["error"] and "execution_result" not in result


def test_a_joined_table_comes_with_its_join_line_as_on_a_dashboard(monkeypatch):
    joined = pd.DataFrame({"revenue": [10, 20], "customers.region": ["North", "South"]})
    monkeypatch.setattr(db_sources, "load_joined_by_id", lambda source_id, link, limit=None: joined)
    source = {"id": "s1:orders+customers", "type": "db", "source_id": "s1", "table": "orders+customers",
              "name": "orders+customers · Shop", "join": LINK}
    planner = Recorder("{}", "{}", "{}")  # unusable on purpose: only the first message matters, and nothing is drawn
    run_kind_request("revenue by region", "treemap", [source], "", planner, None, "",
                     detect=lambda state: {"source_decision": {"selected": source}})
    message = planner.seen[0][-1].content
    assert "Joined tables you can use" in message and "orders.customer_id = customers.id" in message


def test_unknown_kinds_are_refused_at_the_door():
    with pytest.raises(ValidationError):
        GenerateBlockRequest(prompt="x", chart_kind="sankey")
    assert GenerateBlockRequest(prompt="x", chart_kind="treemap").chart_kind == "treemap"
    assert DashboardBriefRequest(brief="", chart_kinds=["pie", "funnel"]).chart_kinds == ["pie", "funnel"]
    with pytest.raises(ValidationError):
        DashboardBriefRequest(brief="", chart_kinds=["pie", "bar", "line", "area", "box"])
