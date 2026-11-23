"""PLANNER_TOOLS=planner: the planner checks its own drafts with tools, at most
3 calls on its first try, then answers in JSON that the usual checks read."""
import json

import pandas as pd
from langchain_core.messages import AIMessage, ToolMessage

from app.services.agents.chartist import ChartistAgent
from app.services.agents.dashboard_flow import build_dashboard
from app.services.agents.data_tools import PLANNER_TOOL_NAMES, ToolBox, tool_specs
from app.services.agents.planning import plan_charts
from app.services.agents.planning_contract import PLANNER_TOOLS_NOTE
from app.services.agents.profiler import profile_table

WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOURS = pd.DataFrame({"weekday": [day for day in WEEK for _ in range(24)], "hourOfDay": list(range(24)) * 7,
                      "bounceRatePct": [30.5 + (i * 7) % 40 for i in range(168)]})
PROFILES = [profile_table("web", HOURS)]
DIRECTION = [{"question": "How does the bounce rate move through the day?", "why": "asked", "table": "web",
              "columns": ["hourOfDay", "bounceRatePct"]}]
PLAN = {"title": "Bounce rate by hour", "question": "How does the bounce rate move through the day?",
        "chart": "line", "table": "web", "x": "hourOfDay", "y": "bounceRatePct", "group": "", "agg": "mean",
        "grain": "", "sort": "", "top_n": 0}
ANSWER = AIMessage(content=json.dumps({"charts": [PLAN]}))
RAW_ANSWER = AIMessage(content=json.dumps({"charts": [{**PLAN, "agg": "none"}]}))


class ToolPlanner:
    """A stand-in planner model. Bound (tools offered) and plain calls read one
    script in order; each call is recorded with which of the two it was."""

    def __init__(self, *replies, bind_fails=False):
        self.replies, self.seen, self.bind_fails, self.specs = list(replies), [], bind_fails, None

    def bind_tools(self, specs):
        if self.bind_fails:
            raise NotImplementedError("this backend has no tools")
        self.specs = specs
        return Bound(self)

    def reply(self, kind, messages):
        self.seen.append((kind, list(messages)))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def invoke(self, messages):
        return self.reply("plain", messages)


class Bound:
    def __init__(self, planner):
        self.planner = planner

    def invoke(self, messages):
        return self.planner.reply("bound", messages)


def calls(*items):
    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"c{i}"} for i, (n, a) in enumerate(items)])


def box():
    return ToolBox({"web": {"type": "file", "name": "web"}}, "", loader=lambda source, data_dir: HOURS,
                   tools=PLANNER_TOOL_NAMES, kinds={"web": PROFILES[0].kinds()})


def plan(model, toolbox):
    return plan_charts(model, DIRECTION, PROFILES, validate=toolbox.validate_spec, toolbox=toolbox)


PREVIEW = ("preview_chart", {"plans": [{"chart": "line", "table": "web", "x": "hourOfDay", "y": "bounceRatePct",
                                        "agg": "none"}]})


def test_the_planner_previews_its_draft_then_answers():
    model, toolbox = ToolPlanner(calls(PREVIEW), ANSWER), box()
    step = plan(model, toolbox)
    assert step.errors == [] and step.items[0]["agg"] == "mean" and step.attempts == 1
    assert [kind for kind, _ in model.seen] == ["bound", "bound"]
    assert [t["function"]["name"] for t in model.specs] == list(PLANNER_TOOL_NAMES)
    first, second = model.seen[0][1], model.seen[1][1]
    assert first[1].content.endswith(PLANNER_TOOLS_NOTE)
    result = second[-1]
    assert isinstance(result, ToolMessage) and result.content.startswith("1. line bounceRatePct by hourOfDay:")
    assert "x repeats within a line" in result.content and not result.content.startswith("{")


def test_several_calls_in_one_reply_are_each_answered_and_charged():
    model, toolbox = ToolPlanner(calls(("row_grain", {"table": "web"}),
                                       ("inspect_column", {"table": "web", "column": "hourOfDay"})), ANSWER), box()
    plan(model, toolbox)
    assert [c.name for c in toolbox.calls] == ["row_grain", "inspect_column"]
    results = [m for m in model.seen[1][1] if isinstance(m, ToolMessage)]
    assert results[0].content.startswith("web: one row per weekday × hourOfDay")


def test_a_planner_that_keeps_calling_is_answered_by_the_plain_model_after_three():
    model = ToolPlanner(calls(("row_grain", {"table": "web"})), calls(PREVIEW),
                        calls(("inspect_column", {"table": "web", "column": "weekday"})), ANSWER)
    toolbox = box()
    step = plan(model, toolbox)
    assert len(toolbox.calls) == 3 and [kind for kind, _ in model.seen] == ["bound", "bound", "bound", "plain"]
    assert step.items and step.errors == []


def test_a_planner_that_calls_no_tool_answers_on_its_first_reply():
    model, toolbox = ToolPlanner(ANSWER), box()
    step = plan(model, toolbox)
    assert step.items and toolbox.calls == [] and [kind for kind, _ in model.seen] == ["bound"]


def test_a_retry_is_a_plain_call_with_the_checks_words():
    model, toolbox = ToolPlanner(RAW_ANSWER, ANSWER), box()
    step = plan(model, toolbox)
    assert step.attempts == 2 and step.items[0]["agg"] == "mean"
    assert [kind for kind, _ in model.seen] == ["bound", "plain"]
    assert "run back and forth" in model.seen[1][1][-1].content


def test_without_tool_support_the_planner_plans_without_them():
    model, toolbox = ToolPlanner(ANSWER, bind_fails=True), box()
    step = plan(model, toolbox)
    assert step.items and toolbox.calls == []
    assert PLANNER_TOOLS_NOTE not in model.seen[0][1][1].content


def test_a_tool_step_that_fails_plans_without_it():
    model, toolbox = ToolPlanner(ConnectionError("tools rejected"), ANSWER), box()
    step = plan(model, toolbox)
    assert step.items and [kind for kind, _ in model.seen] == ["bound", "plain"]


class Fixed:
    def invoke(self, variables):
        return ("import plotly.express as px\n"
                "d = df.groupby('hourOfDay', as_index=False)['bounceRatePct'].mean()\n"
                "fig = px.line(d, x='hourOfDay', y='bounceRatePct')\n"
                "print(fig.to_json())\n")


class Scripted:
    def __init__(self, *replies):
        self.replies = list(replies)

    def invoke(self, messages):
        return type("Reply", (), {"content": self.replies.pop(0)})()


def test_a_dashboard_with_planner_tools_has_no_explorer_step(tmp_path):
    path = tmp_path / "web.csv"
    HOURS.to_csv(path, index=False)
    directions = json.dumps({"directions": [{**DIRECTION[0], "table": "web.csv"}]})
    preview = ("preview_chart", {"plans": [{"chart": "line", "table": "web.csv", "x": "hourOfDay",
                                            "y": "bounceRatePct", "agg": "mean"}]})
    planner = ToolPlanner(calls(preview), AIMessage(content=json.dumps({"charts": [{**PLAN, "table": "web.csv"}]})))
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("bounce rate by hour", [{"type": "file", "name": "web.csv", "path": str(path)}],
                                  str(tmp_path), Scripted(directions), planner, chartist, planner_tools=True))
    labels = [e.data["label"] for e in events if e.kind == "status"]
    assert "Checking the data" not in labels and "Checking the data: previewing 1 draft plan" in labels
    assert [e.kind for e in events][-1] == "chart"


def test_what_the_planner_tools_add_to_the_prompt_is_capped_in_characters():
    # A character cap standing in for tokens. Measured with the base model's chat template while
    # this plan was written (2026-11-23): binding these five tools and this note adds ~850 tokens
    # to the planner's prompt (Spotify table: 1,407 -> 2,262), and three compact results ~675 more
    # (2,937); lora-v2 was trained at 2,048. The probe script prints the server's own counts.
    specs = json.dumps(tool_specs(["t"], PLANNER_TOOL_NAMES), separators=(",", ":"))
    assert len(specs) <= 2000 and len(PLANNER_TOOLS_NOTE) <= 450


class PickyPlanner(ToolPlanner):
    """A server that refuses tool turns when no tools are offered (the plain call)."""

    def invoke(self, messages):
        if any(isinstance(m, ToolMessage) for m in messages):
            self.seen.append(("plain refused", list(messages)))
            raise ValueError("tool messages need tools")
        return self.reply("plain", messages)


def test_a_server_that_refuses_tool_turns_unbound_still_gets_an_answer():
    model = PickyPlanner(calls(("row_grain", {"table": "web"})), calls(PREVIEW),
                         calls(("inspect_column", {"table": "web", "column": "weekday"})), ANSWER)
    step = plan(model, box())
    assert step.items and step.errors == []
    assert [kind for kind, _ in model.seen][-2:] == ["plain refused", "plain"]
    assert not any(isinstance(m, ToolMessage) for m in model.seen[-1][1])
