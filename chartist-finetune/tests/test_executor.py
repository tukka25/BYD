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


def test_stray_print_rejected(csv_path):
    # production json.loads all of stdout, so an extra line would break it
    result = run_candidate("print('hello')\n" + COMPLIANT, csv_path)
    assert result.ok is False and "extra_print" in result.violations


def test_xlsx_input(tmp_path):
    import pandas as pd

    path = tmp_path / "data.xlsx"
    pd.DataFrame({"Category": ["A", "B"], "Value": [1, 2]}).to_excel(path, index=False)
    result = run_candidate(COMPLIANT, str(path))
    assert result.ok is True


def test_css_colour_and_hex_are_not_columns(csv_path):
    code = (
        "import plotly.graph_objects as go\n"
        "fig = go.Figure(go.Scatter(x=df['Category'], y=df['Value'], line=dict(color='blue'),"
        " marker=dict(color='#ff0000')))\n"
        "print(fig.to_json())\n"
    )
    result = run_candidate(code, csv_path)
    assert result.ok is True
    assert result.unknown_columns == []


def test_wrong_column_still_caught_next_to_colour(csv_path):
    code = (
        "import plotly.express as px\n"
        "fig = px.bar(df, x='Category', y='Revenue', color='red')\n"
        "print(fig.to_json())\n"
    )
    assert run_candidate(code, csv_path).unknown_columns == ["Revenue"]


def test_derived_column_is_not_rejected(csv_path):
    code = (
        "import plotly.express as px\n"
        "g = df.groupby('Category').size().reset_index(name='n')\n"
        "fig = px.bar(g, x='Category', y='n')\n"
        "print(fig.to_json())\n"
    )
    result = run_candidate(code, csv_path)
    assert result.ok is True and result.failure_kind is None


def test_hallucinated_column_fails_at_execution(csv_path):
    code = (
        "import plotly.express as px\n"
        "fig = px.bar(df, x='Category', y='Nope')\n"
        "print(fig.to_json())\n"
    )
    result = run_candidate(code, csv_path)
    assert result.ok is False and result.failure_kind == "hallucinated_column"


def _printing(payload: str) -> str:
    """Contract-compliant code whose to_json() emits an arbitrary payload."""
    return (
        "class F:\n"
        f"    def to_json(self):\n        return {payload!r}\n"
        "fig = F()\nprint(fig.to_json())\n"
    )


@pytest.mark.parametrize("printed", ["5", "[1, 2]", "null", '"text"'])
def test_non_object_json_is_bad_output_not_a_crash(csv_path, printed):
    result = run_candidate(_printing(printed), csv_path)
    assert result.ok is False and result.failure_kind == "bad_output"


def test_empty_figure_and_unreadable_csv_have_failure_kind(csv_path, tmp_path):
    empty = run_candidate(_printing('{"data": []}'), csv_path)
    assert empty.ok is False and empty.failure_kind == "no_figure"
    missing = run_candidate(COMPLIANT, str(tmp_path / "nope.csv"))
    assert missing.ok is False and missing.failure_kind == "unreadable_input"


def test_run_candidates_survives_a_crashing_job(csv_path):
    from executor import run_candidates

    jobs = [(COMPLIANT, csv_path), (_printing("5"), csv_path),
            (COMPLIANT, csv_path), (_printing("null"), csv_path)]
    results = run_candidates(jobs)
    assert [r.ok for r in results] == [True, False, True, False]
    assert [r.failure_kind for r in results] == [None, "bad_output", None, "bad_output"]


def test_non_utf8_stdout_returns_verdict(csv_path):
    code = _printing("{}").replace("print(fig.to_json())", "import sys; sys.stdout.buffer.write(b'\\xff\\xfe\\n')")
    code += "\nprint(fig.to_json())\n"
    result = run_candidate(code, csv_path)
    assert result.ok is False


def test_huge_integer_stdout_returns_verdict(csv_path):
    result = run_candidate(_printing("9" * 10000), csv_path)
    assert result.ok is False and result.failure_kind == "bad_output"


def test_deeply_nested_json_returns_verdict(csv_path):
    result = run_candidate(_printing("[" * 100000 + "]" * 100000), csv_path)
    assert result.ok is False


def test_surrogate_in_code_returns_verdict(csv_path):
    result = run_candidate(COMPLIANT + "# \ud800\n", csv_path)
    assert result.ok is False and result.failure_kind == "runtime_error"


def test_subprocess_oserror_returns_verdict(csv_path, monkeypatch):
    import executor

    def boom(*a, **k):
        raise OSError("fork failed")

    monkeypatch.setattr(executor.subprocess, "run", boom)
    result = run_candidate(COMPLIANT, csv_path)
    assert result.ok is False and result.failure_kind == "runtime_error" and "OSError" in result.error


@pytest.mark.parametrize("payload", ['{"data": "abc"}', '{"data": [[1]]}', '{"data": [null]}', '{"data": 5}', "{}"])
def test_garbage_figure_is_not_a_render(csv_path, payload):
    result = run_candidate(_printing(payload), csv_path)
    assert result.ok is False and result.failure_kind in {"bad_output", "no_figure"}
    assert result.figure_type is None


def test_untyped_dict_trace_defaults_to_scatter(csv_path):
    result = run_candidate(_printing('{"data": [{"x": [1]}]}'), csv_path)
    assert result.ok is True and result.figure_type == "scatter"


def test_run_candidates_full_length_with_raising_job(csv_path, tmp_path):
    from executor import run_candidates

    jobs = [(COMPLIANT, csv_path), (COMPLIANT + "# \ud800\n", csv_path),
            (_printing("5"), csv_path), (COMPLIANT, csv_path)]
    results = run_candidates(jobs)
    assert len(results) == 4
    assert [r.ok for r in results] == [True, False, False, True]
