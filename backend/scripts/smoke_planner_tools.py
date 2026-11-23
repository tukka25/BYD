"""One dashboard plan with the tool step, against the live model. Saves nothing.

    docker exec -i promptdash-api python /app/scripts/smoke_planner_tools.py <report id> "<brief>"
"""
import sys
import time

sys.path.insert(0, "/app")
from app.api.v1.endpoints.blocks import _agents, _report_memory, _user_sources  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.dashboard import Dashboard  # noqa: E402
from app.services.agents.dashboard_flow import build_dashboard  # noqa: E402
from app.services.llm import get_llm  # noqa: E402

report_id, brief = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")
db = SessionLocal()
report = db.get(Dashboard, report_id)
flow = build_dashboard(brief, _user_sources(db, report), get_settings().UPLOAD_DIR, get_llm("analyst"),
                       get_llm("spec_planner"), _agents()[2], explorer_llm=get_llm("explorer"),
                       memory=_report_memory(db, report_id))
started = time.perf_counter()
for event in flow:
    t = time.perf_counter() - started
    if event.kind == "status":
        print(f"[{t:6.1f}s] {event.data['label']}", flush=True)
    elif event.kind == "plan":
        print(f"[{t:6.1f}s] facts: {event.data['facts']}", flush=True)
        print(f"          tries {event.data['attempts']}, dropped {event.data['dropped']}", flush=True)
        for item in event.data["placed"]:
            s = item.spec
            print(f"          {s['chart']:9s} {s['title']!r} x={s['x']} y={s['y']} agg={s['agg']} top_n={s['top_n']}", flush=True)
        break  # planning is what this checks; drawing is make smoke's job
    elif event.kind == "error":
        print(f"[{t:6.1f}s] ERROR {event.data['detail']}", flush=True)
        break
