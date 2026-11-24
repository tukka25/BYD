from app.services.agents.chartist_contract import (
    CHARTIST_SYSTEM_PROMPT,
    CHARTIST_USER_TEMPLATE,
    ContractViolation,
    validate_chart_code,
)

COMPLIANT = (
    "import plotly.express as px\n"
    "fig = px.bar(df, x='Category', y='Value')\n"
    "print(fig.to_json())\n"
)


def test_accepts_compliant_code():
    assert validate_chart_code(COMPLIANT) == []


def test_rejects_fig_show():
    violations = validate_chart_code(COMPLIANT.replace("print(fig.to_json())", "fig.show()"))
    assert ContractViolation.CALLS_SHOW in violations
    assert ContractViolation.NO_JSON_PRINT in violations


def test_rejects_reading_data():
    code = (
        "import pandas as pd\nimport plotly.express as px\n"
        "df = pd.read_csv('https://example.com/d.csv')\n"
        "fig = px.bar(df, x='a', y='b')\nprint(fig.to_json())\n"
    )
    assert ContractViolation.READS_DATA in validate_chart_code(code)


def test_rejects_matplotlib():
    assert ContractViolation.USES_MATPLOTLIB in validate_chart_code(
        "import matplotlib.pyplot as plt\nplt.plot([1,2])\n"
    )


def test_rejects_missing_figure_assignment():
    assert ContractViolation.NO_FIGURE in validate_chart_code(
        "import plotly.express as px\nprint(px.bar(df).to_json())\n"
    )


def test_rejects_syntax_error():
    assert validate_chart_code("fig = (((") == [ContractViolation.SYNTAX_ERROR]


def test_user_template_has_the_schema_fields():
    rendered = CHARTIST_USER_TEMPLATE.format(
        task="t", columns="['a']", dtypes="{'a': 'int64'}", sample_rows="[{'a': 1}]"
    )
    assert "['a']" in rendered and "int64" in rendered


def test_system_prompt_states_the_hard_rules():
    assert "print(fig.to_json())" in CHARTIST_SYSTEM_PROMPT
    lowered = CHARTIST_SYSTEM_PROMPT.lower()
    assert "fig.show" in lowered and "pd.read_csv" in lowered


def _code(body: str) -> str:
    return "import plotly.express as px\n" + body + "fig = px.bar(df, x='a', y='b')\nprint(fig.to_json())\n"


def test_rejects_creating_dataframe():
    code = _code("import pandas as pd\ndf = pd.DataFrame({'a': [1], 'b': [2]})\n")
    assert set(validate_chart_code(code)) == {ContractViolation.CREATES_DATAFRAME}


def test_allows_reassigning_df_by_transformation():
    assert validate_chart_code(_code("df = df.groupby('a', as_index=False)['b'].sum()\n")) == []


def test_rejects_from_pandas_import_read():
    code = _code("from pandas import read_csv\n")
    assert set(validate_chart_code(code)) == {ContractViolation.READS_DATA}


def test_rejects_requests():
    assert set(validate_chart_code(_code("import requests\nr = requests.get('d')\n"))) == {
        ContractViolation.READS_DATA
    }


# The code must end with its one print(fig.to_json()) (7deeaa3), so each write goes before it.
def test_rejects_write_html():
    code = COMPLIANT.replace("print(fig.to_json())", "fig.write_html('x.html')\nprint(fig.to_json())")
    assert set(validate_chart_code(code)) == {ContractViolation.WRITES_FILE}


def test_rejects_to_csv():
    code = _code("df.to_csv('x.csv')\n")
    assert set(validate_chart_code(code)) == {ContractViolation.WRITES_FILE}


def test_a_method_named_open_is_blocked_as_the_executor_blocks_it_but_is_not_reading_data():
    # SafeExecutor rejects any `open(` in the lowercased code at run time, and the contract mirrors
    # it (ac39d4d) so the model hears first. Reading data takes a bare `open(` only.
    assert validate_chart_code(_code("x = obj.open(1)\ny = Open(2)\n")) == [ContractViolation.BLOCKED_IMPORT]


def test_fig_to_json_is_not_a_file_write():
    assert validate_chart_code(COMPLIANT) == []
