"""Subprocess entry point. Reads {"code", "data_path"} as JSON on stdin."""
from __future__ import annotations

import json
import socket
import sys


def main() -> int:
    job = json.loads(sys.stdin.read())
    import pandas as pd

    path = job["data_path"]
    df = pd.read_excel(path) if path.endswith((".xlsx", ".xls")) else pd.read_csv(path)

    def _deny(*args, **kwargs):
        raise OSError("network disabled")

    socket.socket = _deny  # type: ignore[assignment]
    socket.create_connection = _deny  # type: ignore[assignment]

    import plotly.express as px
    import plotly.graph_objects as go

    exec(
        compile(job["code"], "<candidate>", "exec"),
        {"df": df, "pd": pd, "px": px, "go": go, "json": json},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
