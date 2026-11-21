"""Run the AI dashboard flow on one file against the real model server.

No database and no web server: it drives agents/dashboard_flow.build_dashboard
with the same LLM roles the endpoint uses and prints what happens.

    cd backend && LLM_BACKEND=mlx MLX_BASE_URL=http://127.0.0.1:8080/v1 \
      PYTHONPATH=. .venv/bin/python scripts/smoke_dashboard_flow.py PATH.csv "brief"
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from app.services.agents.dashboard_flow import build_dashboard
from app.services.agents.workflow import _agents
from app.services.llm import get_llm


def main() -> int:
    path, brief = Path(sys.argv[1]).resolve(), (sys.argv[2] if len(sys.argv) > 2 else "")
    source = {"type": "file", "name": path.name, "path": str(path)}
    started = time.perf_counter()
    rendered = 0
    for event in build_dashboard(brief, [source], str(path.parent),
                                 get_llm("analyst"), get_llm("spec_planner"), _agents()[2]):
        elapsed = time.perf_counter() - started
        if event.kind == "plan":
            print(f"[{elapsed:5.1f}s] plan (tries {event.data['attempts']}; dropped {event.data['dropped']}):")
            for p in event.data["placed"]:
                s = p.spec
                print(f"    {s['chart']:<9} {s['title']!r} x={s['x']!r} y={s['y']!r} group={s['group']!r} "
                      f"agg={s['agg']} grain={s['grain']!r} at ({p.x},{p.y},{p.w}x{p.h})")
        elif event.kind == "chart":
            rendered += 1
            code = event.data["result"]["code"]
            note = " (backup chart)" if "deterministic fallback" in code else ""
            print(f"[{elapsed:5.1f}s] drew {event.data['placed'].spec['title']!r}{note}")
        elif event.kind == "skipped":
            print(f"[{elapsed:5.1f}s] skipped {event.data['placed'].spec['title']!r}: {event.data['reason'][:120]}")
        else:
            print(f"[{elapsed:5.1f}s] {event.kind}: {event.data}")
    print(f"rendered {rendered} charts in {time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
