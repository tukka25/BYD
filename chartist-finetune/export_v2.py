#!/usr/bin/env python3
"""Build the v2 dataset: one adapter, three jobs.

- chartist, question form: the v1 prompt, so single blocks keep working
- chartist, plan form: the same answers with render_spec(plan) as the task
- analyst: profile + request -> directions (Opus)
- planner: profile + directions -> chart plans (Opus)

Every chartist answer passes the contract; every analyst and planner answer
passes the production check with zero errors against its real table. Splits
are by schema, and no row may come from a schema in either frozen test set.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import pandas as pd

from contract import (ANALYST_SYSTEM_PROMPT, ANALYST_USER_TEMPLATE, CHARTIST_SYSTEM_PROMPT, NO_REQUEST,
                      PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE, check_directions, check_specs,
                      columns_by_table, profile_table, render_directions, render_profiles, render_spec,
                      validate_chart_code)

SEP = "\n\nDataFrame `df` schema:"


def spec_prompt(question_prompt: str, spec: dict) -> str:
    head, sep, tail = question_prompt.partition(SEP)
    if not sep:
        raise ValueError("prompt has no schema block")
    return "Task: " + render_spec(spec) + sep + tail


def split_by_schema(rows: list[dict], valid_ratio: float, seed: int) -> dict[str, list]:
    keys = sorted({r["schema_id"] for r in rows})
    random.Random(seed).shuffle(keys)
    valid = set(keys[: max(1, int(len(keys) * valid_ratio))])
    return {"train": [r for r in rows if r["schema_id"] not in valid],
            "valid": [r for r in rows if r["schema_id"] in valid]}


def _jsonl(path: str) -> list[dict]:
    p = Path(path)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="data/mlx_v2")
    ap.add_argument("--valid-ratio", type=float, default=0.12)
    ap.add_argument("--plan-share", type=float, default=0.5, help="share of answers shown in plan form")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    schemas = {r["schema_id"]: r for r in _jsonl("data/schemas.jsonl")}
    frozen = ({r["schema_id"] for r in _jsonl("data/testset.jsonl")}
              | {r["schema_id"] for r in _jsonl("data/v2/planning_testset.jsonl")})
    if not frozen:
        raise SystemExit("no frozen test sets found; refusing to export without a leak check")
    specs = {r["question_id"]: r["spec"] for r in _jsonl("data/v2/target_specs.jsonl")}
    rng = random.Random(args.seed)
    rows: list[dict] = []

    def chartist(row: dict, prompt: str, form: str) -> None:
        rows.append({"schema_id": row["schema_id"], "row_id": f"{row['question_id']}:{form}", "role": "chartist",
                     "form": form, "fixture_csv": row.get("fixture_csv", ""),
                     "messages": [{"role": "system", "content": CHARTIST_SYSTEM_PROMPT},
                                  {"role": "user", "content": prompt},
                                  {"role": "assistant", "content": row["messages"][2]["content"]}]})

    for row in _jsonl("data/targets.jsonl") + _jsonl("data/v2/new_targets.jsonl"):
        spec = row.get("spec") or specs.get(row["question_id"])
        if spec and rng.random() < args.plan_share:
            chartist(row, spec_prompt(row["messages"][1]["content"], spec), "plan")
        else:
            chartist(row, row["messages"][1]["content"], "question")
    for row in _jsonl("data/docs_rows.jsonl"):
        chartist(row, row["messages"][1]["content"], "question")
    for row in _jsonl("data/v2/spec_targets.jsonl"):
        chartist(row, row["messages"][1]["content"], "plan")

    profiles: dict[str, object] = {}
    stale_plans: list[str] = []
    for plan in _jsonl("data/v2/plans.jsonl"):
        schema = schemas[plan["schema_id"]]
        if plan["schema_id"] not in profiles:
            profiles[plan["schema_id"]] = profile_table(schema["table_name"], pd.read_csv(schema["fixture_csv"]))
        profile = profiles[plan["schema_id"]]
        tables = columns_by_table([profile])
        directions, d_err = check_directions({"directions": plan["directions"]}, tables)
        charts, c_err = check_specs({"charts": plan["charts"]}, tables)
        if d_err or c_err:
            # Generated under an older, looser check: dropped whole, so the
            # analyst and planner rows of one example always agree.
            stale_plans.append(f"{plan['request_id']}: {(d_err or c_err)[0]}")
            continue
        text = render_profiles([profile])
        rows.append({"schema_id": plan["schema_id"], "row_id": f"{plan['request_id']}:analyst", "role": "analyst",
                     "form": "analyst", "fixture_csv": schema["fixture_csv"],
                     "messages": [{"role": "system", "content": ANALYST_SYSTEM_PROMPT},
                                  {"role": "user", "content": ANALYST_USER_TEMPLATE.format(
                                      request=plan["request"] or NO_REQUEST, profiles=text)},
                                  {"role": "assistant", "content": json.dumps({"directions": directions},
                                                                              ensure_ascii=False)}]})
        rows.append({"schema_id": plan["schema_id"], "row_id": f"{plan['request_id']}:planner", "role": "planner",
                     "form": "planner", "fixture_csv": schema["fixture_csv"],
                     "messages": [{"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                                  {"role": "user", "content": PLANNER_USER_TEMPLATE.format(
                                      profiles=text, directions=render_directions(directions))},
                                  {"role": "assistant", "content": json.dumps({"charts": charts},
                                                                              ensure_ascii=False)}]})

    if stale_plans:
        print(f"dropped {len(stale_plans)} plans that fail the current checks, e.g. {stale_plans[:3]}")
    leaked = {r["schema_id"] for r in rows} & frozen
    if leaked:
        raise SystemExit(f"LEAK: rows from frozen test schemas: {sorted(leaked)[:5]}")
    bad = [r["row_id"] for r in rows if r["role"] == "chartist" and validate_chart_code(r["messages"][2]["content"])]
    if bad:
        raise SystemExit(f"CONTRACT VIOLATION in {len(bad)} chartist rows: {bad[:10]}")

    splits = split_by_schema(rows, args.valid_ratio, args.seed)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"seed": args.seed, "valid_ratio": args.valid_ratio, "plan_share": args.plan_share,
                "counts": {}, "schema_ids": {}}
    for split, split_rows in splits.items():
        random.Random(args.seed).shuffle(split_rows)
        with (out / f"{split}.jsonl").open("w", encoding="utf-8") as handle:
            for r in split_rows:
                handle.write(json.dumps({"messages": r["messages"]}, ensure_ascii=False) + "\n")
        with (out / f"{split}_fixtures.jsonl").open("w", encoding="utf-8") as handle:
            for r in split_rows:
                handle.write(json.dumps({"schema_id": r["schema_id"], "question_id": r["row_id"],
                                         "fixture_csv": r["fixture_csv"]}) + "\n")
        manifest["counts"][split] = dict(Counter(r["form"] for r in split_rows), total=len(split_rows))
        manifest["schema_ids"][split] = sorted({r["schema_id"] for r in split_rows})
    (out / "split_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
