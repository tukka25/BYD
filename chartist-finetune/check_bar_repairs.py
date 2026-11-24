#!/usr/bin/env python3
"""Acceptance for the bar drawing check: figure_problems sends back bars that repeat a category.

The 23 live plans (data/v2/live_plans.jsonl) are drawn through the app's own path
(run_spec: the chartist, the executor, the repair loop and the drawing check) by the
app's default chartist (no aggregation rule, no chart-type hint) on the model behind
the mlx_lm server, at temperature 0. Each is set beside the off arm of
data/v2/ab_agg_rule_live.rows.jsonl: the same plan, path, prompt and model before the
check existed. Scored as ab_agg_rule.score does, which also counts the bars the check
sent back. The decision (DECISION) was fixed before the first call.

    ../backend/.venv/bin/python check_bar_repairs.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ab_agg_rule import ROOT, SPEC_KEYS, _status, live_items, read_rows, score, summarize

import pandas as pd  # noqa: E402

BASELINE = ROOT / "data/v2/ab_agg_rule_live.rows.jsonl"
OUT = ROOT / "data/v2/bar_check_live.json"
DECISION = ("passes when the baseline drew raw-row bars on at least one plan, every such plan now renders with the "
            "planned values after at least one bar repair, no plan that rendered in the baseline fails now, and bars "
            "with the planned values are not fewer than in the baseline")


def bar_check_decision(rows: list[dict]) -> dict:
    """DECISION on rows whose arms are "before" (the baseline) and "after" (with the check)."""
    raw = [row for row in rows if row["arms"]["before"]["raw_bars"]]
    before, after = summarize(rows, "before"), summarize(rows, "after")
    decision = {
        "baseline_drew_raw_bars": bool(raw),
        "raw_bars_fixed_by_a_bar_repair": all(
            row["arms"]["after"]["rendered"] and row["arms"]["after"]["values_ok"] is True
            and row["arms"]["after"].get("repeated_bars", 0) >= 1 for row in raw),
        "no_chart_lost": not any(row["arms"]["before"]["rendered"] and not row["arms"]["after"]["rendered"]
                                 for row in rows),
        "values_not_fewer": after["bar_values_ok"] >= before["bar_values_ok"],
    }
    decision["passes"] = all(decision.values())
    return decision


def unchanged(rows: list[dict]) -> int:
    """Plans whose code is the same before and after: the check did not fire and the model answered alike."""
    return sum(1 for row in rows if row["arms"]["before"].get("code") == row["arms"]["after"].get("code"))


def main() -> int:
    from app.services.agents.chartist import ChartistAgent
    from app.services.agents.spec_runner import run_spec
    from app.services.llm import get_llm

    baseline = {row["item_id"]: row["arms"]["off"] for row in read_rows(BASELINE)}
    ckpt = OUT.with_suffix(".rows.jsonl")
    done = {row["item_id"] for row in read_rows(ckpt)} if ckpt.exists() else set()
    agent = ChartistAgent(get_llm("chartist"), chart_type_hint_style="off", agg_rule="off")
    items = live_items()
    print(f"{len(items)} plans, {len(items) - len(done)} to go", flush=True)

    frames: dict[str, pd.DataFrame] = {}
    started = time.perf_counter()
    for item in items:
        if item["item_id"] in done:
            continue
        csv = item["csv"]
        if csv not in frames:
            frames[csv] = pd.read_csv(csv)
        began = time.perf_counter()
        result = run_spec(item["spec"], {"type": "file", "name": Path(csv).name, "path": csv}, agent, str(ROOT))
        after = {**score(item["spec"], frames[csv], result), "seconds": round(time.perf_counter() - began, 1),
                 "repair_reasons": [str(reason)[:300] for reason in result.get("repair_reasons") or []]}
        before = baseline[item["item_id"]]
        record = {"item_id": item["item_id"], "csv": str(Path(csv).relative_to(ROOT.parent)),
                  "spec": {key: item["spec"].get(key) for key in SPEC_KEYS + ("title", "question")},
                  "arms": {"before": before, "after": after}}
        with ckpt.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{item['item_id']} {item['spec']['chart']}: before {_status(before)} | after {_status(after)}, "
              f"bar repairs {after['repeated_bars']} ({(time.perf_counter() - started) / 60:.1f} min)", flush=True)

    rows = read_rows(ckpt)
    changed = [{"item_id": row["item_id"], "chart": row["spec"].get("chart"), "title": row["spec"].get("title"),
                "before": _status(row["arms"]["before"]), "after": _status(row["arms"]["after"]),
                "repairs": row["arms"]["after"]["repairs"], "repeated_bars": row["arms"]["after"]["repeated_bars"],
                "repair_reasons": row["arms"]["after"].get("repair_reasons", [])}
               for row in rows if row["arms"]["before"].get("code") != row["arms"]["after"].get("code")]
    report = {
        "items": len(rows), "baseline": "off arm of data/v2/ab_agg_rule_live.rows.jsonl", "decision_rule": DECISION,
        "before": summarize(rows, "before"), "after": summarize(rows, "after"),
        "unchanged_code": unchanged(rows), "changed": changed, "decision": bar_check_decision(rows),
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("before", "after", "unchanged_code", "decision")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
