from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def load_config(config_path: str | Path) -> Dict[str, Any]:
    try:
        import yaml
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Missing dependency 'PyYAML'. Install with: python3 -m pip install -r data-pipeline/requirements.txt"
        ) from e

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError("Config file must contain a top-level mapping")
    return cfg


def ensure_dirs(cfg: Dict[str, Any]) -> None:
    work_dir = Path(cfg["paths"]["work_dir"])
    for part in ["01_seed", "02_rephrases", "03_answer_aug", "04_filtered", "05_final"]:
        (work_dir / part).mkdir(parents=True, exist_ok=True)
