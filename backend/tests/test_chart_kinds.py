"""Every kind the planner accepts has a label for the user, and nothing else does."""
from app.services.agents.chart_kinds import KIND_INFO, chart_kinds
from app.services.agents.planning_contract import CHART_KINDS


def test_every_planner_kind_has_a_label_and_nothing_else_does():
    assert set(KIND_INFO) == set(CHART_KINDS)


def test_the_list_follows_the_planner_order_with_a_label_each():
    kinds = chart_kinds()
    assert [k["kind"] for k in kinds] == list(CHART_KINDS)
    assert all(isinstance(k["label"], str) and k["label"] for k in kinds)
