"""How long each planner tool takes as tables grow. Offline: no model, no server.

    cd backend && .venv/bin/python scripts/time_planner_tools.py

Three tables: the web-traffic sample (`make sample-data`), the Spotify CSV
(32,833 rows; AGENTS.md says how to fetch it) and a generated 50,000-row table
with 120 columns. Each table is loaded once; each tool then runs 5 times on it
and the median is printed, in milliseconds.
"""
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.services.agents.architect import spread_sample  # noqa: E402
from app.services.agents.data_tools import PLANNER_TOOL_NAMES, ToolBox  # noqa: E402
from app.services.agents.profiler import profile_table  # noqa: E402

UPLOADS = BACKEND / "uploads"
RUNS = 5


def wide_table(rows: int = 50_000, measures: int = 115) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    columns = {"id": np.arange(1, rows + 1), "region": rng.choice(["North", "South", "East", "West"], rows),
               "segment": rng.choice(["Consumer", "SMB", "Enterprise"], rows),
               "channel": rng.choice(["web", "app", "store"], rows),
               "day": np.repeat(pd.date_range("2023-01-01", periods=500).astype(str), rows // 500)}
    columns.update({f"metric_{i:03d}": rng.normal(100, 15, rows).round(3) for i in range(measures)})
    return pd.DataFrame(columns)


def tool_calls(table: str, kinds: dict[str, str]) -> list[tuple[str, dict]]:
    measure = next(c for c, k in kinds.items() if k == "number")
    category = next(c for c, k in kinds.items() if k == "category")
    plans = [{"chart": "bar", "table": table, "x": category, "y": measure, "agg": "sum"},
             {"chart": "kpi", "table": table, "y": measure, "agg": "mean"},
             {"chart": "histogram", "table": table, "x": measure, "agg": "none"}]
    return [("preview_chart", {"plans": plans}), ("row_grain", {"table": table}),
            ("inspect_column", {"table": table, "column": category}),
            ("find_columns", {"query": measure.split("_")[0]}),
            ("relationship", {"table": table, "a": category, "b": measure})]


def main() -> int:
    tables = {"web_traffic": pd.read_csv(UPLOADS / "web_traffic.csv"),
              "spotify": pd.read_csv(UPLOADS / "spotify_songs.csv"),
              "wide": wide_table()}
    timings: dict[str, dict[str, float]] = {}
    for name, frame in tables.items():
        kinds = profile_table(name, spread_sample(frame, 2000)).kinds()
        box = ToolBox({name: {"type": "file", "name": name}}, "", max_calls=10_000,
                      loader=lambda source, data_dir, f=frame: f, tools=PLANNER_TOOL_NAMES, kinds={name: kinds})
        box.frame(name)  # loaded once, outside the timings
        for tool, args in tool_calls(name, kinds):
            runs = []
            for _ in range(RUNS):
                started = time.perf_counter()
                box.call(tool, args, compact=True)
                runs.append((time.perf_counter() - started) * 1000)
            timings.setdefault(tool, {})[name] = statistics.median(runs)
    shapes = {name: f"{name} {len(f):,}x{len(f.columns)}" for name, f in tables.items()}
    print(f"{'tool':16s}" + "".join(f"{shapes[n]:>26s}" for n in tables))
    for tool, by_table in timings.items():
        print(f"{tool:16s}" + "".join(f"{by_table[n]:>23.1f} ms" for n in tables))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
