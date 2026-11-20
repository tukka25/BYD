#!/usr/bin/env python3
"""End-to-end check: health, auth, then a real chart from a real CSV.

Proves the whole path rather than any one piece: the API is up, the DB accepted a
user, the token works on the now-authenticated /generate, the detective resolved a
data source, the chartist produced code, and the executor rendered a Plotly figure
with actual data in it.

Uses only the standard library so it adds no dependency.

    python3 scripts/smoke_test.py
    python3 scripts/smoke_test.py --base http://localhost:8000 --prompt "..."
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Any

TIMEOUT = 900


def call(method: str, url: str, body: dict | None = None, token: str | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw
    except urllib.error.URLError as exc:
        return 0, f"unreachable: {exc.reason}"


def fail(step: str, detail: Any) -> int:
    print(f"\n  FAIL at {step}: {str(detail)[:600]}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--email", default="smoke@example.com")
    ap.add_argument("--password", default="smoke-test-password")
    ap.add_argument("--prompt", default="Monthly MRR trend by plan tier")
    ap.add_argument("--data-source", default="")
    args = ap.parse_args()
    api = f"{args.base.rstrip('/')}/api/v1"

    print("1. health")
    status, health = call("GET", f"{args.base.rstrip('/')}/health")
    if status != 200 or not isinstance(health, dict):
        return fail("health", health)
    print(f"   backend={health.get('llm_backend')} model={health.get('model')} url={health.get('llm_url')}")
    uploads = health.get("uploads_present") or []
    print(f"   uploads: {uploads}")
    if not uploads:
        return fail("health", "no CSVs in the upload dir — run `make sample-data`")
    if health.get("insecure_dev_secrets"):
        print("   note: still using this repo's committed placeholder secrets (see `make secrets`)")

    print("2. register (409 is fine, it means the user already exists)")
    status, body = call("POST", f"{api}/auth/register",
                        {"email": args.email, "full_name": "Smoke Test", "password": args.password})
    if status not in (201, 409):
        return fail("register", body)
    print(f"   -> {status}")

    print("3. login")
    status, body = call("POST", f"{api}/auth/login", {"email": args.email, "password": args.password})
    if status != 200 or not isinstance(body, dict) or not body.get("access_token"):
        return fail("login", body)
    token = body["access_token"]
    print(f"   -> token acquired ({len(token)} chars)")

    print("4. /generate WITHOUT a token must be rejected")
    status, _ = call("POST", f"{api}/dashboard/generate", {"prompt": args.prompt})
    if status not in (401, 403):
        return fail("auth check", f"expected 401/403 without a token, got {status}")
    print(f"   -> {status}, correctly refused")

    print(f"5. /generate with a token: {args.prompt!r}")
    status, body = call("POST", f"{api}/dashboard/generate",
                        {"prompt": args.prompt, "data_source": args.data_source, "request_id": "smoke-1"},
                        token=token)
    if status != 200 or not isinstance(body, dict):
        return fail("generate", body)

    html = body.get("dashboard_html") or ""
    meta = body.get("metadata") or {}
    print(f"   model={meta.get('model')} chart={(meta.get('plan') or {}).get('visualization_type')}"
          f" via={(meta.get('plan') or {}).get('chart_type_source')}")
    print(f"   data={(meta.get('data_context') or {}).get('filename')}")
    for step in meta.get("agent_steps") or []:
        print(f"     - {step}")

    if meta.get("used_fallback"):
        return fail(
            "generate",
            "a figure rendered, but from the DETERMINISTIC FALLBACK, not the model. "
            "The chart is real; the model's output was rejected by the contract check. "
            "Most likely MLX_MODEL is not 'default_model', so mlx_lm server served the "
            "base weights without the adapter.\n--- code ---\n" + (meta.get("code") or ""),
        )

    if "No graph generated" in html:
        return fail("generate", f"workflow ran but produced no figure: {html[:300]}")
    match = re.search(r"const fig = (\{.*?\});", html, re.DOTALL)
    if not match:
        return fail("generate", f"no Plotly figure in the response html: {html[:300]}")
    try:
        figure = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        return fail("generate", f"figure json did not parse: {exc}")

    traces = figure.get("data") or []
    if not traces:
        return fail("generate", "figure has no traces")

    # plotly 7 encodes numeric arrays as {"dtype","bdata"}; plotly.js 2.35.2
    # cannot read that, so a chart carrying it renders blank in the browser even
    # though the figure is valid. The backend decodes it, and finding any here
    # means that decoding was skipped.
    def find_binary(node) -> bool:
        if isinstance(node, dict):
            if isinstance(node.get("bdata"), str) and node.get("dtype"):
                return True
            return any(find_binary(v) for v in node.values())
        if isinstance(node, list):
            return any(find_binary(v) for v in node)
        return False

    if find_binary(figure):
        return fail("generate", "figure still contains base64 typed arrays; the browser would render it blank")

    def count(node) -> int:
        """Data points in a trace field, descending into 2D grids like heatmap z."""
        if isinstance(node, list):
            return sum(count(v) for v in node) if node and isinstance(node[0], list) else len(node)
        return 0

    points = sum(
        count(t.get("x")) or count(t.get("labels")) or count(t.get("values")) or count(t.get("z"))
        for t in traces
    )
    kinds = sorted({t.get("type") or "scatter" for t in traces})
    print(f"   figure: {len(traces)} trace(s) {kinds}, ~{points} points")
    print(f"   code was written by the model ({len(meta.get('code') or '')} chars), not the fallback")
    if points == 0:
        return fail("generate", "figure rendered but contains no data points")

    print("\n  PASS — health, auth, source resolution, code generation and execution all worked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
