from app.services.agents.chartist import ChartistAgent
from app.services.agents.chartist_contract import render_spec

SPEC = {
    "title": "Churn by country", "question": "Where is churn highest?", "chart": "bar",
    "table": "saas", "x": "cntry_cd", "y": "churn_cnt", "group": "", "agg": "sum",
    "grain": "", "sort": "desc", "top_n": 10,
}


def test_render_spec_reads_as_a_plan():
    assert render_spec(SPEC) == (
        "Where is churn highest?\n\n"
        "Chart plan:\n"
        "- chart: bar\n"
        "- x: cntry_cd\n"
        "- y: churn_cnt (sum)\n"
        "- order: descending, top 10\n"
        "- title: Churn by country"
    )


def test_render_spec_count_and_grain():
    text = render_spec({**SPEC, "chart": "line", "x": "snap_dt", "y": "", "agg": "count",
                        "grain": "month", "sort": "", "top_n": 0})
    assert "- y: row count" in text and "- time grain: month" in text and "order" not in text


class _Recorder:
    def __init__(self):
        self.seen = None

    def invoke(self, variables):
        self.seen = variables
        return "import plotly.express as px\nfig = px.bar(df, x='cntry_cd', y='churn_cnt')\nprint(fig.to_json())\n"


def test_generate_code_sends_the_plan_as_the_task():
    recorder = _Recorder()
    agent = ChartistAgent(llm=None, generator=recorder, chart_type_hint_style="off")
    context = {"columns": ["cntry_cd", "churn_cnt"], "dtypes": {}, "sample": []}
    agent.generate_code("ignored question", {"visualization_type": "bar"}, context, spec=SPEC)
    assert recorder.seen["task"] == render_spec(SPEC)
