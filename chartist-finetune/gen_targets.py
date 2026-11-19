#!/usr/bin/env python3
"""Generate verified code targets with adaptive best-of-k.

Round 1 sends k candidates per question. Every candidate is executed against the
schema's real CSV; a candidate survives only if it runs and yields a trace type in
the requested chart bucket. Questions with no survivor get one extra attempt in round 2.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter
from pathlib import Path

import chart_types
import client
from contract import CHARTIST_SYSTEM_PROMPT, CHARTIST_USER_TEMPLATE
from executor import run_candidates

CODE_SCHEMA = {
    "type": "object",
    "properties": {"code": {"type": "string"}},
    "required": ["code"],
    "additionalProperties": False,
}


def build_prompt(schema: dict, question: dict) -> str:
    return CHARTIST_USER_TEMPLATE.format(
        task=question["question"],
        columns=schema["pandas_columns"],
        dtypes=schema["pandas_dtypes"],
        sample_rows=schema["sample_rows"],
    )


def system_for(question: dict) -> str:
    """Same contract, plus the requested chart shape as a steer."""
    bucket = question["chart_bucket"]
    extra = f"\n\nFor this request, produce a {bucket.replace('_', ' ')} chart."
    if question.get("hard_case") == "missing_field":
        extra += (
            "\nThe request may name something absent from the schema. Do not invent a "
            "column: answer with the closest thing the schema actually provides."
        )
    return CHARTIST_SYSTEM_PROMPT + extra


def verdict(result, question: dict) -> tuple[bool, str | None]:
    if not result.ok:
        if result.violations:
            reason = result.violations[0]
        elif result.failure_kind:
            reason = result.failure_kind
        elif result.figure_type is None:
            reason = "no_figure"
        else:
            reason = "other_rejected"
        return False, reason
    allowed = chart_types.TRACE_TYPES.get(question["chart_bucket"], set())
    if allowed and result.figure_type not in allowed:
        return False, "wrong_chart_type"
    return True, None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None, help="limit questions (pilot)")
    parser.add_argument("--offset", type=int, default=0, help="skip N shuffled questions (stage B)")
    parser.add_argument("--seed", type=int, default=20261119)
    parser.add_argument("--max-spend", type=float, default=14.00)
    args = parser.parse_args()

    schemas = {
        r["schema_id"]: r
        for r in (json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)
    }
    questions = [
        r
        for r in (json.loads(l) for l in Path("data/questions.jsonl").read_text(encoding="utf-8").splitlines() if l)
        if r["split"] == "train"
    ]
    # Seeded shuffle so any slice is a representative sample; same seed => stages partition exactly.
    random.Random(args.seed).shuffle(questions)
    questions = questions[args.offset:]
    if args.limit:
        questions = questions[: args.limit]
    # Never generate against test-split schemas.
    assert all(schemas[q["schema_id"]]["split"] == "train" for q in questions), "test-split schema leaked"
    print(f"train questions: {len(questions)}, k={args.k}")

    index = {q["question_id"]: q for q in questions}
    spend = 0.0
    prior_report: dict = {}
    prior_rows: dict[str, dict] = {}
    if args.offset > 0:
        prior_report = json.loads(Path("runs/targets_report.json").read_text(encoding="utf-8"))
        prior_rows = {
            r["question_id"]: r
            for r in (json.loads(l) for l in Path("data/targets.jsonl").read_text(encoding="utf-8").splitlines() if l)
        }
    prior_spend = prior_report.get("spend_usd", 0.0)
    cap = args.max_spend - prior_spend  # cap is cumulative across stages
    kept: dict[str, dict] = {}
    reasons: Counter[str] = Counter()
    round_stats: dict[str, dict] = {}
    batches: list[dict] = []
    rejected_log: list[dict] = []

    def submit(pending: list[dict], attempt: int) -> None:
        nonlocal spend
        requests = []
        for question in pending:
            schema = schemas[question["schema_id"]]
            effort = "medium" if question.get("hard_case") else "low"
            for candidate in range(args.k if attempt == 1 else 1):
                requests.append(
                    client.json_request(
                        custom_id=f"{question['question_id']}__{attempt}__{candidate}",
                        model=client.SONNET,
                        system=system_for(question),
                        user=build_prompt(schema, question),
                        schema=CODE_SCHEMA,
                        max_tokens=3000,
                        effort=effort,
                    )
                )
        if not requests:
            return
        label = f"targets-a{attempt}"
        outcome = client.run_batch(requests, label=label)
        cost = client.record_spend(label, client.SONNET, outcome.usage, {"requests": len(requests)})
        spend += cost
        stat = {
            "requests": len(requests), "cost_usd": round(cost, 4), "usage": outcome.usage,
            "refusals": outcome.refusals, "unparsed": outcome.unparsed,
            "errored": outcome.errored, "candidates_judged": 0, "candidates_passed": 0,
            "newly_kept": 0, "reasons": Counter(),
        }
        round_stats[label] = stat
        batches.append({"label": label, "batch_id": outcome.batch_id, "cost_usd": round(cost, 4)})

        # Phase 1: collect candidates.
        pending = []
        for custom_id, payload in outcome.payloads.items():
            question_id = custom_id.split("__")[0]
            question = index[question_id]
            code = (payload.get("code") or "").strip()
            stat["candidates_judged"] += 1
            if not code:
                reasons["empty_code"] += 1
                stat["reasons"]["empty_code"] += 1
                continue
            pending.append((custom_id, question_id, question, code,
                            schemas[question["schema_id"]]["fixture_csv"]))

        # Phase 2: execute all candidates concurrently (order preserved).
        t0 = time.time()
        results = run_candidates([(p[3], p[4]) for p in pending], max_workers=8)
        stat["validation_seconds"] = round(time.time() - t0, 1)
        print(f"[{label}] validated {len(pending)} candidates in {stat['validation_seconds']}s", flush=True)

        # Phase 3: judge sequentially, zipping by index.
        for (custom_id, question_id, question, code, fixture), result in zip(pending, results):
            good, reason = verdict(result, question)
            if not good:
                reasons[reason] += 1
                stat["reasons"][reason] += 1
                rejected_log.append({"custom_id": custom_id, "reason": reason,
                                     "error": result.error, "unknown": result.unknown_columns,
                                     "figure_type": result.figure_type, "code": code})
                continue
            stat["candidates_passed"] += 1
            if question_id in kept:
                continue
            stat["newly_kept"] += 1
            kept[question_id] = {
                "schema_id": question["schema_id"],
                "question_id": question_id,
                "messages": [
                    {"role": "system", "content": CHARTIST_SYSTEM_PROMPT},
                    {"role": "user", "content": build_prompt(schemas[question["schema_id"]], question)},
                    {"role": "assistant", "content": code},
                ],
                "fixture_csv": fixture,
                "chart_bucket": question["chart_bucket"],
                "hard_case": question["hard_case"],
                "figure_type": result.figure_type,
                "attempt": int(custom_id.split("__")[1]),
            }

    submit(questions, attempt=1)
    print(f"after round 1: kept {len(kept)}/{len(questions)}, spend ${spend:.4f}")

    retry = [q for q in questions if q["question_id"] not in kept]
    if retry:
        r1 = round_stats.get("targets-a1")
        est = (r1["cost_usd"] / max(1, r1["requests"])) * len(retry) if r1 else 0.0
        if spend + est <= cap:
            print(f"round 2: retrying {len(retry)} questions (est ${est:.4f})")
            submit(retry, attempt=2)
        else:
            print(f"skipping round 2: spend ${spend:.4f} + est ${est:.4f} exceeds remaining cap ${cap:.2f}")

    stage = "B" if args.offset > 0 else "A"
    Path(f"runs/targets_rejected_{stage}.jsonl").write_text(
        "\n".join(json.dumps(r, default=str) for r in rejected_log), encoding="utf-8")

    asked = Counter(q["chart_bucket"] for q in questions)
    for stat in round_stats.values():
        stat["reasons"] = dict(stat["reasons"].most_common())
    stage_rep = {
        "stage": stage, "offset": args.offset, "limit": args.limit, "questions": len(questions),
        "verified": len(kept), "spend_usd": round(spend, 4),
        "asked_by_bucket": dict(asked), "rejection_reasons": dict(reasons),
        "rounds": round_stats, "batches": batches,
        "refusals": sum(s["refusals"] for s in round_stats.values()),
        "validation_seconds": round(sum(s.get("validation_seconds", 0) for s in round_stats.values()), 1),
    }
    all_rows = {**prior_rows, **kept}  # dedupe by question_id
    with Path("data/targets.jsonl").open("w", encoding="utf-8") as handle:
        for row in all_rows.values():
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    stages = prior_report.get("stages", []) + [stage_rep]
    asked_all, reasons_all = Counter(), Counter()
    for s in stages:
        asked_all.update(s["asked_by_bucket"]); reasons_all.update(s["rejection_reasons"])
    got = Counter(r["chart_bucket"] for r in all_rows.values())
    total_q = sum(asked_all.values())
    total_spend = sum(s["spend_usd"] for s in stages)
    report = {
        "train_questions": total_q,
        "verified_targets": len(all_rows),
        "yield": round(len(all_rows) / max(1, total_q), 3),
        "spend_usd": round(total_spend, 4),
        "cost_per_verified_row": round(total_spend / max(1, len(all_rows)), 5),
        "rejection_reasons": dict(reasons_all.most_common()),
        "by_bucket": dict(got.most_common()),
        "yield_by_bucket": {b: round(got[b] / n, 3) for b, n in sorted(asked_all.items())},
        "hard_case_share": round(sum(1 for r in all_rows.values() if r["hard_case"]) / max(1, len(all_rows)), 3),
        "refusals": sum(s["refusals"] for s in stages),
        "stages": stages,
    }
    Path("runs/targets_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "stages"}, indent=2))
    print(f"stage {stage}: validation {stage_rep['validation_seconds']}s, stage spend ${spend:.4f}")


if __name__ == "__main__":
    main()
