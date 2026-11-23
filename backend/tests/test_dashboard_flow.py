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


def _status_labels(events):
    return [e.data["label"] for e in events if e.kind == "status"]


def test_an_analyst_retry_shows_on_screen(tmp_path):
    # Retries took minutes behind one unchanging label, which read as a stuck build.
    bad = json.dumps({"directions": [{"question": "q", "why": "", "table": "saas.csv", "columns": ["x"]}]})
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("churn by country", [_source(tmp_path)], str(tmp_path),
                                  Scripted(bad, DIRECTIONS), Scripted(CHARTS), chartist, top=5))
    labels = _status_labels(events)
    assert len(labels) == 4 and labels[1] == "Choosing what to show" and labels[3] == "Planning the charts"
    assert labels[2].startswith("Choosing what to show") and "try 2 of 3" in labels[2]


def test_a_planner_retry_shows_on_screen(tmp_path):
    bad = CHARTS.replace('"x": "cntry_cd"', '"x": "nope"')
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("churn by country", [_source(tmp_path)], str(tmp_path),
                                  Scripted(DIRECTIONS), Scripted(bad, CHARTS), chartist, top=5))
    labels = _status_labels(events)
    assert len(labels) == 4 and labels[2] == "Planning the charts"
    assert labels[3].startswith("Planning the charts") and "try 2 of 3" in labels[3]
    assert events[-1].kind == "chart"


from langchain_core.messages import AIMessage


class Recorder(Scripted):
    """Scripted, and keeps every message list it was sent."""

    def __init__(self, *replies):
        super().__init__(*replies)
        self.seen = []

    def invoke(self, messages):
        self.seen.append(list(messages))
        return super().invoke(messages)


class Explorer:
    def __init__(self, *replies):
        self.replies = list(replies)

    def bind_tools(self, specs):
        return self

    def invoke(self, messages):
        return self.replies.pop(0)


INSPECT = AIMessage(content="", tool_calls=[{"name": "inspect_column",
                                             "args": {"table": "saas.csv", "column": "cntry_cd"}, "id": "c0"}])


def test_with_tools_the_facts_reach_the_analyst_and_the_planner(tmp_path):
    analyst, planner = Recorder(DIRECTIONS), Recorder(CHARTS)
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("churn by country", [_source(tmp_path)], str(tmp_path), analyst, planner,
                                  chartist, top=5, explorer_llm=Explorer(INSPECT, AIMessage(content="DONE"))))
    labels = [e.data["label"] for e in events if e.kind == "status"]
    assert "Checking the data" in labels and any(label.startswith("Checking the data: ") for label in labels)
    assert "Facts checked on the full data:" in analyst.seen[0][-1].content
    assert "Facts checked on the full data:" in planner.seen[0][-1].content
    plan = next(e for e in events if e.kind == "plan").data
    assert plan["facts"] and "cntry_cd" in plan["facts"][0]


def test_memory_reaches_the_analyst_and_not_the_planner(tmp_path):
    analyst, planner = Recorder(DIRECTIONS), Recorder(CHARTS)
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    memory = "Already on this report (do not repeat these; add what is missing):\n1. bar · Churn by country"
    list(build_dashboard("", [_source(tmp_path)], str(tmp_path), analyst, planner, chartist, memory=memory))
    assert memory in analyst.seen[0][-1].content and memory not in planner.seen[0][-1].content


def test_a_plan_that_breaks_on_the_real_data_goes_back_to_the_planner(tmp_path):
    # 60 names x 25 rows: the profile calls `name` a category (60 values, under 5% of
    # 1,500 rows), so the bar passes the rules and only the data check can catch it.
    path = tmp_path / "names.csv"
    pd.DataFrame({"name": [f"n{i}" for i in range(60)] * 25, "v": [i % 7 for i in range(1500)]}).to_csv(path, index=False)
    source = {"type": "file", "name": "names.csv", "path": str(path)}
    directions = json.dumps({"directions": [{"question": "Which names score most?", "why": "asked",
                                             "table": "names.csv", "columns": ["name", "v"]}]})
    bar = {"title": "Top names", "question": "Which names score most?", "chart": "bar", "table": "names.csv",
           "x": "name", "y": "v", "group": "", "agg": "sum", "grain": "", "sort": "desc", "top_n": 0}
    planner = Recorder(json.dumps({"charts": [bar]}), json.dumps({"charts": [{**bar, "top_n": 20}]}))
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("", [source], str(tmp_path), Scripted(directions), planner, chartist,
                                  explorer_llm=Explorer(AIMessage(content="DONE"))))
    plan = next(e for e in events if e.kind == "plan").data
    assert plan["attempts"]["planner"] == 2 and plan["placed"][0].spec["top_n"] == 20
    assert "60 bars" in planner.seen[1][-1].content
