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
