import pytest

from executor import run_candidate

COMPLIANT = (
    "import plotly.express as px\n"
    "fig = px.bar(df, x='Category', y='Value')\n"
    "print(fig.to_json())\n"
)


@pytest.fixture()
def csv_path(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("Category,Value\nA,10\nB,20\n", encoding="utf-8")
    return str(path)


def test_compliant_code_runs(csv_path):
    result = run_candidate(COMPLIANT, csv_path)
    assert result.ok is True
    assert result.figure_type == "bar"
    assert result.violations == []


def test_static_violation_short_circuits(csv_path):
    result = run_candidate(COMPLIANT.replace("print(fig.to_json())", "fig.show()"), csv_path)
    assert result.ok is False
    assert "calls_fig_show" in result.violations


def test_hallucinated_columns_reported(csv_path):
    code = (
        "import plotly.express as px\n"
        "fig = px.bar(df, x='Region', y='Revenue')\n"
        "print(fig.to_json())\n"
    )
    result = run_candidate(code, csv_path)
    assert result.ok is False
    assert set(result.unknown_columns) == {"Region", "Revenue"}


def test_runtime_error_captured(csv_path):
    code = COMPLIANT.replace("print(", "raise ValueError('boom')\nprint(")
    result = run_candidate(code, csv_path)
    assert result.ok is False
    assert "boom" in (result.error or "")


def test_timeout_captured(csv_path):
    # Must pass the static check, or the subprocess never starts.
    code = "while True:\n    pass\n" + COMPLIANT
    result = run_candidate(code, csv_path, timeout_seconds=3)
    assert result.ok is False
    assert "timed out" in (result.error or "").lower()


def test_empty_figure_is_rejected(csv_path):
    code = "import plotly.graph_objects as go\nfig = go.Figure()\nprint(fig.to_json())\n"
    result = run_candidate(code, csv_path)
    assert result.ok is False
    assert result.error


def test_title_text_is_not_a_column(csv_path):
    code = (
        "import plotly.express as px\n"
        "fig = px.bar(df, x='Category', y='Value', title='Sales by region')\n"
        "fig.update_xaxes(title_text='Product category')\n"
        "print(fig.to_json())\n"
    )
    result = run_candidate(code, csv_path)
    assert result.ok is True
    assert result.unknown_columns == []


def test_subscript_hallucination_caught(csv_path):
    code = (
        "import plotly.express as px\n"
        "fig = px.bar(df, x='Category', y=df['Nope'])\n"
        "print(fig.to_json())\n"
    )
    assert run_candidate(code, csv_path).unknown_columns == ["Nope"]


def test_stray_print_tolerated(csv_path):
    result = run_candidate("print('hello')\n" + COMPLIANT, csv_path)
    assert result.ok is True


def test_xlsx_input(tmp_path):
    import pandas as pd

    path = tmp_path / "data.xlsx"
    pd.DataFrame({"Category": ["A", "B"], "Value": [1, 2]}).to_excel(path, index=False)
    result = run_candidate(COMPLIANT, str(path))
    assert result.ok is True
