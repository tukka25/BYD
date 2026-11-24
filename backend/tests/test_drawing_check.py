"""A line the model draws back and forth, or bars it draws on raw rows, go back
to the model, on every path that runs its code (dashboard, ask bar, "/" kinds,
comparison)."""
import pandas as pd

from app.services import comparison
from app.services.agents.chartist import ChartistAgent
from app.services.agents.chartist_contract import REPEATED_BAR_FIX, REPEATED_X_FIX, figure_problems
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


# "Bounce Rate by Weekday" in the live app: px.bar on 168 weekday x hour rows,
# so each weekday's 24 rows stack into one bar of their sum under an "Average" axis.
RAW_BARS = ("import plotly.express as px\n"
            "fig = px.bar(df, x='weekday', y='bounceRatePct')\n"
            "print(fig.to_json())\n")
ONE_BAR_PER_DAY = ("import plotly.express as px\n"
                   "d = df.groupby('weekday', as_index=False, sort=False)['bounceRatePct'].mean()\n"
                   "fig = px.bar(d, x='weekday', y='bounceRatePct')\n"
                   "print(fig.to_json())\n")


def bars(**fields):
    return {"data": [{"type": "bar", "x": ["Mon", "Mon", "Tue", "Tue"], "y": [1, 2, 3, 4], **fields}]}


def test_bars_that_repeat_a_category_are_a_problem_the_model_can_act_on():
    assert figure_problems(bars()) == [
        "the bar series 'trace 1' has 4 bars on 2 categories, and Plotly stacks bars that share a category: "
        + REPEATED_BAR_FIX]


def test_several_bar_series_that_repeat_a_category_make_one_problem():
    # px.bar(df, x='weekday', y='bounceRatePct', color='weekday') on the raw rows: a series per weekday.
    per_day = {"data": [{"type": "bar", "name": day, "x": [day] * 24, "y": [50.0] * 24} for day in WEEK]}
    assert figure_problems(per_day) == [
        "7 bar series repeat a category (the bar series 'Mon' has 24 bars on 1 category), and Plotly stacks "
        "bars that share a category: " + REPEATED_BAR_FIX]


def test_one_bar_per_category_and_bars_with_no_value_are_fine():
    assert figure_problems(bars(x=["Mon", "Tue", "Wed", "Thu"])) == []
    # Plotly draws no bar for a missing value, so a category that repeats only there is drawn once.
    assert figure_problems(bars(y=[1, None, 3, float("nan")])) == []
    assert figure_problems(bars(orientation="h", y=["a", "b", "c", "d"], x=[1, 2, 3, 4])) == []


def test_the_model_is_asked_to_fix_bars_drawn_on_raw_rows():
    asked = []
    outcome = run_on_frame(SafeExecutor(), RAW_BARS, HOURS,
                           repair=lambda code, problem: asked.append(problem) or ONE_BAR_PER_DAY)
    assert outcome["repairs"] == 1 and outcome["repair_reasons"] == asked
    assert REPEATED_BAR_FIX in asked[0] and "168 bars on 7 categories" in asked[0]
    assert outcome["execution_result"]["success"] and outcome["code_run"] == ONE_BAR_PER_DAY


def test_a_number_as_colour_is_one_series_and_the_model_is_told_to_colour_by_text():
    # px draws a numeric `color` as one series with a colour scale, so grouped bars share categories.
    split = {"data": [{"type": "bar", "x": ["N", "N", "S", "S"], "y": [100, 160, 100, 130],
                       "marker": {"color": [2, 3, 2, 3], "coloraxis": "coloraxis"}}]}
    assert figure_problems(split) == [
        "the bar series 'trace 1' has 4 bars on 2 categories because its colour is a number, which Plotly "
        "draws as one series: " + REPEATED_BAR_FIX]


def test_raw_rows_coloured_by_a_number_are_still_raw_rows():
    # A colour with about one value per bar groups nothing: these are the rows, not a split.
    measure = {"data": [{"type": "bar", "x": ["N", "N", "S", "S"], "y": [100, 160, 100, 130],
                         "marker": {"color": [100, 160, 100.5, 130]}}]}
    assert "Plotly stacks bars that share a category" in figure_problems(measure)[0]
    # Nor is a colour value repeated within one category.
    twice = {"data": [{"type": "bar", "x": ["N", "N", "S", "S"], "y": [1, 2, 3, 4], "marker": {"color": [2, 2, 3, 3]}}]}
    assert "Plotly stacks bars that share a category" in figure_problems(twice)[0]


PROPERTY = pd.DataFrame({"zone": ["N", "N", "N", "S", "S", "S"], "bedrooms": [2, 3, 3, 2, 2, 3],
                         "price": [100.0, 150.0, 170.0, 90.0, 110.0, 130.0]})
NUMBER_COLOUR = ("import plotly.express as px\n"
                 "d = df.groupby(['zone', 'bedrooms'], as_index=False)['price'].mean()\n"
                 "fig = px.bar(d, x='zone', y='price', color='bedrooms', barmode='group')\n"
                 "print(fig.to_json())\n")
TEXT_COLOUR = ("import plotly.express as px\n"
               "d = df.groupby(['zone', 'bedrooms'], as_index=False)['price'].mean()\n"
               "d['bedrooms'] = d['bedrooms'].astype(str)\n"
               "fig = px.bar(d, x='zone', y='price', color='bedrooms', barmode='group')\n"
               "print(fig.to_json())\n")


def test_grouped_bars_coloured_by_a_number_are_sent_back_to_colour_by_text():
    # "Average Sale Price by Zone and Bedrooms": lora-v2 grouped right, coloured by bedroomCount, and the
    # bars of each zone overlapped in one series. Told only to aggregate, it sent the same code back twice.
    asked = []
    outcome = run_on_frame(SafeExecutor(), NUMBER_COLOUR, PROPERTY,
                           repair=lambda code, problem: asked.append(problem) or TEXT_COLOUR)
    assert outcome["repairs"] == 1 and "because its colour is a number" in asked[0]
    assert outcome["execution_result"]["success"] and outcome["code_run"] == TEXT_COLOUR


def test_bars_never_fixed_are_reported_failed_without_a_figure():
    outcome = run_on_frame(SafeExecutor(), RAW_BARS, HOURS, repair=lambda code, problem: RAW_BARS)
    assert outcome["repairs"] == 2 and "Plotly stacks bars" in outcome["error"]
    assert outcome["execution_result"]["success"] is False and outcome["execution_result"]["figure"] is None
