"""Ask the model for one example of each chart kind, for the chart kinds panel.

Every example is the model's own chart, made through the same path a user's
"/kind" request takes (run_kind_request), on a seeded sample file. A kind the
model cannot draw is left out, and the panel says so; nothing stands in.

    docker exec -i promptdash-api python /app/scripts/make_chart_kind_examples.py > byd-web/public/chart-kinds/examples.json
"""
import json
import logging
import sys

sys.path.insert(0, "/app")
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)  # stdout is the JSON

from app.core.config import get_settings  # noqa: E402
from app.services.agents.chart_kinds import chart_kinds  # noqa: E402
from app.services.agents.kind_request import run_kind_request  # noqa: E402
from app.services.agents.workflow import _agents  # noqa: E402
from app.services.llm import get_llm  # noqa: E402
from app.utils.figure_json import decode_typed_arrays  # noqa: E402

MAX_FIGURE_CHARS = 150_000  # a thumbnail; a bigger figure would slow the panel for nothing
settings = get_settings()
source = {"id": "ecommerce_orders.csv", "type": "file", "name": "ecommerce_orders.csv",
          "path": f"{settings.UPLOAD_DIR}/ecommerce_orders.csv"}
planner, chartist = get_llm("spec_planner"), _agents()[2]
examples = []
for kind in chart_kinds():
    result = run_kind_request(f"Show this data as a {kind['label'].lower()}", kind["kind"], [source], source["id"],
                              planner, chartist, settings.UPLOAD_DIR)
    figure = (result.get("execution_result") or {}).get("figure")
    if not figure:
        print(f"[examples] no {kind['kind']}: {result.get('error')}", file=sys.stderr)
        continue
    figure = decode_typed_arrays(figure)
    if len(json.dumps(figure)) > MAX_FIGURE_CHARS:
        print(f"[examples] {kind['kind']} is too large for a thumbnail; left out", file=sys.stderr)
        continue
    print(f"[examples] {kind['kind']}: {result['spec']['title']}", file=sys.stderr)
    examples.append({"kind": kind["kind"], "title": result["spec"]["title"], "figure": figure})
print(json.dumps(examples))
