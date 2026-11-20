"""Decode Plotly's binary typed arrays into plain JSON lists.

plotly.py 6+ (this project has 7.1.0) serialises large numeric arrays as

    {"dtype": "f8", "bdata": "<base64>", "shape": "168, 24"}

instead of a list of numbers. That encoding is only understood by plotly.js 3.x
and newer, while the chart HTML this API returns loads plotly.js 2.35.2 from the
CDN — so a chart with any sizeable numeric column rendered **blank in the
browser** even though the figure was completely correct. The backend's own checks
did not catch it, because the figure JSON was valid and full of data; only the
browser could not read it.

Decoding here rather than bumping the CDN keeps the payload readable by any
Plotly version, and does not depend on which plotly.js the page happens to load.
"""
from __future__ import annotations

import base64
from typing import Any

import numpy as np


def _decode_binary_array(node: dict) -> Any:
    """Turn one {dtype, bdata[, shape]} node into a (possibly nested) list."""
    try:
        buffer = base64.b64decode(node["bdata"])
        array = np.frombuffer(buffer, dtype=np.dtype(node["dtype"]))
        shape = node.get("shape")
        if shape:
            dims = [int(part) for part in str(shape).replace(" ", "").split(",") if part]
            if dims:
                array = array.reshape(dims)
        return array.tolist()
    except Exception:
        # A node we cannot decode is better returned untouched than dropped:
        # the chart may still render, and the original is at least inspectable.
        return node


def decode_typed_arrays(value: Any) -> Any:
    """Recursively replace Plotly binary arrays with plain lists."""
    if isinstance(value, dict):
        if isinstance(value.get("bdata"), str) and value.get("dtype"):
            return _decode_binary_array(value)
        return {key: decode_typed_arrays(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_typed_arrays(item) for item in value]
    return value
