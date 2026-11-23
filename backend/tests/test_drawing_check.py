"""A line the model draws back and forth goes back to the model, on every path
that runs its code (dashboard, ask bar, "/" kinds, comparison)."""
import pandas as pd

from app.services import comparison
from app.services.agents.chartist import ChartistAgent
from app.services.agents.chartist_contract import REPEATED_X_FIX, figure_problems
from app.services.agents.spec_runner import run_spec
from app.services.agents.workflow import run_on_frame
from app.utils.executor import SafeExecutor

WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOURS = pd.DataFrame({"weekday": [day for day in WEEK for _ in range(24)], "hourOfDay": list(range(24)) * 7,
                      "bounceRatePct": [30 + (i * 7) % 40 for i in range(168)]})
LOOPS = ("import plotly.express as px\n"
         "fig = px.line(df, x='hourOfDay', y='bounceRatePct')\n"
         "print(fig.to_json())\n")
ONE_POINT_PER_HOUR = ("import plotly.express as px\n"
                      "d = df.groupby('hourOfDay', as_index=False)['bounceRatePct'].mean().sort_values('hourOfDay')\n"
                      "fig = px.line(d, x='hourOfDay', y='bounceRatePct')\n"
                      "print(fig.to_json())\n")


def figure(**fields):
    return {"data": [{"type": "scatter", "x": [0, 1, 0, 1], "y": [1, 2, 3, 4], **fields}]}


def test_a_line_whose_x_repeats_is_a_problem_the_model_can_act_on():
    problems = figure_problems(figure(mode="lines"))
    assert problems == ["the line 'trace 1' has 4 points but only 2 x values, so it runs back and forth: "
                        + REPEATED_X_FIX]


def test_a_stacked_area_is_a_line():
    assert figure_problems(figure(stackgroup="1")) and figure_problems(figure(mode="lines+markers"))


def test_markers_may_repeat_x():
    assert figure_problems(figure(mode="markers")) == [] and figure_problems(figure(mode="none")) == []


def test_a_trace_with_no_mode_is_drawn_as_a_line():
    assert figure_problems(figure()) == [
        "the line 'trace 1' has 4 points but only 2 x values, so it runs back and forth: " + REPEATED_X_FIX
        + " (it has no mode, so Plotly draws it as a line; for a scatter, set mode='markers')"]


def test_a_closed_shape_may_go_back_over_its_x():
    band = figure(mode="lines", fill="toself", x=[0, 1, 2, 2, 1, 0], y=[3, 4, 5, 1, 2, 1])
    assert figure_problems(band) == []


def test_an_x_repeated_with_the_same_y_is_fine():
    assert figure_problems(figure(mode="lines", y=[1, 2, 1, 2])) == []


def test_a_line_with_each_x_once_or_unreadable_values_is_fine():
    assert figure_problems(figure(mode="lines", x=[0, 1, 2, 3])) == []
    assert figure_problems(figure(mode="lines", x={"dtype": "i1", "bdata": "!!"})) == []
    assert figure_problems(figure(mode="lines", y={"dtype": "i1", "bdata": "!!"})) == []
    assert figure_problems(figure(mode="lines", y=None)) == []
    assert figure_problems({"data": [{"type": "bar", "x": [0, 0]}]}) == []


def test_the_model_is_asked_to_fix_a_line_that_runs_back_and_forth():
    # px.line stores x as a typed array, so this also shows the figure is decoded before it is read.
    asked = []
    outcome = run_on_frame(SafeExecutor(), LOOPS, HOURS,
                           repair=lambda code, problem: asked.append(problem) or ONE_POINT_PER_HOUR)
    assert outcome["repairs"] == 1 and outcome["repair_reasons"] == asked and REPEATED_X_FIX in asked[0]
    assert outcome["execution_result"]["success"] and outcome["code_run"] == ONE_POINT_PER_HOUR


def test_a_line_never_fixed_is_reported_failed_without_a_figure():
    outcome = run_on_frame(SafeExecutor(), LOOPS, HOURS, repair=lambda code, problem: LOOPS)
    assert outcome["repairs"] == 2 and "back and forth" in outcome["error"]
    assert outcome["execution_result"]["success"] is False and outcome["execution_result"]["figure"] is None


class Scripted:
    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []

    def invoke(self, variables):
        self.requests.append(dict(variables))
        return self.replies.pop(0)


def _chartist(*replies):
    model = Scripted(*replies)
    return ChartistAgent(llm=None, generator=model, chart_type_hint_style="off"), model


def test_a_planned_chart_says_why_it_was_repaired(tmp_path):
    path = tmp_path / "web.csv"
    HOURS.to_csv(path, index=False)
    spec = {"title": "Bounce rate by hour", "question": "Bounce rate by hour", "chart": "line", "table": "web.csv",
            "x": "hourOfDay", "y": "bounceRatePct", "group": "", "agg": "mean", "grain": "", "sort": "", "top_n": 0}
    chartist, model = _chartist(LOOPS, ONE_POINT_PER_HOUR)
    result = run_spec(spec, {"type": "file", "name": "web.csv", "path": str(path)}, chartist, str(tmp_path))
    assert result["error"] == "" and result["repairs"] == 1
    assert REPEATED_X_FIX in result["repair_reasons"][0] and REPEATED_X_FIX in model.requests[1]["problem"]


def test_a_comparison_cell_with_a_line_never_fixed_is_not_a_chart():
    chartist, _ = _chartist(LOOPS, LOOPS, LOOPS)
    context = {"columns": list(HOURS.columns), "dtypes": {c: str(t) for c, t in HOURS.dtypes.items()},
               "sample": HOURS.head(3).to_dict("records")}
    cell = comparison.run_cell("slm", chartist, "Bounce rate by hour", {}, context, HOURS, SafeExecutor())
    assert not cell.ok and cell.figure is None and cell.repairs == 2 and "back and forth" in cell.error


def test_a_staircase_that_never_turns_back_is_fine():
    assert figure_problems(figure(mode="lines", x=[1, 1, 2, 3, 3, 3], y=[1, 2, 3, 4, 5, 6])) == []


def test_a_sorted_x_whose_y_jumps_is_still_a_problem():
    assert figure_problems(figure(mode="lines", x=[0, 0, 1, 1], y=[5, 1, 4, 2]))
