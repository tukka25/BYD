#!/usr/bin/env python3
"""Sonnet writes the code for the chart plans Opus planned.

The v2 chartist then learns plan -> code on exactly the kind of plans the
planner produces. Each plan becomes one chartist prompt built with render_spec,
the same text the app sends. Kept only if the code passes the contract, runs
against the real table, draws the planned kind, and uses the plan's columns.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import client
from contract import CHARTIST_SYSTEM_PROMPT, CHARTIST_USER_TEMPLATE, render_spec, validate_chart_code
from executor import run_candidates
from extract_specs import columns_in_code, consistent

CODE_SCHEMA = {"type": "object", "properties": {"code": {"type": "string"}},
               "required": ["code"], "additionalProperties": False}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-charts", type=int, default=1000)
    ap.add_argument("--max-spend", type=float, default=4.00)
    ap.add_argument("--out", default="data/v2/spec_targets.jsonl")
    args = ap.parse_args()

    schemas = {
        r["schema_id"]: r
        for r in (json.loads(l) for l in Path("data/schemas.jsonl").read_text(encoding="utf-8").splitlines() if l)
    }
    plans = [json.loads(l) for l in Path("data/v2/plans.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    jobs = [(p, n, spec) for p in plans for n, spec in enumerate(p["charts"])][: args.max_charts]

    def prompt(p, spec):
        s = schemas[p["schema_id"]]
        return CHARTIST_USER_TEMPLATE.format(task=render_spec(spec), columns=s["pandas_columns"],
                                             dtypes=s["pandas_dtypes"], sample_rows=s["sample_rows"])

    requests = [client.json_request(f"{p['request_id']}-c{n}", client.SONNET,
                                    CHARTIST_SYSTEM_PROMPT + f"\n\nFor this request, produce a {spec['chart']} chart.",
                                    prompt(p, spec), CODE_SCHEMA, max_tokens=3000, effort="low")
                for p, n, spec in jobs]
    planned = min(args.max_spend, client.worst_case_cost(client.SONNET, len(requests), 2500, 3000))
    client.guard("v2-spec-code", planned)
    outcome = client.run_batch(requests, label="v2-spec-code")
    client.record_spend("v2-spec-code", client.SONNET, outcome.usage, {"phase": "v2", "requests": len(requests)})

    candidates = [(p, n, spec, outcome.payloads[f"{p['request_id']}-c{n}"]["code"].strip())
                  for p, n, spec in jobs if outcome.payloads.get(f"{p['request_id']}-c{n}")]
    verdicts = run_candidates([(c[3], schemas[c[0]["schema_id"]]["fixture_csv"]) for c in candidates], max_workers=8)
    kept = 0
    reasons: dict[str, int] = {}
    with Path(args.out).open("w", encoding="utf-8") as handle:
        for (p, n, spec, code), verdict in zip(candidates, verdicts):
            reason = ("contract" if validate_chart_code(code)
                      else "does not run" if not verdict.ok
                      else "column not in code" if not columns_in_code(spec, code)
                      else "kind does not match the figure" if not consistent(spec, verdict.figure_type, code)
                      else "")
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
                continue
            handle.write(json.dumps({
                "schema_id": p["schema_id"], "question_id": f"{p['request_id']}-c{n}",
                "messages": [{"role": "system", "content": CHARTIST_SYSTEM_PROMPT},
                             {"role": "user", "content": prompt(p, spec)},
                             {"role": "assistant", "content": code}],
                "fixture_csv": schemas[p["schema_id"]]["fixture_csv"], "chart_bucket": spec["chart"],
                "hard_case": None, "figure_type": verdict.figure_type, "attempt": 1,
                "spec": spec, "format": "spec",
            }, ensure_ascii=False) + "\n")
            kept += 1
    print(f"kept {kept} of {len(candidates)}; rejected {reasons}; v2 spend so far ${client.phase_spend():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
