#!/usr/bin/env python3
"""Answers for the chart kinds v1 barely saw: funnel 0, sunburst 0, waterfall 2, KPI 39.

Stage 1, Haiku: for each (train schema, kind), one question a user would ask
that this kind answers best, or an empty question when the table cannot support
it. Stage 2, Sonnet: the code and the plan it implements, in one reply. A row is
kept only if the code passes the contract, runs against the real table, the
figure is that kind, the plan passes the production check, and every column the
plan names is in the code.

Rows are stored in data/targets.jsonl's format, so the existing exporters and
caps work on them, with `kind` and `spec` added.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import client
from contract import (CHARTIST_SYSTEM_PROMPT, CHARTIST_USER_TEMPLATE, KIND_TRACES, SPEC_RULES, SPEC_SCHEMA,
                      check_spec, columns_by_table, profile_table, render_profiles, validate_chart_code)
from executor import run_candidates
from extract_specs import columns_in_code, consistent

KIND_QUOTA = {"funnel": 150, "sunburst": 120, "waterfall": 150, "kpi": 150}
BUCKET_OF_KIND = {"funnel": "treemap_funnel_waterfall", "sunburst": "treemap_funnel_waterfall",
                  "waterfall": "treemap_funnel_waterfall", "kpi": "gauge_or_indicator"}
MEANING = {
    "funnel": "a funnel: how a count narrows across ordered stages, like visits to signups to purchases",
    "sunburst": "a sunburst: one total split by two nested categories, like region then product",
    "waterfall": "a waterfall: how separate amounts add up to a total, or how a value changed step by step",
    "kpi": "a single headline number, like total revenue or the average score",
}
STEER = {
    "funnel": "a funnel chart (go.Funnel or px.funnel), stages ordered from largest to smallest",
    "sunburst": "a sunburst chart (px.sunburst) with a two-level path",
    "waterfall": "a waterfall chart (go.Waterfall)",
    "kpi": "a single headline number drawn with go.Indicator (mode 'number', or 'number+delta' for a change)",
}
Q_SYSTEM = """You write one question a business user would type into a dashboard tool about this table, the kind best answered by the chart described. Use everyday words, under 15 words. If this table cannot honestly support that chart, reply with an empty question.
When the variation number is above 1, ask about a different measure or breakdown than the most obvious one.
Reply as JSON: {"question": "..."}"""
Q_SCHEMA = {"type": "object", "properties": {"question": {"type": "string"}},
            "required": ["question"], "additionalProperties": False}
CODE_SCHEMA = {"type": "object", "properties": {"plan": SPEC_SCHEMA, "code": {"type": "string"}},
               "required": ["plan", "code"], "additionalProperties": False}


def assign(kinds: dict[str, int], schemas: list[dict]) -> list[tuple[str, dict]]:
    train = [s for s in schemas if s["split"] == "train"]
    pairs = []
    for kind, count in kinds.items():
        pairs.extend((kind, train[i % len(train)]) for i in range(count))
    return pairs


def _prompt(schema: dict, question: str) -> str:
    return CHARTIST_USER_TEMPLATE.format(task=question, columns=schema["pandas_columns"],
                                         dtypes=schema["pandas_dtypes"], sample_rows=schema["sample_rows"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0, help="0.05 for a pilot")
    ap.add_argument("--out", default="data/v2/new_targets.jsonl")
    ap.add_argument("--max-spend", type=float, default=5.00)
    args = ap.parse_args()

    schemas = [json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l]
    train_count = sum(1 for s in schemas if s["split"] == "train")
    quota = {k: max(1, int(v * args.scale)) for k, v in KIND_QUOTA.items()}
    pairs = assign(quota, schemas)
    profiles = {s["schema_id"]: profile_table(s["table_name"], pd.read_csv(s["fixture_csv"])) for _, s in pairs}

    q_requests = []
    per_kind: dict[str, int] = {}
    for i, (kind, s) in enumerate(pairs):
        # A schema gets a kind twice when the quota passes the 120 train schemas.
        nth = per_kind.get(kind, 0)
        per_kind[kind] = nth + 1
        variation = nth // train_count + 1
        user = (f"Chart: {MEANING[kind]}\nVariation: {variation}\n\n"
                f"{render_profiles([profiles[s['schema_id']]])}")
        q_requests.append(client.json_request(f"q{i}", client.HAIKU, Q_SYSTEM, user, Q_SCHEMA,
                                              max_tokens=800, effort="low"))
    client.guard("v2-kind-questions", client.worst_case_cost(client.HAIKU, len(q_requests), 1500, 800))
    q_out = client.run_batch(q_requests, label="v2-kind-questions")
    spent = client.record_spend("v2-kind-questions", client.HAIKU, q_out.usage,
                                {"phase": "v2", "requests": len(q_requests)})

    jobs = [(i, kind, s, q_out.payloads[f"q{i}"]["question"].strip()) for i, (kind, s) in enumerate(pairs)
            if q_out.payloads.get(f"q{i}", {}).get("question", "").strip()]
    print(f"{len(jobs)} questions of {len(pairs)} (the rest: the table could not support the kind)")
    c_requests = []
    for i, kind, s, question in jobs:
        system = (CHARTIST_SYSTEM_PROMPT + f"\n\nFor this request, produce {STEER[kind]}. Return the code and "
                  f"the chart plan it implements, described below.\n\n{SPEC_RULES}")
        c_requests.append(client.json_request(f"c{i}", client.SONNET, system, _prompt(s, question), CODE_SCHEMA,
                                              max_tokens=4000, effort="medium"))
    planned = min(client.worst_case_cost(client.SONNET, len(c_requests), 2500, 4000), args.max_spend - spent)
    client.guard("v2-kind-code", planned)
    c_out = client.run_batch(c_requests, label="v2-kind-code")
    client.record_spend("v2-kind-code", client.SONNET, c_out.usage, {"phase": "v2", "requests": len(c_requests)})

    candidates = [(i, kind, s, q, c_out.payloads[f"c{i}"]) for i, kind, s, q in jobs if c_out.payloads.get(f"c{i}")]
    verdicts = run_candidates([(c[4]["code"], c[2]["fixture_csv"]) for c in candidates], max_workers=8)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    reasons: dict[str, int] = {}
    with out.open("w", encoding="utf-8") as handle:
        for (i, kind, s, question, payload), verdict in zip(candidates, verdicts):
            code = payload["code"].strip()
            plan = {**payload["plan"], "table": s["table_name"], "question": question}
            spec, problems = check_spec(plan, columns_by_table([profiles[s["schema_id"]]]))
            reason = ("contract" if validate_chart_code(code)
                      else "does not run" if not verdict.ok
                      else "wrong kind of figure" if verdict.figure_type not in KIND_TRACES[kind]
                      else "plan fails the check" if spec is None
                      else "plan is another kind" if spec["chart"] != kind
                      else "column not in code" if not columns_in_code(spec, code)
                      else "kind does not match the figure" if not consistent(spec, verdict.figure_type, code)
                      else "")
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
                continue
            handle.write(json.dumps({
                "schema_id": s["schema_id"], "question_id": f"v2-{kind}-{i}",
                "messages": [{"role": "system", "content": CHARTIST_SYSTEM_PROMPT},
                             {"role": "user", "content": _prompt(s, question)},
                             {"role": "assistant", "content": code}],
                "fixture_csv": s["fixture_csv"], "chart_bucket": BUCKET_OF_KIND[kind], "hard_case": None,
                "figure_type": verdict.figure_type, "attempt": 1, "kind": kind, "spec": spec,
            }, ensure_ascii=False) + "\n")
            kept += 1
    print(f"kept {kept} of {len(candidates)}; rejected {reasons}; v2 spend so far ${client.phase_spend():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
