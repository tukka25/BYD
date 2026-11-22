"""Single charts and the model comparison get the same repair loop as planned charts:
failed code goes back to the model, and nothing else ever draws the chart."""
import pandas as pd

from app.services import comparison
from app.services.agents import workflow
from app.services.agents.chartist import ChartistAgent
from app.services.agents.chartist_contract import VIOLATION_WORDS, ContractViolation, problems_with
from app.utils.executor import SafeExecutor

GOOD = (
    "import plotly.express as px\n"
    "d = df.groupby('cntry_cd', as_index=False)['churn_cnt'].sum()\n"
    "fig = px.bar(d, x='cntry_cd', y='churn_cnt')\n"
    "print(fig.to_json())\n"
)
BROKEN = "import plotly.express as px\nfig = px.bar(df, x='nope', y='churn_cnt')\nprint(fig.to_json())\n"
FRAME = pd.DataFrame({"cntry_cd": ["DE", "US", "DE"], "churn_cnt": [3, 5, 4]})
CONTEXT = {"columns": ["cntry_cd", "churn_cnt"], "dtypes": {"cntry_cd": "str", "churn_cnt": "int64"},
           "sample": FRAME.head(3).to_dict("records")}


class Scripted:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def invoke(self, variables):
        self.requests.append(dict(variables))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _chartist(*replies):
    model = Scripted(*replies)
    return ChartistAgent(llm=None, generator=model, chart_type_hint_style="off"), model


def test_a_single_chart_goes_back_to_the_model_too(tmp_path, monkeypatch):
    path = tmp_path / "saas.csv"
    FRAME.to_csv(path, index=False)
    chartist, model = _chartist(BROKEN, GOOD)
    monkeypatch.setattr(workflow, "_agents", lambda: (None, None, chartist, SafeExecutor()))
    state = {"user_query": "Where is churn highest?", "plan": {}, "source_decision": {},
             "data_context": {**CONTEXT, "filepath": str(path)}}
    state.update(workflow.coding_node(state))
    out = workflow.execution_node(state)
    assert out["execution_result"]["figure"] and out["code_run"].strip() == GOOD.strip()
    assert "nope" in model.requests[1]["problem"]


def test_a_single_chart_model_that_cannot_be_reached_is_an_error(monkeypatch):
    chartist, _ = _chartist(ConnectionError("server down"))
    monkeypatch.setattr(workflow, "_agents", lambda: (None, None, chartist, SafeExecutor()))
    out = workflow.coding_node({"user_query": "q", "plan": {}, "source_decision": {}, "data_context": CONTEXT})
    assert "server down" in out["error"]


def test_a_comparison_cell_lets_the_model_fix_its_code():
    chartist, _ = _chartist(BROKEN, GOOD)
    cell = comparison.run_cell("slm", chartist, "Where is churn highest?", {}, CONTEXT, FRAME, SafeExecutor())
    assert cell.ok and cell.repairs == 1 and cell.code.strip() == GOOD.strip()


def test_a_comparison_cell_the_model_cannot_fix_fails_with_no_stand_in():
    chartist, _ = _chartist(BROKEN, BROKEN, BROKEN)
    cell = comparison.run_cell("slm", chartist, "Where is churn highest?", {}, CONTEXT, FRAME, SafeExecutor())
    assert not cell.ok and cell.error and cell.figure is None and cell.repairs == 2


def test_contract_problems_are_put_in_words_the_model_can_act_on():
    assert problems_with(GOOD) == []
    syntax = problems_with("fig = px.bar(df\nprint(fig.to_json())\n")
    assert len(syntax) == 1 and "line" in syntax[0]  # the parser's own message, with where
    assert set(VIOLATION_WORDS) == set(ContractViolation)  # a new rule cannot reach the model as nothing
