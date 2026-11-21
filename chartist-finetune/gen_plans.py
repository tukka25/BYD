#!/usr/bin/env python3
"""Analyst and planner examples written by Claude Opus 5.5.

Planning is the reasoning-heavy step, where a 9B is furthest behind Opus, so
it is where copying Opus pays most. Opus gets the EXACT production prompts
(planning_contract via contract.py): stage A the analyst prompt, stage B the
planner prompt built from Opus's own checked directions. Only replies with zero
check errors and at least three items become training rows. Train-split
schemas only. Refused requests are dropped and counted: Batches reject the
server-side fallback, and an answer from another model would not be Opus's.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import pandas as pd

import client
from contract import (ANALYST_SYSTEM_PROMPT, ANALYST_USER_TEMPLATE, DIRECTIONS_SCHEMA, NO_REQUEST,
                      PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE, SPECS_SCHEMA, check_directions,
                      check_specs, columns_by_table, profile_table, render_directions, render_profiles)

MIN_ITEMS = 3
CHUNK = 60


def keep_directions(items: list, errors: list) -> bool:
    return len(items) >= MIN_ITEMS and not errors


def keep_charts(items: list, errors: list) -> bool:
    return len(items) >= MIN_ITEMS and not errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="20 for the pilot")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--est-cost", type=float, default=None, help="USD per Opus request, from the pilot")
    ap.add_argument("--max-spend", type=float, default=22.00)
    ap.add_argument("--out", default="data/v2/plans.jsonl")
    ap.add_argument("--seed", type=int, default=20261121)
    ap.add_argument("--chunk", type=int, default=CHUNK, help="requests per batch pair")
    args = ap.parse_args()

    schemas = {
        r["schema_id"]: r
        for r in (json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)
    }
    rows = [json.loads(l) for l in Path("data/v2/requests.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r["split"] == "train"]
    if any(schemas[r["schema_id"]]["split"] != "train" for r in rows):
        raise SystemExit("a test-split schema reached the training requests")
    random.Random(args.seed).shuffle(rows)
    out = Path(args.out)
    done = (
        {json.loads(l)["request_id"] for l in out.read_text(encoding="utf-8").splitlines() if l.strip()}
        if out.exists() else set()
    )
    rows = [r for r in rows if r["request_id"] not in done]
    if args.limit:
        rows = rows[: args.limit]
    print(f"{len(rows)} requests to plan ({len(done)} already done)")

    spent_here = 0.0

    def batch(requests: list, label: str):
        nonlocal spent_here
        planned = ((args.est_cost * len(requests)) if args.est_cost
                   else client.worst_case_cost(client.OPUS, len(requests), 3000, 16000))
        if spent_here + planned > args.max_spend:
            raise SystemExit(f"stopping: ${spent_here:.2f} + ${planned:.2f} would pass --max-spend ${args.max_spend:.2f}")
        client.guard(label, planned)
        result = client.run_batch(requests, label=label)
        spent_here += client.record_spend(label, client.OPUS, result.usage, {"phase": "v2", "requests": len(requests)})
        print(f"[{label}] refusals {result.refusals}, unparsed {result.unparsed}, errored {result.errored}")
        return result

    kept = 0
    for start in range(0, len(rows), args.chunk):
        chunk = rows[start:start + args.chunk]
        profiles = {r["request_id"]: profile_table(schemas[r["schema_id"]]["table_name"],
                                                   pd.read_csv(schemas[r["schema_id"]]["fixture_csv"]))
                    for r in chunk}
        analyst = batch([client.json_request(r["request_id"], client.OPUS, ANALYST_SYSTEM_PROMPT,
                                             ANALYST_USER_TEMPLATE.format(
                                                 request=r["request"] or NO_REQUEST,
                                                 profiles=render_profiles([profiles[r["request_id"]]])),
                                             DIRECTIONS_SCHEMA, max_tokens=16000, effort=args.effort)
                         for r in chunk], "v2-plans-analyst")
        good = {}
        for r in chunk:
            items, errors = check_directions(analyst.payloads.get(r["request_id"]),
                                             columns_by_table([profiles[r["request_id"]]]))
            if keep_directions(items, errors):
                good[r["request_id"]] = items
        planner = batch([client.json_request(rid, client.OPUS, PLANNER_SYSTEM_PROMPT,
                                             PLANNER_USER_TEMPLATE.format(
                                                 profiles=render_profiles([profiles[rid]]),
                                                 directions=render_directions(items)),
                                             SPECS_SCHEMA, max_tokens=16000, effort=args.effort)
                         for rid, items in good.items()], "v2-plans-planner") if good else None
        with out.open("a", encoding="utf-8") as handle:
            for r in chunk:
                if r["request_id"] not in good or planner is None:
                    continue
                charts, errors = check_specs(planner.payloads.get(r["request_id"]),
                                             columns_by_table([profiles[r["request_id"]]]))
                if not keep_charts(charts, errors):
                    continue
                handle.write(json.dumps({"request_id": r["request_id"], "schema_id": r["schema_id"],
                                         "request": r["request"], "directions": good[r["request_id"]],
                                         "charts": charts}, ensure_ascii=False) + "\n")
                kept += 1
        print(f"  {start + len(chunk)}/{len(rows)}: kept {kept}; analyst ok {len(good)}/{len(chunk)}; "
              f"spent here ${spent_here:.4f}", flush=True)
    print(f"done: {kept} planning examples; v2 spend so far ${client.phase_spend():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
