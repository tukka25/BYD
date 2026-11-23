"""The dashboard endpoint: the kinds picked with "/" reach the build, and a kind
the plan still lacks reaches the client in the plan event."""
import asyncio
import json
from types import SimpleNamespace

from app.api.v1.endpoints import blocks
from app.api.v1.endpoints.blocks import DashboardBriefRequest
from app.services.agents.dashboard_flow import Event

SOURCE = {"id": "s1", "type": "file", "name": "saas.csv", "path": "saas.csv"}
PLACED = SimpleNamespace(spec={"title": "Churn by country", "question": "q", "chart": "bar"}, x=0, y=3, w=6, h=9)


class NoDb:
    """Enough of a session for the intro block: nothing is stored."""

    def add(self, row):
        pass

    def commit(self):
        pass

    def refresh(self, row):
        row.id = "b1"

    def rollback(self):
        pass


def _fake_build(seen):
    """Stands in for dashboard_flow.build_dashboard: records what it was given, at call time."""
    def build_dashboard(*args, **kwargs):
        seen.update(kwargs)
        return iter([Event("plan", {"intro": {"text": "<p>About</p>", "x": 0, "y": 0, "w": 12, "h": 3},
                                    "placed": [PLACED], "tables": [SimpleNamespace(label="saas.csv")],
                                    "attempts": {"analyst": 1, "planner": 3}, "dropped": [], "facts": [],
                                    "missing_kinds": ["pie"]})])
    return build_dashboard


def _wire(monkeypatch, seen):
    """Everything around the build replaced: no database, no model, no files."""
    monkeypatch.setattr(blocks, "build_dashboard", _fake_build(seen))
    monkeypatch.setattr(blocks, "_owned_report", lambda db, dashboard_id, user: SimpleNamespace(id=dashboard_id))
    monkeypatch.setattr(blocks, "_user_sources", lambda db, report: [SOURCE])
    monkeypatch.setattr(blocks, "_report_memory", lambda db, report_id: "")
    monkeypatch.setattr(blocks, "_record_request", lambda *args: None)
    monkeypatch.setattr(blocks, "_next_row", lambda db, report_id: 0)
    monkeypatch.setattr(blocks, "get_llm", lambda role: role)
    monkeypatch.setattr(blocks, "_agents", lambda: (None, None, "chartist", None))
    monkeypatch.setattr(blocks.settings, "DASHBOARD_PLANNER", "ai")


def _start(payload):
    async def run():
        return await blocks.generate_whole_dashboard("r1", payload, current_user=SimpleNamespace(id="u1"), db=NoDb())
    return asyncio.run(run())


def _events(response):
    async def drain():
        return [chunk async for chunk in response.body_iterator]
    out = []
    for chunk in asyncio.run(drain()):
        fields = dict(line.split(": ", 1) for line in chunk.strip().splitlines())
        out.append((fields["event"], json.loads(fields["data"])))
    return out


def test_picked_kinds_reach_the_build_and_a_missing_one_reaches_the_client(monkeypatch):
    seen = {}
    _wire(monkeypatch, seen)
    events = _events(_start(DashboardBriefRequest(brief="churn", chart_kinds=["pie"])))
    assert seen["required_kinds"] == ("pie",)
    assert [name for name, _ in events] == ["plan", "block", "done"]
    assert events[0][1]["missing_kinds"] == ["pie"]
