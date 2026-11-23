import json
import logging

import pandas as pd

from app.services.agents.planning import plan_charts, propose_directions
from app.services.agents.profiler import profile_table


class Scripted:
    """Replies in order and records every message list it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return type("Reply", (), {"content": reply})()


def _profiles():
    frame = pd.DataFrame({"cntry_cd": ["DE", "US"] * 5, "churn_cnt": range(10)})
    return [profile_table("saas", frame)]


GOOD = json.dumps({"directions": [{"question": "Where is churn highest?", "why": "asked",
                                   "table": "saas", "columns": ["cntry_cd", "churn_cnt"]}]})
BAD = json.dumps({"directions": [{"question": "q", "why": "", "table": "saas", "columns": ["country"]}]})


def test_a_failed_check_goes_back_to_the_model():
    llm = Scripted(BAD, GOOD)
    step = propose_directions(llm, "churn by country", _profiles())
    assert step.attempts == 2 and step.errors == []
    assert step.items[0]["columns"] == ["cntry_cd", "churn_cnt"]
    retry = llm.calls[1][-1].content
    assert "'country' not in table 'saas'" in retry and "Reply again" in retry


def test_the_best_attempt_is_kept_when_none_is_clean():
    llm = Scripted(BAD, BAD, BAD)
    step = propose_directions(llm, "", _profiles())
    assert step.attempts == 3 and step.items == [] and step.errors


def test_a_model_failure_is_an_error_not_a_crash():
    step = propose_directions(Scripted(RuntimeError("server down")), "", _profiles())
    assert step.items == [] and "server down" in step.errors[0]


def test_the_planner_gets_the_directions_and_returns_checked_plans():
    directions = json.loads(GOOD)["directions"]
    charts = json.dumps({"charts": [{"title": "Churn by country", "question": "Where?", "chart": "bar",
                                     "table": "saas", "x": "cntry_cd", "y": "churn_cnt", "group": "",
                                     "agg": "sum", "grain": "", "sort": "desc", "top_n": 0}]})
    llm = Scripted(charts)
    step = plan_charts(llm, directions, _profiles())
    assert step.errors == [] and step.items[0]["title"] == "Churn by country"
    assert "1. Where is churn highest?" in llm.calls[0][1].content


def test_each_failed_try_is_logged_with_its_problems(caplog):
    # A plan that needs retries was invisible in the api log: only the final plan was logged.
    caplog.set_level(logging.INFO, logger="app.services.agents.planning")
    propose_directions(Scripted(BAD, GOOD), "churn by country", _profiles())
    lines = [r.getMessage() for r in caplog.records if r.name == "app.services.agents.planning"]
    failed = [line for line in lines if "try 1 of 3" in line]
    assert failed and "analyst" in failed[0] and "'country' not in table 'saas'" in failed[0]



SAAS = pd.DataFrame({"cntry_cd": ["DE", "US", "BR", "FR"] * 50, "plan_tier": ["a", "b"] * 100,
                     "mrr": [i % 37 * 1.5 for i in range(200)]})
ONE_DIRECTION = [{"question": "q", "why": "w", "table": "saas", "columns": ["cntry_cd", "mrr"]}]


def _chart(kind, x="cntry_cd", y="mrr", title="t"):
    return {"title": title, "question": "q", "chart": kind, "table": "saas", "x": "" if kind == "kpi" else x,
            "y": y, "group": "", "agg": "sum", "grain": "", "sort": "", "top_n": 0}


def test_a_try_with_the_picked_kind_beats_a_bigger_try_without_it():
    # The final review's reproduction: two bars without the pie used to be kept over a
    # valid pie next to one broken chart, so a /pie brief could end with no pie.
    two_bars = json.dumps({"charts": [_chart("bar", title="a"), _chart("bar", x="plan_tier", title="b")]})
    pie_and_broken = json.dumps({"charts": [_chart("pie", title="p"), _chart("bar", y="no_such_column", title="x")]})
    step = plan_charts(Scripted(two_bars, pie_and_broken, pie_and_broken), ONE_DIRECTION,
                       [profile_table("saas", SAAS)], required_kinds=("pie",))
    assert step.attempts == 3 and [s["chart"] for s in step.items] == ["pie"]
    assert not any("asked for a pie" in e for e in step.errors)


def test_the_planner_is_told_the_picked_kinds_up_front():
    llm = Scripted(json.dumps({"charts": [_chart("pie", title="p"), _chart("kpi", title="k")]}))
    step = plan_charts(llm, ONE_DIRECTION, [profile_table("saas", SAAS)], required_kinds=("pie", "kpi"))
    assert step.attempts == 1 and step.errors == []
    assert llm.calls[0][1].content.endswith("\n\nInclude these chart kinds: Pie chart, KPI card.")
