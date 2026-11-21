#!/usr/bin/env python3
"""The new dashboard flow, end to end, on the local model.

Same prompts, same checks and the same retry text as the backend
(planning_contract via contract.py), run in-process with mlx so it can batch.
For each frozen planning test row: the analyst proposes directions (checked,
retried twice), the planner writes chart plans (checked, retried twice), and
the chartist draws the first plans, which are executed against the real table.

The planning roles run with thinking off, as backend/app/services/llm.py sends
them; the chartist keeps the server default, as production does.

Reports how often each stage produces something usable, how often a planned
chart renders, and how often the rendered chart is the kind that was planned.
Rows are saved as each batch finishes; rerunning resumes.

    .venv/bin/python measure_planning.py --label lora-v1
    .venv/bin/python measure_planning.py --label lora-v2 --adapter-path runs/adapters-mlx-v2
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

import chart_types
from contract import (
    ANALYST_MAX_TOKENS, ANALYST_SYSTEM_PROMPT, ANALYST_USER_TEMPLATE, CHARTIST_MAX_TOKENS,
    CHARTIST_SYSTEM_PROMPT, CHARTIST_USER_TEMPLATE, FIX_PROMPT, KIND_TRACES, NO_REQUEST,
    PLANNER_MAX_TOKENS, PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE, check_directions,
    check_specs, columns_by_table, extract_json, profile_table, render_directions,
    render_profiles, render_spec,
)
from evaluate import THINK_PREFIX, strip_fence
from executor import run_candidates

MAX_ATTEMPTS = 3


def plan_matches(chart: str, figure_type: str | None, code: str) -> bool:
    if figure_type not in KIND_TRACES.get(chart, set()):
        return False
    if chart == "area":
        return chart_types.is_area_figure(code)
    if chart in ("line", "scatter"):
        return not chart_types.is_area_figure(code)
    return True


def summarize(rows: list[dict]) -> dict:
    n = len(rows) or 1
    with_dirs = [r for r in rows if r["directions"]]
    drawn = [d for r in rows for d in r["drawn"]]
    rendered = [d for d in drawn if d["ok"]]
    return {
        "rows": len(rows),
        "analyst_ok_rate": len(with_dirs) / n,
        "mean_directions": sum(r["directions"] for r in rows) / n,
        "planner_ok_rate": (sum(1 for r in with_dirs if r["charts"]) / len(with_dirs)) if with_dirs else 0.0,
        "mean_charts": (sum(r["charts"] for r in with_dirs) / len(with_dirs)) if with_dirs else 0.0,
        "rows_needing_retries": sum(1 for r in rows if r["analyst_attempts"] > 1 or r["planner_attempts"] > 1) / n,
        "charts_drawn": len(drawn),
        "render_rate": (len(rendered) / len(drawn)) if drawn else 0.0,
        # Of the charts that rendered, how many are the kind that was planned.
        "plan_match_rate": (sum(1 for d in rendered if d["match"]) / len(rendered)) if rendered else 0.0,
        # End to end: rendered AND the planned kind, over every chart attempted.
        "right_chart_rate": (sum(1 for d in drawn if d["match"]) / len(drawn)) if drawn else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--model", default="models/qwen3.5-9b-4bit")
    ap.add_argument("--adapter-path", default="runs/adapters-mlx")
    ap.add_argument("--testset", default="data/v2/planning_testset.jsonl")
    ap.add_argument("--max-charts-per-dashboard", type=int, default=3)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--batch-size", type=int, default=16)
    args = ap.parse_args()

    from mlx_lm import batch_generate, load
    from mlx_lm.sample_utils import make_sampler

    schemas = {
        r["schema_id"]: r
        for r in (json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)
    }
    rows = [json.loads(l) for l in Path(args.testset).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        rows = rows[: args.limit]
    out = Path(f"data/v2/planning_eval_{args.label}.json")
    ckpt = out.with_suffix(".rows.jsonl")
    done = (
        {json.loads(l)["request_id"] for l in ckpt.read_text(encoding="utf-8").splitlines() if l.strip()}
        if ckpt.exists() else set()
    )
    todo = [r for r in rows if r["request_id"] not in done]
    print(f"{len(rows)} planning rows, {len(todo)} to go")

    adapter = None if args.adapter_path in ("none", "") else args.adapter_path
    model, tokenizer = load(args.model, adapter_path=adapter)
    sampler = make_sampler(temp=0.0)

    def tokens(messages: list[dict], thinking: bool) -> list[int]:
        # The planning roles run with thinking off, as llm.py sends them; the
        # chartist keeps the server default, so its prompt is byte-identical.
        extra = {} if thinking else {"enable_thinking": False}
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, **extra)
        if isinstance(ids, dict):
            ids = ids.get("input_ids", [])
        if ids and isinstance(ids[0], (list, tuple)):
            ids = ids[0]
        return list(ids)

    def generate(conversations: list[list[dict]], max_tokens: int, thinking: bool = False) -> list[str]:
        out_texts: list[str] = []
        for start in range(0, len(conversations), args.batch_size):
            chunk = [tokens(c, thinking) for c in conversations[start:start + args.batch_size]]
            resp = batch_generate(model, tokenizer, chunk, max_tokens=max_tokens, sampler=sampler, verbose=False)
            out_texts.extend(THINK_PREFIX.sub("", t, count=1) if "</think>" in t else t for t in resp.texts)
        return out_texts

    def checked(convs: list[list[dict]], check, tables: list[dict], max_tokens: int):
        """The backend's run_checked, batched across rows."""
        best = [([], ["not run"]) for _ in convs]
        attempts = [0] * len(convs)
        live = list(range(len(convs)))
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if not live:
                break
            replies = generate([convs[i] for i in live], max_tokens)
            still = []
            for i, raw in zip(live, replies):
                attempts[i] = attempt
                items, errors = check(extract_json(raw), tables[i])
                better = len(items) > len(best[i][0]) or (
                    len(items) == len(best[i][0]) and len(errors) < len(best[i][1])
                )
                if attempt == 1 or better:
                    best[i] = (items, errors)
                if not (items and not errors):
                    convs[i] = convs[i] + [
                        {"role": "assistant", "content": raw},
                        {"role": "user", "content": FIX_PROMPT.format(errors="\n".join(f"- {e}" for e in errors[:10]))},
                    ]
                    still.append(i)
            live = still
        return best, attempts

    started = time.time()
    for start in range(0, len(todo), args.batch_size * 4):
        batch = todo[start:start + args.batch_size * 4]
        profiles, tables = [], []
        for row in batch:
            schema = schemas[row["schema_id"]]
            profile = profile_table(schema["table_name"], pd.read_csv(schema["fixture_csv"]))
            profiles.append(profile)
            tables.append(columns_by_table([profile]))
        analyst_convs = [
            [{"role": "system", "content": ANALYST_SYSTEM_PROMPT},
             {"role": "user", "content": ANALYST_USER_TEMPLATE.format(
                 request=row["request"] or NO_REQUEST, profiles=render_profiles([p]))}]
            for row, p in zip(batch, profiles)
        ]
        dir_best, dir_attempts = checked(analyst_convs, check_directions, tables, ANALYST_MAX_TOKENS)

        plan_idx = [i for i, (items, _) in enumerate(dir_best) if items]
        planner_convs = [
            [{"role": "system", "content": PLANNER_SYSTEM_PROMPT},
             {"role": "user", "content": PLANNER_USER_TEMPLATE.format(
                 profiles=render_profiles([profiles[i]]), directions=render_directions(dir_best[i][0]))}]
            for i in plan_idx
        ]
        spec_best_list, spec_attempts_list = checked(
            planner_convs, check_specs, [tables[i] for i in plan_idx], PLANNER_MAX_TOKENS
        )
        spec_best = dict(zip(plan_idx, spec_best_list))
        spec_attempts = dict(zip(plan_idx, spec_attempts_list))

        jobs = []  # (row index, spec, conversation)
        for i in plan_idx:
            schema = schemas[batch[i]["schema_id"]]
            for spec in spec_best[i][0][: args.max_charts_per_dashboard]:
                user = CHARTIST_USER_TEMPLATE.format(
                    task=render_spec(spec), columns=schema["pandas_columns"],
                    dtypes=schema["pandas_dtypes"], sample_rows=schema["sample_rows"],
                )
                jobs.append((i, spec, [{"role": "system", "content": CHARTIST_SYSTEM_PROMPT},
                                       {"role": "user", "content": user}]))
        codes = [strip_fence(t) for t in generate([j[2] for j in jobs], CHARTIST_MAX_TOKENS, thinking=True)]
        verdicts = run_candidates(
            [(c, schemas[batch[j[0]]["schema_id"]]["fixture_csv"]) for c, j in zip(codes, jobs)], max_workers=8
        )
        drawn: dict[int, list] = {i: [] for i in range(len(batch))}
        for (i, spec, _), code, verdict in zip(jobs, codes, verdicts):
            drawn[i].append({
                "chart": spec["chart"], "ok": bool(verdict.ok),
                "match": bool(verdict.ok) and plan_matches(spec["chart"], verdict.figure_type, code),
                "figure_type": verdict.figure_type, "error": (verdict.error or "")[:160],
            })

        with ckpt.open("a", encoding="utf-8") as handle:
            for i, row in enumerate(batch):
                specs, spec_errors = spec_best.get(i, ([], []))
                handle.write(json.dumps({
                    "request_id": row["request_id"], "schema_id": row["schema_id"], "request": row["request"],
                    "directions": len(dir_best[i][0]),
                    "direction_errors": len(dir_best[i][1]) if not dir_best[i][0] else 0,
                    "analyst_attempts": dir_attempts[i], "charts": len(specs), "chart_errors": len(spec_errors),
                    "planner_attempts": spec_attempts.get(i, 0), "specs": specs, "drawn": drawn[i],
                }, ensure_ascii=False) + "\n")
        print(f"  {min(start + len(batch), len(todo))}/{len(todo)} rows "
              f"({(time.time() - started) / 60:.1f} min)", flush=True)

    all_rows = [json.loads(l) for l in ckpt.read_text(encoding="utf-8").splitlines() if l.strip()]
    report = {"label": args.label, "adapter": args.adapter_path, "summary": summarize(all_rows)}
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
