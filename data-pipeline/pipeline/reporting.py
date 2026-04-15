from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def write_report(path: str | Path, report: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
