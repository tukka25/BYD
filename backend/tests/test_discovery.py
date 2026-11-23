"""The tool step: the model checks facts before planning, within a budget."""
import pandas as pd
from langchain_core.messages import AIMessage, ToolMessage

from app.services.agents.data_tools import ToolBox
from app.services.agents.discovery import FACTS_CHARS, Findings, Probe, discover
from app.services.agents.profiler import profile_table

TRACKS = pd.DataFrame({"track_name": ["Poison"] * 3 + [f"Song {i}" for i in range(37)],
                       "track_popularity": [10, 20, 30, 40] * 10})
PROFILES = [profile_table("tracks", TRACKS)]


class ToolScripted:
    """A stand-in tool-calling model: replies in order, records what it was sent."""

    def __init__(self, *replies):
        self.replies, self.seen, self.tools = list(replies), [], None

    def bind_tools(self, specs):
        self.tools = specs
        return self

    def invoke(self, messages):
        self.seen.append(list(messages))
        return self.replies.pop(0)


def calls(*items):
    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"c{i}"} for i, (n, a) in enumerate(items)])


def box():
    return ToolBox({"tracks": {"type": "file", "name": "tracks"}}, "", loader=lambda source, data_dir: TRACKS)


def run(gen):
    probes = []
    while True:
        try:
            probes.append(next(gen))
        except StopIteration as done:
            return probes, done.value


def test_the_models_tool_calls_run_and_their_facts_are_kept():
    model = ToolScripted(calls(("inspect_column", {"table": "tracks", "column": "track_name"})), AIMessage(content="DONE"))
    probes, findings = run(discover(model, "most listened songs", PROFILES, box()))
    assert probes == [Probe("inspect_column", {"table": "tracks", "column": "track_name"})]
    assert len(findings.facts) == 1 and "more than one row" in findings.facts[0]
    tool_reply = model.seen[1][-1]
    assert isinstance(tool_reply, ToolMessage) and tool_reply.tool_call_id == "c0"
    assert [t["function"]["name"] for t in model.tools] == ["find_columns", "inspect_column", "relationship", "preview"]


def test_the_step_stops_at_the_budget():
    five = calls(*[("find_columns", {"query": "track"})] * 5)
    model = ToolScripted(five)
    _, findings = run(discover(model, "", PROFILES, box()))
    assert len(findings.calls) == 3 and len(model.seen) == 1
    assert sum(isinstance(m, ToolMessage) for m in model.seen[0]) == 0  # results go after the reply, not before


def test_a_model_without_tool_support_gives_no_facts():
    probes, findings = run(discover(object(), "", PROFILES, box()))
    assert probes == [] and findings.facts == []


def test_a_model_that_answers_without_tools_gives_no_facts():
    _, findings = run(discover(ToolScripted(AIMessage(content="DONE")), "", PROFILES, box()))
    assert findings.facts == [] and findings.note == ""


def test_the_note_is_cut_whole_at_the_limit():
    note = Findings(facts=["x" * 300] * 5).note
    assert len(note) <= FACTS_CHARS and all(line == "- " + "x" * 300 for line in note.splitlines())
