"""bar_repeats: bar traces that repeat a category, which Plotly stacks into one bar.

The two shapes the model drew in live use on web_traffic.csv (168 weekday x hour
rows) are the first two tests.
"""
from app.services.agents.chartist_contract import bar_repeats, figure_problems

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def raw_rows_in_one_trace():
    # px.bar(df, x='weekday', y='sessions')
    xs = [day for day in WEEKDAYS for _ in range(24)]
    return {"data": [{"type": "bar", "orientation": "v", "x": xs, "y": [1.0] * len(xs)}]}


def raw_rows_in_a_trace_per_colour():
    # px.bar(df, x='weekday', y='bounceRatePct', color='weekday')
    return {"data": [{"type": "bar", "name": day, "x": [day] * 24, "y": [50.0] * 24} for day in WEEKDAYS]}


def test_one_trace_of_raw_rows_is_reported():
    problems = bar_repeats(raw_rows_in_one_trace())
    assert len(problems) == 1
    assert "168 bars on 7 categories" in problems[0]


def test_a_trace_per_colour_reports_every_trace():
    problems = bar_repeats(raw_rows_in_a_trace_per_colour())
    assert len(problems) == 7
    assert "'Mon'" in problems[0] and "24 bars on 1 category" in problems[0]


def test_one_bar_per_category_is_fine():
    assert bar_repeats({"data": [{"type": "bar", "x": WEEKDAYS, "y": list(range(7))}]}) == []


def test_a_category_repeated_with_the_same_value_still_stacks():
    assert len(bar_repeats({"data": [{"type": "bar", "x": ["a", "a"], "y": [1, 1]}]})) == 1


def test_numeric_categories_count_too():
    assert len(bar_repeats({"data": [{"type": "bar", "x": [0, 0, 1], "y": [1, 2, 3]}]})) == 1


def test_horizontal_bars_use_y_as_the_category():
    figure = {"data": [{"type": "bar", "orientation": "h", "x": [1, 1, 2], "y": ["a", "b", "c"]}]}
    assert bar_repeats(figure) == []
    figure["data"][0]["y"] = ["a", "a", "c"]
    assert len(bar_repeats(figure)) == 1


def test_timelines_and_histograms_are_left_out():
    timeline = {"data": [{"type": "bar", "orientation": "h", "base": ["2024-01-01", "2024-02-01"],
                          "x": [1, 2], "y": ["task", "task"]}]}
    histogram = {"data": [{"type": "histogram", "x": ["a", "a", "b"]}]}
    assert bar_repeats(timeline) == []
    assert bar_repeats(histogram) == []


def test_unreadable_traces_are_skipped():
    assert bar_repeats({"data": [{"type": "bar", "y": [1, 2]}, {"type": "bar", "x": ["a"], "y": [1, 2]}]}) == []
    assert bar_repeats({}) == []


def test_it_counts_but_never_sends_a_chart_back():
    # Measured, not enforced: a repair in either arm would hide what the A/B measures.
    assert figure_problems(raw_rows_in_one_trace()) == []
