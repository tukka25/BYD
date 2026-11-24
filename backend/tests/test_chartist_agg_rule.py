"""The aggregation rule: one instruction appended to the chartist's system prompt
behind CHARTIST_AGG_RULE, off by default because lora-v2 was trained without it.

Every place that sends the chartist's system text must send the same text: the
first call, the repair turn, and the Claude generator on the Compare page.
"""
from types import SimpleNamespace

import pytest

from app.services.agents.chartist import ChartistAgent
from app.services.agents.chartist_contract import (
    AGG_RULE_MODES,
    CHARTIST_AGG_RULE,
    CHARTIST_SYSTEM_PROMPT,
    chartist_system_prompt,
)
from app.services.claude_chartist import ClaudeGenerator

VARIABLES = {"task": "t", "columns": "['a']", "dtypes": "{}", "sample_rows": "[]"}


class Recorder:
    """A stand-in model that remembers what it was sent."""

    def __init__(self):
        self.calls = []

    def invoke(self, variables):
        self.calls.append(variables)
        return "import plotly.express as px\nfig = px.bar(df, x='a', y='a')\nprint(fig.to_json())"


def test_off_is_the_trained_prompt_byte_for_byte():
    assert chartist_system_prompt("off") == CHARTIST_SYSTEM_PROMPT


def test_on_appends_the_rule_and_changes_nothing_before_it():
    on = chartist_system_prompt("on")
    assert on.startswith(CHARTIST_SYSTEM_PROMPT)
    assert on == f"{CHARTIST_SYSTEM_PROMPT}\n{CHARTIST_AGG_RULE}"


def test_the_rule_names_the_plan_markers_and_spares_raw_charts():
    assert "(mean)" in CHARTIST_AGG_RULE and "(sum)" in CHARTIST_AGG_RULE
    assert "with that aggregation" in CHARTIST_AGG_RULE
    assert "Scatter, box and histogram" in CHARTIST_AGG_RULE


def test_an_unknown_mode_is_refused():
    assert AGG_RULE_MODES == ("off", "on")
    with pytest.raises(ValueError):
        chartist_system_prompt("yes")


@pytest.mark.parametrize("mode", ["off", "on"])
def test_first_call_and_repair_turn_send_the_same_system_text(mode):
    agent = ChartistAgent(llm=None, chart_type_hint_style="off", agg_rule=mode)
    first = agent.prompt.format_messages(**VARIABLES)
    repair = agent.repair_prompt.format_messages(**VARIABLES, previous_code="x = 1", problem="p")
    assert first[0].content == chartist_system_prompt(mode)
    assert repair[0].content == chartist_system_prompt(mode)


@pytest.mark.parametrize("mode", ["off", "on"])
def test_a_generator_is_handed_the_agents_system_text(mode):
    model = Recorder()
    agent = ChartistAgent(llm=None, generator=model, chart_type_hint_style="off", agg_rule=mode)
    agent.write(dict(VARIABLES))
    agent.write(dict(VARIABLES), previous_code="x = 1", problem="p")
    assert [call["system"] for call in model.calls] == [chartist_system_prompt(mode)] * 2


def test_the_agent_refuses_an_unknown_mode():
    with pytest.raises(ValueError, match="CHARTIST_AGG_RULE"):
        ChartistAgent(llm=None, generator=Recorder(), chart_type_hint_style="off", agg_rule="yes")


def test_the_agent_takes_the_setting_when_not_told(monkeypatch):
    from app.services.agents import chartist as chartist_module

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(CHARTIST_CHART_TYPE_HINT="off", CHARTIST_AGG_RULE="on"),
    )
    agent = chartist_module.ChartistAgent(llm=None, generator=Recorder())
    assert agent.system_prompt == chartist_system_prompt("on")


class _Stream:
    def __init__(self, sent):
        self.sent = sent

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="code")],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )


def test_the_claude_generator_sends_the_system_text_it_is_handed():
    sent = {}

    def stream(**kwargs):
        sent.update(kwargs)
        return _Stream(sent)

    generator = object.__new__(ClaudeGenerator)
    generator._client = SimpleNamespace(messages=SimpleNamespace(stream=stream))
    generator._effort = "medium"
    generator.last = None
    generator.invoke({**VARIABLES, "system": chartist_system_prompt("on")})
    assert sent["system"] == chartist_system_prompt("on")
