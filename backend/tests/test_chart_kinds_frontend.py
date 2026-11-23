"""The "/" menu and the chart kinds panel offer a fixed list kept in the frontend
(byd-web/lib/chart-kinds.ts). It must be the planner's own list in the same
words, so the UI can never offer a kind the planner rejects (a 422 at the API)."""
import re
from pathlib import Path

from app.services.agents.chart_kinds import KIND_INFO
from app.services.agents.planning_contract import CHART_KINDS

FRONTEND_LIST = Path(__file__).resolve().parents[2] / "byd-web" / "lib" / "chart-kinds.ts"


def _entries() -> list[tuple[str, str]]:
    """(kind, label) for each entry of the frontend's CHART_KINDS, in file order."""
    return re.findall(r'kind:\s*"([^"]+)",\s*label:\s*"([^"]+)"', FRONTEND_LIST.read_text(encoding="utf-8"))


def test_the_frontend_offers_exactly_the_planner_kinds_in_its_order():
    assert [kind for kind, _ in _entries()] == list(CHART_KINDS)


def test_the_frontend_names_each_kind_as_the_backend_does():
    assert [label for _, label in _entries()] == [KIND_INFO[kind]["label"] for kind in CHART_KINDS]
