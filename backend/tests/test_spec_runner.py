import pandas as pd

from app.services.agents.chartist import ChartistAgent
from app.services.agents.spec_runner import fallback_kind, run_spec

SPEC = {"title": "Churn by country", "question": "Where is churn highest?", "chart": "bar",
        "table": "saas", "x": "cntry_cd", "y": "churn_cnt", "group": "", "agg": "sum",
        "grain": "", "sort": "desc", "top_n": 0}


class Fixed:
    def __init__(self, code):
        self.code = code

    def invoke(self, variables):
        return self.code


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


def test_a_plan_becomes_a_figure(tmp_path):
    chartist = ChartistAgent(llm=None, generator=Fixed(GOOD), chart_type_hint_style="off")
    result = run_spec(SPEC, _csv(tmp_path), chartist, str(tmp_path))
    assert result["error"] == "" and result["execution_result"]["figure"]["data"][0]["type"] == "bar"


def test_code_that_fails_at_runtime_falls_back(tmp_path):
    broken = "import plotly.express as px\nfig = px.bar(df, x='nope', y='churn_cnt')\nprint(fig.to_json())\n"
    chartist = ChartistAgent(llm=None, generator=Fixed(broken), chart_type_hint_style="off")
    result = run_spec(SPEC, _csv(tmp_path), chartist, str(tmp_path))
    assert result["execution_result"].get("figure") and "fallback" in result["code"]


def test_fallback_kinds():
    assert (fallback_kind("area"), fallback_kind("scatter"), fallback_kind("kpi")) == ("line", "scatter", "bar")
