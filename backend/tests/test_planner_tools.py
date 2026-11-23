"""PLANNER_TOOLS=planner: the planner drafts with its trained prompt and no tools;
on its first try a separate checking turn holds the tools (at most 3 calls),
and the lines it asks to change go back to the planner once, as a retry would."""
import json

import pandas as pd
from langchain_core.messages import AIMessage, ToolMessage

from app.services.agents.chartist import ChartistAgent
from app.services.agents.dashboard_flow import build_dashboard
from app.services.agents.data_tools import PLANNER_TOOL_NAMES, ToolBox, tool_specs
from app.services.agents.planning import changes_asked, plan_charts
from app.services.agents.planning_contract import CHECKER_SYSTEM_PROMPT, FIX_PROMPT
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
NO_CHANGES = AIMessage(content="no changes")
PREVIEW = ("preview_chart", {"plans": [{"chart": "line", "table": "web", "x": "hourOfDay", "y": "bounceRatePct",
                                        "agg": "none"}]})


class ToolPlanner:
    """A stand-in model. Bound (tools offered) and plain calls read one script in
    order; each call is recorded with which of the two it was."""

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


def kinds(model):
    return [kind for kind, _ in model.seen]


def test_the_planner_drafts_plainly_and_a_separate_turn_checks_the_draft():
    model, toolbox = ToolPlanner(ANSWER, calls(PREVIEW), NO_CHANGES), box()
    step = plan(model, toolbox)
    assert step.items and step.errors == [] and step.items[0]["agg"] == "mean"
    assert kinds(model) == ["plain", "bound", "bound"] and [c.name for c in toolbox.calls] == ["preview_chart"]
    planner_user = model.seen[0][1][1].content
    assert not any(name in planner_user for name in PLANNER_TOOL_NAMES)
    check = model.seen[1][1]
    assert check[0].content == CHECKER_SYSTEM_PROMPT and ANSWER.content in check[1].content
    fact = [m for m in model.seen[2][1] if isinstance(m, ToolMessage)][0].content
    assert fact.startswith("1. line bounceRatePct by hourOfDay: 168 points per line, x repeats within a line")


def test_a_change_asked_goes_back_to_the_planner_once_in_the_retrys_form():
    asked = "1. Change agg to 'mean' so the line does not run back and forth\n2. no changes"
    model = ToolPlanner(RAW_ANSWER, calls(PREVIEW), AIMessage(content=asked), ANSWER)
    step = plan(model, box())
    assert step.items and step.errors == [] and step.items[0]["agg"] == "mean"
    assert kinds(model) == ["plain", "bound", "bound", "plain"]
    revision = model.seen[3][1]
    assert revision[-2].content == RAW_ANSWER.content
    assert revision[-1].content == FIX_PROMPT.format(errors="- Change agg to 'mean' so the line does not run back and forth")


def test_only_the_no_change_reply_the_prompt_asks_for_counts_as_no_change():
    for reply in ("no changes", "No changes.", "1. no changes", "Plan 1: no changes", "Chart 2: No change needed",
                  "none", "1) None", "---", ""):
        assert changes_asked(reply) == [], reply
    assert changes_asked("1. no changes\n2. no changes") == []


def test_any_other_line_asks_for_a_change():
    for reply in ("Correct the agg to 'mean'", "No, change it.", "OK, but change agg to mean",
                  "No change to the chart type, change agg to mean", "Change agg to 'mean':", "Looks good to me"):
        assert changes_asked(reply) == [reply], reply
    assert changes_asked("1. Change agg to 'mean'\n2. no changes") == ["Change agg to 'mean'"]
    assert changes_asked("Plan 2: Change agg to 'mean'") == ["Change agg to 'mean'"]


def test_a_revision_that_checks_worse_leaves_the_draft():
    model = ToolPlanner(ANSWER, AIMessage(content="1. Give it a shorter title"), AIMessage(content="not json"))
    step = plan(model, box())
    assert step.items and step.items[0]["title"] == PLAN["title"] and step.attempts == 1
    assert kinds(model) == ["plain", "bound", "plain"]


def test_a_revision_that_checks_as_well_is_kept():
    shorter = AIMessage(content=json.dumps({"charts": [{**PLAN, "title": "Bounce by hour"}]}))
    model = ToolPlanner(ANSWER, AIMessage(content="1. Give it a shorter title"), shorter)
    step = plan(model, box())
    assert step.items and step.items[0]["title"] == "Bounce by hour"


def test_the_check_runs_on_the_first_try_only_and_a_retry_is_plain():
    model = ToolPlanner(RAW_ANSWER, NO_CHANGES, ANSWER)
    step = plan(model, box())
    assert step.items and step.errors == [] and step.attempts == 2
    assert kinds(model) == ["plain", "bound", "plain"]
    assert model.seen[2][1][-1].content.startswith("Some of that did not check out:")


def test_a_check_that_keeps_calling_is_answered_by_the_plain_model_after_three():
    model, toolbox = ToolPlanner(ANSWER, calls(PREVIEW), calls(PREVIEW), calls(PREVIEW), NO_CHANGES), box()
    step = plan(model, toolbox)
    assert step.items and len(toolbox.calls) == 3
    assert kinds(model) == ["plain", "bound", "bound", "bound", "plain"]
    assert model.seen[-1][1][0].content == CHECKER_SYSTEM_PROMPT


def test_without_tool_support_the_planner_plans_without_a_check():
    model = ToolPlanner(ANSWER, bind_fails=True)
    step = plan(model, box())
    assert step.items and step.errors == [] and kinds(model) == ["plain"]


def test_a_check_that_fails_leaves_the_draft():
    model = ToolPlanner(ANSWER, ConnectionError("model server went away"))
    step = plan(model, box())
    assert step.items and step.errors == [] and kinds(model) == ["plain", "bound"]


def test_a_revision_that_fails_leaves_the_draft():
    model = ToolPlanner(ANSWER, AIMessage(content="1. Give it a shorter title"), ConnectionError("gone"))
    step = plan(model, box())
    assert step.items and step.items[0]["title"] == PLAN["title"] and kinds(model) == ["plain", "bound", "plain"]


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


def test_a_dashboard_in_planner_mode_shows_the_check_and_has_no_explorer_step(tmp_path):
    path = tmp_path / "web.csv"
    HOURS.to_csv(path, index=False)
    directions = json.dumps({"directions": [{**DIRECTION[0], "table": "web.csv"}]})
    preview = ("preview_chart", {"plans": [{"chart": "line", "table": "web.csv", "x": "hourOfDay",
                                            "y": "bounceRatePct", "agg": "mean"}]})
    planner = ToolPlanner(AIMessage(content=json.dumps({"charts": [{**PLAN, "table": "web.csv"}]})),
                          calls(preview), NO_CHANGES)
    chartist = ChartistAgent(llm=None, generator=Fixed(), chart_type_hint_style="off")
    events = list(build_dashboard("bounce rate by hour", [{"type": "file", "name": "web.csv", "path": str(path)}],
                                  str(tmp_path), Scripted(directions), planner, chartist, planner_tools=True))
    labels = [e.data["label"] for e in events if e.kind == "status"]
    assert "Checking the data" not in labels and "Checking the data: previewing 1 draft plan" in labels
    assert [e.kind for e in events][-1] == "chart"


def test_the_checking_turns_prompt_and_tools_stay_small():
    # Measured in the controller's runs (2026-11-23): the checking turn's prompt was 1,154-1,924 server
    # tokens with two drafts; lora-v2 was trained at 2,048. These caps stand in for tokens.
    specs = json.dumps(tool_specs(["t"], PLANNER_TOOL_NAMES), separators=(",", ":"))
    assert len(specs) <= 2000 and len(CHECKER_SYSTEM_PROMPT) <= 900


class PickyPlanner(ToolPlanner):
    """A server that refuses tool turns when no tools are offered (a plain call)."""

    def invoke(self, messages):
        if any(isinstance(m, ToolMessage) for m in messages):
            self.seen.append(("plain refused", list(messages)))
            raise ValueError("tool messages need tools")
        return self.reply("plain", messages)


def test_a_server_that_refuses_tool_turns_unbound_still_gets_the_checks_answer():
    model = PickyPlanner(ANSWER, calls(("row_grain", {"table": "web"})), calls(PREVIEW),
                         calls(("inspect_column", {"table": "web", "column": "weekday"})), NO_CHANGES)
    step = plan(model, box())
    assert step.items and step.errors == []
    assert kinds(model)[-2:] == ["plain refused", "plain"]
    assert not any(isinstance(m, ToolMessage) for m in model.seen[-1][1])
