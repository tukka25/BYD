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
