from rewrite_docs import (
    ensure_json_print, lift_literals, rename_var, split_data_loading, strip_show,
)


def test_strip_show_removes_only_the_call():
    assert strip_show("fig = px.bar(df)\nfig.show()\n").strip() == "fig = px.bar(df)"


def test_strip_show_handles_arguments():
    assert "show" not in strip_show('fig = px.bar(df)\nfig.show(renderer="png")\n')


def test_strip_show_handles_nested_parens():
    assert "show" not in strip_show("fig = px.bar(df)\nfig.show(config=dict(a=(1, 2)))\n")


def test_ensure_json_print_is_idempotent():
    once = ensure_json_print("fig = px.bar(df)")
    assert once.endswith("print(fig.to_json())")
    assert ensure_json_print(once) == once


def test_split_data_loading_separates_loader_from_chart():
    code = (
        "import pandas as pd\nimport plotly.express as px\n"
        "df = pd.read_csv('https://example.com/x.csv')\n"
        "fig = px.bar(df, x='a', y='b')\nfig.show()\n"
    )
    loader, chart = split_data_loading(code)
    assert "read_csv" in loader and "read_csv" not in chart and "px.bar" in chart


def test_rename_var_and_conflict():
    assert "df" in rename_var("fig = px.bar(data, x='a')", "data")
    assert rename_var("fig = px.bar(df, x=data)", "data") is None


def test_lift_literals_replaces_lists_with_columns():
    out = lift_literals("fig = go.Figure(go.Bar(x=['a', 'b'], y=[1, 2]))")
    assert out is not None
    code, frame = out
    assert list(frame.columns) == ["x", "y"] and "df['x']" in code and "[1, 2]" not in code
