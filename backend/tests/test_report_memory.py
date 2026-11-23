"""What is already on a report, in a few lines: descriptions, never data."""
from app.services.agents.report_memory import MAX_CHARTS, MEMORY_CHARS, describe_report


def test_charts_and_requests_are_described_and_notes_left_out():
    blocks = [
        {"kind": "chart", "title": "Top tracks", "chart_type": "bar", "prompt": "Which tracks are listened to most?"},
        {"kind": "metric", "title": "Total tracks", "chart_type": "kpi", "prompt": "How many tracks?"},
        {"kind": "text", "title": "Note", "chart_type": None, "prompt": None},
    ]
    requests = [{"kind": "dashboard", "text": "most listened songs"}, {"kind": "chart", "text": "now by genre"}]
    text = describe_report(blocks, requests)
    assert "1. bar · Top tracks — Which tracks are listened to most?" in text
    assert "2. kpi · Total tracks" in text and "Note" not in text
    assert '"most listened songs" (dashboard)' in text and '"now by genre" (chart)' in text


def test_an_empty_report_has_no_memory():
    assert describe_report([], []) == ""


def test_memory_keeps_the_latest_charts_and_stays_short():
    blocks = [{"kind": "chart", "title": f"Chart {i} " + "x" * 80, "chart_type": "bar", "prompt": ""} for i in range(30)]
    text = describe_report(blocks, [])
    assert len(text) <= MEMORY_CHARS and "Chart 29" in text and "Chart 17 " not in text
    assert len([line for line in text.splitlines() if line[:1].isdigit()]) <= MAX_CHARTS
