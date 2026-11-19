#!/usr/bin/env python3
"""Regenerate treemap_funnel_waterfall question text in place, with a stricter spec."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import client
import gen_questions

RULE = """

Extra rule for the chart shape treemap_funnel_waterfall. Each such question must be exactly one of:
- a HIERARCHY spanning two or more nesting levels (a category within a category, e.g. "from region down to product line").
- an ordered FUNNEL with stage-to-stage drop-off (e.g. "how many go from lead to qualified to won").
- a WATERFALL of positive and negative contributions to a running total (e.g. "what adds to and subtracts from net change").
A single-dimension breakdown or share-of-total question ("break down X by Y", "what share goes to each Z") is a bar or pie question and must NOT be used here. If the table lacks a natural hierarchy, stage order, or signed contributions, pick the closest nesting of two dimensions it does have."""

SCHEMA = {
    "type": "object",
    "properties": {"questions": {"type": "array", "items": {"type": "object",
        "properties": {"question": {"type": "string"}}, "required": ["question"], "additionalProperties": False}}},
    "required": ["questions"], "additionalProperties": False,
}


def main() -> None:
    schemas = {j["schema_id"]: j for j in (json.loads(l) for l in Path("data/schemas.jsonl").read_text().splitlines() if l)}
    path = Path("data/questions.jsonl")
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l]
    by_schema = defaultdict(list)
    for i, r in enumerate(rows):
        if r["chart_bucket"] == "treemap_funnel_waterfall":
            by_schema[r["schema_id"]].append(i)

    reqs = []
    for sid, idxs in by_schema.items():
        s = schemas[sid]
        spec = "\n".join(
            f"{n + 1}. chart shape: treemap_funnel_waterfall"
            + (f", hard case: {rows[i]['hard_case']}" if rows[i]["hard_case"] else "")
            for n, i in enumerate(idxs)
        )
        reqs.append(client.json_request(
            custom_id=sid, model=client.HAIKU, system=gen_questions.SYSTEM + RULE,
            user=(f"Table: {s['table_name']} ({s['domain']})\ncolumns: {json.dumps(s['columns'], default=str)}\n\n"
                  f"Write exactly {len(idxs)} questions, one per line item below, in order:\n{spec}"),
            schema=SCHEMA, max_tokens=2048, effort="low"))

    out = client.run_batch(reqs, label="treemap_regen")
    cost = client.record_spend("treemap_regen", client.HAIKU, out.usage, {"requests": len(reqs)})
    replaced, new = 0, []
    for sid, idxs in by_schema.items():
        qs = (out.payloads.get(sid) or {}).get("questions", [])
        if len(qs) != len(idxs):
            print("count mismatch, skipped", sid, len(qs), len(idxs)); continue
        for i, q in zip(idxs, qs):
            t = (q.get("question") or "").strip()
            if len(t) >= 8:
                rows[i]["question"] = t; replaced += 1; new.append(t)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps({"replaced": replaced, "of": sum(map(len, by_schema.values())), "cost": cost}))
    import random
    for t in random.Random(1).sample(new, 8): print("-", t)


if __name__ == "__main__":
    main()
