"""What is already on a report, in a few lines, rebuilt from the database each run.

Runs are stateless: every build is a fresh conversation. This gives the analyst
the report's charts (kind, title, the question each answers) and what the user
asked before, so a second build extends the report instead of repeating it.
Descriptions only: no figure data ever goes into a prompt.
"""
from __future__ import annotations

MAX_CHARTS = 12
MAX_REQUESTS = 5
MEMORY_CHARS = 1000  # about 250 tokens, analyst only


def describe_report(blocks: list[dict], requests: list[dict]) -> str:
    charts = [b for b in blocks if b.get("kind") in ("chart", "metric")][-MAX_CHARTS:]
    asked = [r for r in requests if str(r.get("text") or "").strip()][-MAX_REQUESTS:]

    def render(entries: list[dict]) -> str:
        lines: list[str] = []
        if entries:
            lines.append("Already on this report (do not repeat these; add what is missing):")
            for n, block in enumerate(entries, 1):
                kind = block.get("chart_type") or ("kpi" if block.get("kind") == "metric" else "chart")
                title = str(block.get("title") or "Untitled")
                question = str(block.get("prompt") or "").strip()
                line = f"{n}. {kind} · {title}"
                if question and question != title:
                    line += f" — {question[:120]}"
                lines.append(line)
        if asked:
            lines.append("Asked before: " + "; ".join(
                f"\"{str(r['text']).strip()[:120]}\" ({r.get('kind', 'chart')})" for r in asked))
        return "\n".join(lines)

    text = render(charts)
    while len(text) > MEMORY_CHARS and charts:
        charts = charts[1:]  # the oldest chart goes first
        text = render(charts)
    return text[:MEMORY_CHARS]
