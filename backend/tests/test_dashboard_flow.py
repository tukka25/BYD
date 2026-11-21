import json

import pandas as pd

from app.services.agents.chartist import ChartistAgent
from app.services.agents.dashboard_flow import build_dashboard, profile_sources


class Scripted:
    def __init__(self, *replies):
        self.replies = list(replies)

    def invoke(self, messages):
        return type("Reply", (), {"content": self.replies.pop(0)})()


class Fixed:
    def invoke(self, variables):
        return (
            "import plotly.express as px\n"
            "d = df.groupby('cntry_cd', as_index=False)['churn_cnt'].sum()\n"
            "fig = px.bar(d, x='cntry_cd', y='churn_cnt')\n"
            "print(fig.to_json())\n"
        )


def _source(tmp_path):
    path = tmp_path / "saas.csv"
    pd.DataFrame({"snap_dt": ["2024-01-09", "2024-02-09"] * 5, "cntry_cd": ["DE", "US"] * 5,
                  "churn_cnt": range(10)}).to_csv(path, index=False)
    return {"type": "file", "name": "saas.csv", "path": str(path)}


DIRECTIONS = json.dumps({"directions": [{"question": "Where is churn highest?", "why": "asked",
                                         "table": "saas.csv", "columns": ["cntry_cd", "churn_cnt"]}]})
CHARTS = json.dumps({"charts": [{"title": "Churn by country", "question": "Where is churn highest?",
                                 "chart": "bar", "table": "saas.csv", "x": "cntry_cd", "y": "churn_cnt",
                                 "group": "", "agg": "sum", "grain": "", "sort": "desc", "top_n": 0}]})


def test_profiles_label_files_by_name(tmp_path):
    entries = profile_sources([_source(tmp_path)], str(tmp_path))
    assert entries[0].label == "saas.csv" and entries[0].profile.kinds()["snap_dt"] == "date"


def test_a_dashboard_is_planned_and_drawn(tmp_path):
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("churn by country", [_source(tmp_path)], str(tmp_path),
                                  Scripted(DIRECTIONS), Scripted(CHARTS), chartist, top=5))
    kinds = [e.kind for e in events]
    assert kinds == ["status", "status", "status", "plan", "step", "chart"]
    plan = events[3].data
    assert plan["intro"]["y"] == 5 and plan["placed"][0].y == 8
    assert plan["attempts"] == {"analyst": 1, "planner": 1} and plan["dropped"] == []
    assert events[5].data["result"]["execution_result"]["figure"]


def test_an_unusable_plan_is_an_error_event(tmp_path):
    bad = json.dumps({"directions": [{"question": "q", "why": "", "table": "saas.csv", "columns": ["x"]}]})
    events = list(build_dashboard("", [_source(tmp_path)], str(tmp_path),
                                  Scripted(bad, bad, bad), Scripted(), None))
    assert events[-1].kind == "error" and "what to show" in events[-1].data["detail"]
