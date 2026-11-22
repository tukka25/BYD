"""A planned chart is drawn by the model, and only by the model.

There is no stand-in chart: when the model's code fails, the error goes back to
the model to fix its own code, and a chart it still cannot fix is reported as
failed. A hardcoded backup once drew 32,833 bars of the wrong column under a
planned title and froze the report it sat in.
"""
import pandas as pd

from app.services.agents.chartist import ChartistAgent
from app.services.agents.spec_runner import run_spec

SPEC = {"title": "Churn by country", "question": "Where is churn highest?", "chart": "bar",
        "table": "saas", "x": "cntry_cd", "y": "churn_cnt", "group": "", "agg": "sum",
        "grain": "", "sort": "desc", "top_n": 0}


class Scripted:
    """A stand-in model: replies in order and keeps every request it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def invoke(self, variables):
        self.requests.append(dict(variables))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _csv(tmp_path):
    path = tmp_path / "saas.csv"
    pd.DataFrame({"cntry_cd": ["DE", "US", "DE"], "churn_cnt": [3, 5, 4]}).to_csv(path, index=False)
    return {"type": "file", "name": "saas.csv", "path": str(path)}


GOOD = (
    "import plotly.express as px\n"
    "d = df.groupby('cntry_cd', as_index=False)['churn_cnt'].sum()\n"
    "fig = px.bar(d, x='cntry_cd', y='churn_cnt')\n"
    "print(fig.to_json())\n"
)
BROKEN = "import plotly.express as px\nfig = px.bar(df, x='nope', y='churn_cnt')\nprint(fig.to_json())\n"
WRITES_A_FILE = GOOD.replace("print(fig.to_json())", "d.to_csv('out.csv')\nprint(fig.to_json())")


def _run(tmp_path, *replies):
    model = Scripted(*replies)
    chartist = ChartistAgent(llm=None, generator=model, chart_type_hint_style="off")
    return run_spec(SPEC, _csv(tmp_path), chartist, str(tmp_path)), model


def test_a_plan_becomes_a_figure(tmp_path):
    result, model = _run(tmp_path, GOOD)
    assert result["error"] == "" and result["execution_result"]["figure"]["data"][0]["type"] == "bar"
    assert len(model.requests) == 1


def test_code_that_fails_goes_back_to_the_model_with_the_error(tmp_path):
    result, model = _run(tmp_path, BROKEN, GOOD)
    assert result["error"] == "" and result["execution_result"]["figure"]
    assert result["code"].strip() == GOOD.strip()
    fix = model.requests[1]
    assert fix["previous_code"].strip() == BROKEN.strip()
    assert "nope" in fix["problem"]  # the real error, passed on to the model


def test_code_that_breaks_the_rules_goes_back_to_the_model(tmp_path):
    result, model = _run(tmp_path, WRITES_A_FILE, GOOD)
    assert result["execution_result"]["figure"] and len(model.requests) == 2
    assert "file" in model.requests[1]["problem"]


def test_a_chart_the_model_cannot_fix_is_reported_not_replaced(tmp_path):
    result, model = _run(tmp_path, BROKEN, BROKEN, BROKEN)
    assert len(model.requests) == 3  # the first answer and two fixes, then it stops
    assert result["error"] and not result["execution_result"].get("figure")
    assert result["code"].strip() == BROKEN.strip()


def test_a_model_that_cannot_be_reached_is_an_error(tmp_path):
    result, model = _run(tmp_path, ConnectionError("server down"))
    assert "server down" in result["error"] and not result["execution_result"].get("figure")
