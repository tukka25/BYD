"""Subprocess entry point. Reads {"code", "data_path"} as JSON on stdin."""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile


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

    # Run from an empty temp dir so no relative path (../.env) reaches the repo.
    code = compile(job["code"], "<candidate>", "exec")
    workdir = tempfile.mkdtemp(prefix="candidate_")
    try:
        os.chdir(workdir)
        exec(code, {"df": df, "pandas": pd, "pd": pd, "px": px, "go": go, "json": json})
    finally:
        os.chdir(tempfile.gettempdir())
        shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
