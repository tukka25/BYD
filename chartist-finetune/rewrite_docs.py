#!/usr/bin/env python3
"""Rewrite scraped Plotly-docs examples into contract-compliant rows.

The docs code builds its own dataframe, renders with fig.show(), and never prints
figure JSON. Lift the embedded data into a CSV fixture, drop the loader, and the
row becomes a legitimate schema-conditioned example. The code and the fixture are
deterministic; the user question is written by one Haiku batch afterwards, because
the scraped prompts are documentation-page phrasing that never occurs at inference.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

import client
from contract import CHARTIST_SYSTEM_PROMPT, CHARTIST_USER_TEMPLATE
from executor import run_candidates

REPO = Path(__file__).resolve().parent.parent
SOURCES = [
    ("train", REPO / "web-crawler/dataset/plotly_qwen_train.jsonl"),
    ("val", REPO / "web-crawler/dataset/plotly_qwen_val.jsonl"),
]
MAPPING = REPO / "web-crawler/dataset/plotly_qwen_mapping.jsonl"
FIXTURE_DIR = Path("data/fixtures_docs")
WORKERS = 8

# A statement that creates the dataframe: a read_*, px.data.*, or a DataFrame call.
FRAME_SOURCE = re.compile(r"\bread_\w+\s*\(|\bpx\s*\.\s*data\s*\.|\bDataFrame\s*\(")

DUMP = """
import json, sys
job = json.loads(sys.stdin.read())
ns = {}
exec(compile(job["loader"], "<loader>", "exec"), ns)
import pandas as pd
frame = ns.get(job["var"])
if not isinstance(frame, pd.DataFrame) or frame.empty:
    sys.exit(3)
frame.head(240).to_csv(job["out"], index=False)
"""


# ---------------------------------------------------------------- code rewriting

class _DropShow(ast.NodeTransformer):
    def visit_Expr(self, node: ast.Expr):  # noqa: N802
        call = node.value
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "show"
        ):
            return ast.Pass()
        return node


def strip_show(code: str) -> str:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return re.sub(r"^\s*fig\s*\.\s*show\s*\(.*\)\s*$", "", code, flags=re.MULTILINE)
    tree = _DropShow().visit(tree)
    tree.body = [n for n in tree.body if not isinstance(n, ast.Pass)] or tree.body
    return ast.unparse(ast.fix_missing_locations(tree))


def ensure_json_print(code: str) -> str:
    text = code.rstrip()
    return text if text.endswith("print(fig.to_json())") else f"{text}\nprint(fig.to_json())"


def _is_import(node: ast.stmt) -> bool:
    return isinstance(node, (ast.Import, ast.ImportFrom))


def split_loader(code: str) -> tuple[str, str, str] | None:
    """(loader, chart, frame_var), or None when no top-level frame assignment exists.

    The loader is every statement up to and including the frame assignment, so
    seeds and numpy arrays the frame is built from travel with it. Imports go to
    both sides. The chart is everything after, with the frame renamed to `df`.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    body = tree.body
    for i, node in enumerate(body):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and FRAME_SOURCE.search(ast.unparse(node.value))
        ):
            var = node.targets[0].id
            imports = [n for n in body if _is_import(n)]
            loader = ast.Module(body=imports + [n for n in body[: i + 1] if not _is_import(n)],
                                type_ignores=[])
            chart = ast.Module(body=imports + body[i + 1 :], type_ignores=[])
            return (
                ast.unparse(ast.fix_missing_locations(loader)),
                ast.unparse(ast.fix_missing_locations(chart)),
                var,
            )
    return None


def split_data_loading(code: str) -> tuple[str, str]:
    found = split_loader(code)
    if found is None:
        return "", code
    return found[0], found[1]


class _Rename(ast.NodeTransformer):
    def __init__(self, old: str, new: str):
        self.old, self.new = old, new

    def visit_Name(self, node: ast.Name):  # noqa: N802
        if node.id == self.old:
            return ast.copy_location(ast.Name(id=self.new, ctx=node.ctx), node)
        return node


def rename_var(chart: str, old: str, new: str = "df") -> str | None:
    """Rename the frame to `df`; None if `df` is already something else in the chart."""
    if old == new:
        return chart
    tree = ast.parse(chart)
    if any(isinstance(n, ast.Name) and n.id == new for n in ast.walk(tree)):
        return None
    return ast.unparse(ast.fix_missing_locations(_Rename(old, new).visit(tree)))


def _literal_list(node: ast.AST):
    if isinstance(node, (ast.List, ast.Tuple)):
        try:
            value = ast.literal_eval(node)
        except (ValueError, SyntaxError):
            return None
        if len(value) >= 2 and all(isinstance(v, (int, float, str)) and not isinstance(v, bool)
                                   for v in value):
            return list(value)
    return None


class _LiftXY(ast.NodeTransformer):
    """Replace the first call's literal x=[..], y=[..] with df['x'], df['y']."""

    def __init__(self):
        self.frame: pd.DataFrame | None = None

    def visit_Call(self, node: ast.Call):  # noqa: N802
        if self.frame is None:
            kw = {k.arg: k for k in node.keywords if k.arg in ("x", "y")}
            if len(kw) == 2:
                xs, ys = _literal_list(kw["x"].value), _literal_list(kw["y"].value)
                if xs is not None and ys is not None and len(xs) == len(ys):
                    self.frame = pd.DataFrame({"x": xs, "y": ys})
                    for name, k in kw.items():
                        k.value = ast.Subscript(
                            value=ast.Name(id="df", ctx=ast.Load()),
                            slice=ast.Constant(value=name), ctx=ast.Load(),
                        )
                    return node
        self.generic_visit(node)
        return node


def lift_literals(code: str) -> tuple[str, pd.DataFrame] | None:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    lifter = _LiftXY()
    tree = lifter.visit(tree)
    if lifter.frame is None:
        return None
    return ast.unparse(ast.fix_missing_locations(tree)), lifter.frame


# ---------------------------------------------------------------- fixtures

def _dump_frame(job: dict) -> bool:
    try:
        done = subprocess.run(
            [sys.executable, "-I", "-c", DUMP],
            input=json.dumps({"loader": job["loader"], "var": job["var"], "out": job["out"]}),
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0 and Path(job["out"]).is_file()


def materialize_all(jobs: list[dict]) -> list[bool]:
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return list(pool.map(_dump_frame, jobs))


# ---------------------------------------------------------------- questions

QUESTION_SYSTEM = """You write the questions a business user types into a dashboard tool.

You are shown a table (columns, dtypes, two sample rows) and the chart code that was written for it. Write the one question a person might have asked that this chart answers.

Rules:
- Never mention Plotly, Python, code, charts-as-examples, or column names verbatim unless a person naturally would.
- Write like a person asking for something, not like documentation. 4 to 18 words.
- The question must be answerable from the given table, and must suit the chart the code draws.
- Vary phrasing: questions, imperatives, and fragments all appear in real usage.
- No greetings, no "please", no "could you"."""

QUESTION_SCHEMA = {
    "type": "object",
    "properties": {"question": {"type": "string"}},
    "required": ["question"],
    "additionalProperties": False,
}
LEAK = re.compile(
    r"plotly|python|\bcode\b|\bexample|dataframe|\bdf\b|focus on|details:|return only",
    re.IGNORECASE,
)


def question_user_turn(item: dict) -> str:
    return (
        f"columns: {item['columns']}\ndtypes: {item['dtypes']}\n"
        f"first rows: {item['sample_rows']}\n\nchart code:\n{item['chart']}"
    )


def write_questions(items: list[dict]) -> dict[str, str]:
    requests = [
        client.json_request(
            it["question_id"], client.HAIKU, QUESTION_SYSTEM, question_user_turn(it),
            QUESTION_SCHEMA, max_tokens=200,
        )
        for it in items
    ]
    outcome = client.run_batch(requests, "docs-questions", poll_seconds=15)
    cost = client.record_spend("docs-questions", client.HAIKU, outcome.usage,
                               {"requests": len(requests)})
    print(f"questions: {len(outcome.payloads)}/{len(requests)} parsed, refusals "
          f"{outcome.refusals}, errored {outcome.errored}, unparsed {outcome.unparsed}, "
          f"${cost:.4f}")
    return {k: (v.get("question") or "").strip() for k, v in outcome.payloads.items()
            if isinstance(v, dict)}


# ---------------------------------------------------------------- main

def slugify(url: str) -> str:
    tail = [p for p in url.split("?")[0].split("#")[0].split("/") if p][-1]
    return re.sub(r"[^a-z0-9]+", "-", tail.lower()).strip("-") or "unknown"


def load_rows() -> list[dict]:
    meta = [json.loads(l) for l in MAPPING.read_text(encoding="utf-8").splitlines() if l]
    kept = {s: [m for m in meta if m["kept"] and m["split"] == s] for s, _ in SOURCES}
    rows = []
    for split, path in SOURCES:
        lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l]
        assert len(lines) == len(kept[split]), (split, len(lines), len(kept[split]))
        for row, m in zip(lines, kept[split]):
            rows.append({"messages": row["messages"], "meta": m})
    return rows


LIST_ARGS = {"x", "y", "z", "values", "labels", "lat", "lon", "open", "high", "low", "close"}
MAX_PER_PAGE = 6


def has_literal_data(chart: str) -> bool:
    """True if any call still passes a literal list/tuple for a data argument."""
    for node in ast.walk(ast.parse(chart)):
        if isinstance(node, ast.Call):
            for k in node.keywords:
                if k.arg in LIST_ARGS and _literal_list(k.value) is not None:
                    return True
    return False


def count_figure_constructors(chart: str) -> int:
    n = 0
    for node in ast.walk(ast.parse(chart)):
        if (isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "fig" for t in node.targets)
                and isinstance(node.value, ast.Call)):
            f = node.value.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and (
                    f.value.id == "px" or (f.value.id == "go" and f.attr == "Figure")):
                n += 1
            elif isinstance(f, ast.Name) and f.id == "make_subplots":
                n += 1
            elif isinstance(f, ast.Attribute) and f.attr == "make_subplots":
                n += 1
    return n


def _norm_code(chart: str) -> str:
    return re.sub(r"\s+", "", ast.unparse(ast.parse(chart)))  # unparse drops comments


def refilter(rows: list[dict]) -> tuple[list[dict], Counter]:
    """Post-filter: partial lifts, multi-figure rows, duplicates, per-page cap.

    Dedupe and cap walk rows rarest-figure_type first so exotic types survive.
    """
    reasons: Counter = Counter()
    all_types = {r["figure_type"] for r in rows}
    live = []
    for r in rows:
        chart = r["messages"][2]["content"]
        lifted = "df['x']" in chart and list(pd.read_csv(r["fixture_csv"], nrows=1).columns) == ["x", "y"]
        if lifted and has_literal_data(chart):
            reasons["partial_lift"] += 1
        elif count_figure_constructors(chart) > 1:
            reasons["multiple_figures"] += 1
        else:
            live.append(r)
    before_types = {r["figure_type"] for r in live}
    print("types lost to partial_lift/multiple_figures (every row of the type failed):",
          sorted(all_types - before_types))
    freq = Counter(r["figure_type"] for r in live)
    seen_q, seen_c, per_page, keep = set(), set(), Counter(), set()
    for r in sorted(live, key=lambda r: (freq[r["figure_type"]], r["question_id"])):
        q = " ".join(r["question"].lower().split())
        c = _norm_code(r["messages"][2]["content"])
        if q in seen_q:
            reasons["duplicate_question"] += 1
        elif c in seen_c:
            reasons["duplicate_code"] += 1
        elif per_page[r["schema_id"]] >= MAX_PER_PAGE:
            reasons["page_cap"] += 1
        else:
            seen_q.add(q); seen_c.add(c); per_page[r["schema_id"]] += 1
            keep.add(r["question_id"])
    out = [r for r in rows if r["question_id"] in keep]
    lost = before_types - {r["figure_type"] for r in out}
    if lost:
        raise SystemExit(f"dedupe/cap LOST figure types: {sorted(lost)}")
    return out, reasons


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refilter", action="store_true",
                        help="apply the post-filter to data/docs_rows.jsonl (no API calls)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-questions", action="store_true",
                        help="smoke mode: skip Haiku, write to runs/docs_rows_noq.jsonl")
    args = parser.parse_args()

    if args.refilter:
        src = Path("runs/docs_rows_prefix.jsonl")
        rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l]
        out, why = refilter(rows)
        Path("data/docs_rows.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in out),
            encoding="utf-8")
        live = {Path(r["fixture_csv"]).name for r in out}
        for f in FIXTURE_DIR.glob("*.csv"):
            if f.name not in live:
                f.unlink()
        pages = Counter(r["schema_id"] for r in out)
        print(json.dumps({"before": len(rows), "kept": len(out), "drops": dict(why),
                          "schemas": len(pages), "max_per_page": max(pages.values()),
                          "types_before": len({r["figure_type"] for r in rows}),
                          "types_after": len({r["figure_type"] for r in out})}, indent=2))
        return

    rows = load_rows()
    if args.limit:
        rows = rows[: args.limit]
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    reasons: Counter = Counter()
    cands: list[dict] = []

    # Phase 1: deterministic rewrite.
    for index, row in enumerate(rows):
        messages = row["messages"]
        if len(messages) != 3:
            reasons["malformed"] += 1
            continue
        code = messages[2]["content"]
        qid = f"docs-{index:04d}"
        out = FIXTURE_DIR / f"{qid}.csv"
        split = split_loader(code)
        cand = {"index": index, "question_id": qid, "out": str(out), "meta": row["meta"],
                "frame": None, "loader": None, "var": None}
        if split is not None:
            loader, chart, var = split
            chart = rename_var(chart, var)
            if chart is None:
                reasons["df_name_conflict"] += 1
                continue
            cand.update(loader=loader, var=var)
        else:
            lifted = lift_literals(code)
            if lifted is None:
                reasons["no_dataframe_recovered"] += 1
                continue
            chart, cand["frame"] = lifted
        chart = ensure_json_print(strip_show(chart))
        try:
            ast.parse(chart)
        except SyntaxError:
            reasons["chart_syntax_error"] += 1
            continue
        cand["chart"] = chart
        cands.append(cand)
    print(f"phase 1: {len(cands)} candidates of {len(rows)}", flush=True)

    # Phase 2: fixtures, 8 threads.
    t0 = time.time()
    for c in cands:
        if c["frame"] is not None:
            c["frame"].to_csv(c["out"], index=False)
    dump_jobs = [c for c in cands if c["loader"] is not None]
    done = dict(zip((c["question_id"] for c in dump_jobs), materialize_all(dump_jobs)))
    t_fix = time.time() - t0
    print(f"phase 2 (fixtures, {len(dump_jobs)} subprocesses): {t_fix:.0f}s", flush=True)

    ready = []
    for c in cands:
        if c["loader"] is not None and not done[c["question_id"]]:
            reasons["no_dataframe_recovered"] += 1
            continue
        try:
            frame = pd.read_csv(c["out"])
        except Exception:  # noqa: BLE001
            reasons["unreadable_fixture"] += 1
            continue
        if frame.empty:
            reasons["empty_frame"] += 1
            continue
        c["columns"] = list(frame.columns)
        c["dtypes"] = {k: str(d) for k, d in frame.dtypes.items()}
        c["sample_rows"] = frame.head(2).to_dict(orient="records")
        ready.append(c)

    # Phase 3: execution filter, 8 workers.
    t0 = time.time()
    verdicts = run_candidates([(c["chart"], c["out"]) for c in ready], max_workers=WORKERS)
    t_exec = time.time() - t0
    print(f"phase 3 (execution, {len(ready)} candidates): {t_exec:.0f}s", flush=True)
    survivors = []
    for c, v in zip(ready, verdicts):
        if not v.ok:
            reasons[f"exec:{v.failure_kind or (v.violations[0] if v.violations else 'failed')}"] += 1
            continue
        c["figure_type"] = v.figure_type
        survivors.append(c)

    # Phase 4: natural questions, one Haiku batch.
    if args.no_questions:
        questions = {c["question_id"]: "(smoke)" for c in survivors}
        dest = Path("runs/docs_rows_noq.jsonl")
    else:
        questions = write_questions(survivors)
        dest = Path("data/docs_rows.jsonl")

    kept = []
    for c in survivors:
        q = questions.get(c["question_id"], "")
        if not q:
            reasons["question_empty_or_missing"] += 1
            continue
        if LEAK.search(q):
            reasons["question_leaks_docs_phrasing"] += 1
            continue
        prompt = CHARTIST_USER_TEMPLATE.format(
            task=q, columns=c["columns"], dtypes=c["dtypes"], sample_rows=c["sample_rows"]
        )
        kept.append({
            "schema_id": f"docs-{slugify(c['meta']['source_url'])}",
            "question_id": c["question_id"],
            "messages": [
                {"role": "system", "content": CHARTIST_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": c["chart"]},
            ],
            "fixture_csv": c["out"],
            "chart_bucket": None,
            "hard_case": None,
            "figure_type": c["figure_type"],
            "source": "docs",
            "question": q,
            "docs_graph_type": c["meta"].get("graph_type"),
        })

    with dest.open("w", encoding="utf-8") as handle:
        for item in kept:
            handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
    # Fixtures for rows that did not survive are noise; remove them.
    live = {Path(k["fixture_csv"]).name for k in kept}
    for f in FIXTURE_DIR.glob("*.csv"):
        if f.name not in live and not args.limit:
            f.unlink()
    print(json.dumps({"input": len(rows), "kept": len(kept),
                      "drop_reasons": dict(reasons.most_common()),
                      "fixture_seconds": round(t_fix), "exec_seconds": round(t_exec),
                      "figure_types": dict(Counter(k["figure_type"] for k in kept))},
                     indent=2))


if __name__ == "__main__":
    main()
