"""Live check: does a "/" kind request on a wide table plan the column its question needs?

    docker exec -i promptdash-api python /app/scripts/check_kind_columns.py \
        "<connection name>" "<table>" <kind> "<question>" "<needed column>"

Prints what the one direction lists, the plan the model wrote, and whether the
needed column is in each. The chart goes through the normal path (planner,
checks, chartist, repairs); nothing is saved.
"""
import sys

sys.path.insert(0, "/app")
from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.data_source import DataSource  # noqa: E402
from app.services import db_sources  # noqa: E402
from app.services.agents.dashboard_flow import profile_sources  # noqa: E402
from app.services.agents.kind_request import direction_columns, run_kind_request  # noqa: E402
from app.services.agents.workflow import _agents  # noqa: E402
from app.services.llm import get_llm  # noqa: E402

connection, table, kind, question, needed = sys.argv[1:6]
db = SessionLocal()
row = db.query(DataSource).filter(DataSource.display_name == connection).first()
if row is None:
    sys.exit(f"no connection named {connection!r}")
candidates = db_sources.candidates_for(row)
source = next((c for c in candidates if c["table"] == table), None)
if source is None:
    sys.exit(f"{table!r} is not offered; tables: {', '.join(c['table'] for c in candidates)}")
settings = get_settings()
profile = profile_sources([source], settings.UPLOAD_DIR)[0].profile
listed = direction_columns(question, profile)
print(f"{table}: {len(profile.columns)} columns; the direction lists {len(listed)}: {', '.join(listed)}")
print(f"needed {needed!r} listed: {needed in listed}")
result = run_kind_request(question, kind, candidates, source["id"], get_llm("spec_planner"), _agents()[2],
                          settings.UPLOAD_DIR)
spec = result.get("spec") or {}
print("plan:", {key: spec.get(key) for key in ("chart", "x", "y", "group", "agg", "top_n")})
print(f"needed {needed!r} planned: {needed in (spec.get('x'), spec.get('y'), spec.get('group'))}")
figure = (result.get("execution_result") or {}).get("figure")
print("rendered:", bool(figure) and not result.get("error"), result.get("error") or "")
