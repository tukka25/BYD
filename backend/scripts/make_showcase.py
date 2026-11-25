#!/usr/bin/env python3
"""Build one of the landing page's dashboards with the running app, and export it unedited.

The dashboard is built the way a person builds one: a new, empty report with its
sources, then the prompt sent as the dashboard brief to
POST /api/v1/dashboard/{id}/blocks/dashboard, the endpoint behind the app's
"Build it". The blocks the app saved are exported as it stored them; nothing here
edits a chart. When a dashboard falls short, build it again from a rephrased
--prompt, and count the prompts tried with --tries.

Needs `make up`, `make serve-model`, the files from fetch_showcase_data.py, and
SHOWCASE_PASSWORD in the environment: the password of this script's own local
account (any value; keep it for reruns). Run from the repository root.
`make showcase NAME=...` passes the database login from the postgres container
without printing it.

    SHOWCASE_PASSWORD=... make showcase NAME=airbnb
    SHOWCASE_PASSWORD=... make showcase NAME=airbnb SHOWCASE_PROMPT="..." SHOWCASE_TRIES=2
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

MAX_BYTES = 1_500_000
BRIEF_LIMIT = 400  # DashboardBriefRequest.brief in blocks.py
EMAIL = "showcase@example.com"
UPLOADS = Path("backend/uploads/showcase")
LORA_V2 = "runs/adapters-mlx-v2"
BLOCK_KEYS = ("kind", "title", "chart_type", "figure", "text_body", "code", "x", "y", "w", "h")

SHOWCASES: dict[str, dict[str, Any]] = {
    "airbnb": {
        "title": "Airbnb in Edinburgh",
        "prompt": "thinking of renting out my flat in edinburgh on airbnb. which areas charge the most, "
                  "entire place vs private room, and when are guests busiest?",
        "files": ["listings.xlsx", "reviews.csv"],
        "currency": "GBP",  # Inside Airbnb states prices in local currency
    },
    "shop": {
        "title": "A demo shop",
        "prompt": "how is my shop doing? revenue by month, which product categories sell best, "
                  "and which customer regions spend the most",
        "database": {"display_name": "Shop demo", "db_name": "shop", "tables": ["orders", "customers", "products", "visits"]},
        "source": {"url": "https://github.com/tukka25/BYD/blob/main/backend/scripts/make_relational_demo.py",
                   "licence": "synthetic, made for this project", "licence_url": "",
                   "note": "Seeded by backend/scripts/make_relational_demo.py: four tables, joined by their declared keys."},
        "currency": "",
    },
    "netflix": {
        "title": "The Netflix catalogue",
        "prompt": "how has netflix changed over the years? movies vs tv shows, which countries make the most "
                  "content, and the most common ratings",
        "files": ["netflix_titles.csv"],
        "currency": "",
    },
}


# --- pure parts -------------------------------------------------------------

def parse_sse(lines: Iterable[bytes | str]) -> Iterator[tuple[str, dict]]:
    """Server-sent events as (event, data) pairs. The app sends one data line per event."""
    event, data = "message", []
    for raw in lines:
        line = (raw.decode("utf-8") if isinstance(raw, bytes) else raw).rstrip("\r\n")
        if not line:
            if data:
                yield event, json.loads("\n".join(data))
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:"):].lstrip())
    if data:
        yield event, json.loads("\n".join(data))


def summarize_build(events: list[tuple[str, dict]]) -> dict:
    """What the build planned and skipped. The plan's total counts the intro text block."""
    plan = next((data for name, data in events if name == "plan"), None)
    if plan is None:
        errors = [data for name, data in events if name == "error"]
        raise RuntimeError(f"the build made no plan: {errors or events[-1:]}")
    return {
        "charts_planned": int(plan["total"]) - 1,
        "skipped": [{"label": data["label"], "reason": data["reason"]} for name, data in events if name == "skipped"],
        "missing_kinds": list(plan.get("missing_kinds") or []),
    }


def export_block(block: dict) -> dict:
    """A saved block as the page needs it, unchanged."""
    return {key: block.get(key) for key in BLOCK_KEYS}


def served_model(ps_output: str) -> dict | None:
    """The running mlx_lm server's --model and --adapter-path, from `ps -axo command`."""
    for line in ps_output.splitlines():
        if re.search(r"mlx_lm[. ]server", line):
            model = re.search(r"--model\s+(\S+)", line)
            adapter = re.search(r"--adapter-path\s+(\S+)", line)
            return {"base": model.group(1) if model else "unknown", "adapter": adapter.group(1) if adapter else "none"}
    return None


def model_record(model: dict) -> dict:
    """The model behind the dashboard. The page says lora-v2 only when the server ran it."""
    return {**model, "label": "lora-v2" if model["adapter"] == LORA_V2 else model["adapter"]}


def multipart(field: str, filename: str, content: bytes) -> tuple[bytes, str]:
    """A multipart/form-data body with one file, and its Content-Type."""
    boundary = uuid.uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    return head + content + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def write_dashboard(path: Path, dashboard: dict, limit: int = MAX_BYTES) -> int:
    """Write compact JSON through a temporary file, so a failed run leaves no partial file.

    A file over the limit is refused, naming its largest block: change the
    prompt, never the figure."""
    text = json.dumps(dashboard, separators=(",", ":"), ensure_ascii=False)
    size = len(text.encode("utf-8"))
    if size > limit:
        largest = max(dashboard["blocks"], key=lambda block: len(json.dumps(block)))
        raise ValueError(
            f"{path.name} would be {size:,} bytes, over {limit:,}. Its largest block is {largest['title']!r} "
            f"({len(json.dumps(largest)):,} bytes): rephrase the prompt."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return size


# --- talking to the app -------------------------------------------------------

def request(method: str, url: str, *, token: str | None = None, body: dict | None = None,
            raw: bytes | None = None, content_type: str | None = None, timeout: float = 60):
    data = json.dumps(body).encode() if body is not None else raw
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    elif content_type:
        req.add_header("Content-Type", content_type)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(req, timeout=timeout)


def call(method: str, url: str, **kwargs) -> Any:
    try:
        with request(method, url, **kwargs) as response:
            return json.loads(response.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {url} -> {exc.code}: {exc.read().decode()[:500]}") from None


def login(api: str, password: str) -> str:
    try:
        call("POST", f"{api}/auth/register",
             body={"email": EMAIL, "full_name": "PromptDash showcase", "password": password})
    except RuntimeError as exc:
        if "-> 409" not in str(exc):
            raise
    return call("POST", f"{api}/auth/login", body={"email": EMAIL, "password": password})["access_token"]


def file_sources(api: str, token: str, names: list[str]) -> tuple[list[str], list[dict]]:
    manifest = {item["file"]: item for item in json.loads((UPLOADS / "manifest.json").read_text(encoding="utf-8"))}
    ids, sources = [], []
    for name in names:
        item = manifest[name]
        content = (UPLOADS / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise RuntimeError(f"{name} changed since it was fetched; run fetch_showcase_data.py again")
        body, content_type = multipart("file", name, content)
        created = call("POST", f"{api}/data-sources/upload", token=token, raw=body,
                       content_type=content_type, timeout=300)
        ids.append(created["id"])
        sources.append({"name": name, "kind": "file", "rows": item["rows"], "url": item["url"],
                        "licence": item["licence"], "licence_url": item["licence_url"], "note": item["note"]})
    return ids, sources


def count_rows(database: str, table: str, user: str, password: str) -> int:
    import psycopg2
    from psycopg2 import sql

    connection = psycopg2.connect(host="localhost", port=5432, dbname=database, user=user, password=password)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
            return int(cursor.fetchone()[0])
    finally:
        connection.close()


def database_source(api: str, token: str, config: dict) -> tuple[list[str], list[dict]]:
    db = config["database"]
    user, password = os.environ["SHOWCASE_DB_USER"], os.environ["SHOWCASE_DB_PASSWORD"]
    existing = [s for s in call("GET", f"{api}/data-sources", token=token) if s["display_name"] == db["display_name"]]
    if existing:
        source_id = existing[0]["id"]
    else:
        # The api container makes this connection, so the host is the compose service name.
        source_id = call("POST", f"{api}/data-sources/db-connection", token=token, body={
            "display_name": db["display_name"], "db_type": "postgresql",
            "db_host": os.environ.get("SHOWCASE_DB_HOST", "postgres"), "db_port": 5432,
            "db_name": db["db_name"], "db_username": user, "db_password": password,
        })["id"]
    tables = call("GET", f"{api}/data-sources/{source_id}/tables", token=token)
    missing = [table for table in db["tables"] if table not in tables]
    if missing:
        raise RuntimeError(f"the {db['db_name']} database has no {missing}; AGENTS.md says how to rebuild it")
    sources = [{"name": f"{db['db_name']}.{table}", "kind": "database",
                "rows": count_rows(db["db_name"], table, user, password), **config["source"]}
               for table in db["tables"]]
    return [source_id], sources


def build(api: str, token: str, report_id: str, prompt: str) -> tuple[list[tuple[str, dict]], float]:
    started = time.monotonic()
    events: list[tuple[str, dict]] = []
    with request("POST", f"{api}/dashboard/{report_id}/blocks/dashboard", token=token,
                 body={"brief": prompt}, timeout=900) as response:
        for name, data in parse_sse(response):
            events.append((name, data))
            print(f"  [{name}] {data.get('label') or data.get('title') or ''}"[:160], file=sys.stderr)
            if name in ("done", "error"):
                break
    return events, round(time.monotonic() - started, 1)


def app_commit() -> str:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True)
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "backend/app"], capture_output=True, text=True,
                           check=True)
    return head.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build one landing-page dashboard with the running app.")
    parser.add_argument("--name", required=True, choices=sorted(SHOWCASES))
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--prompt", default="", help="a rephrased prompt; the default is the approved one")
    parser.add_argument("--tries", type=int, default=1, help="prompts tried for this dashboard, counting this one")
    parser.add_argument("--out", default="site/data/dashboards")
    args = parser.parse_args()
    config = SHOWCASES[args.name]
    prompt = args.prompt or config["prompt"]
    if len(prompt) > BRIEF_LIMIT:
        print(f"the prompt is {len(prompt)} characters; the brief takes at most {BRIEF_LIMIT}", file=sys.stderr)
        return 2
    password = os.environ.get("SHOWCASE_PASSWORD")
    if not password:
        print("set SHOWCASE_PASSWORD: the password of this script's own local account", file=sys.stderr)
        return 2
    base = args.base.rstrip("/")
    api = f"{base}/api/v1"

    health = call("GET", f"{base}/health")
    model = served_model(subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True, check=True).stdout)
    if model is None:
        print("the model server is not running: make serve-model", file=sys.stderr)
        return 2
    print(f"api: {health.get('llm_backend')}; model server: {model['base']} + {model['adapter']}", file=sys.stderr)

    token = login(api, password)
    ids, sources = (database_source(api, token, config) if "database" in config
                    else file_sources(api, token, config["files"]))
    report = call("POST", f"{api}/dashboard", token=token,
                  body={"title": f"Showcase: {config['title']}", "data_source_ids": ids})
    events, seconds = build(api, token, report["id"], prompt)
    if events and events[-1][0] == "error":
        raise RuntimeError(f"the build failed: {events[-1][1]}")
    record = summarize_build(events)
    saved = call("GET", f"{api}/dashboard/{report['id']}/blocks", token=token)
    blocks = sorted((export_block(block) for block in saved), key=lambda block: (block["y"], block["x"]))
    dashboard = {
        "name": args.name,
        "title": config["title"],
        "prompt": prompt,
        "currency": config["currency"],
        "sources": sources,
        "blocks": blocks,
        "build": {
            "charts_planned": record["charts_planned"],
            "charts_drawn": sum(1 for block in blocks if block["kind"] in ("chart", "metric")),
            "skipped": record["skipped"],
            "missing_kinds": record["missing_kinds"],
            "seconds": seconds,
            "prompts_tried": args.tries,
        },
        "model": model_record(model),
        "app_commit": app_commit(),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path = Path(args.out) / f"{args.name}.json"
    size = write_dashboard(path, dashboard)
    built = dashboard["build"]
    print(f"wrote {path}: {size:,} bytes; {built['charts_drawn']} of {built['charts_planned']} charts drawn "
          f"in {seconds} s; report {report['id']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
