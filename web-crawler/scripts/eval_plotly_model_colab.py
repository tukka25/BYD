#!/usr/bin/env python3
"""Colab-friendly evaluation script for fine-tuned Qwen Plotly code model.

Evaluates a model on a JSONL validation set with `messages` format:
- format compliance (code-only heuristics)
- plotly usage
- python syntax validity
- optional runtime execution with timeout
- lightweight chart-type keyword match from prompt

Works with Unsloth models/adapters and can optionally compare with a base model.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from unsloth import FastLanguageModel
from unsloth.chat_templates import get_chat_template
try:
    from tqdm.auto import tqdm
except Exception:  # pragma: no cover
    tqdm = None


@dataclass
class EvalSample:
    idx: int
    prompt: str
    reference: str


def load_eval_samples(path: Path, limit: int | None = None) -> list[EvalSample]:
    samples: list[EvalSample] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if not line.strip():
                continue
            obj = json.loads(line)
            msgs = obj.get("messages", [])
            user = next((m.get("content", "") for m in msgs if m.get("role") == "user"), "")
            assistant = next((m.get("content", "") for m in msgs if m.get("role") == "assistant"), "")
            if not user or not assistant:
                continue
            samples.append(EvalSample(idx=i, prompt=user, reference=assistant))
            if limit and len(samples) >= limit:
                break
    return samples


def resolve_model_name(model_arg: str) -> str:
    """
    Accepts:
    - HF model id
    - direct checkpoint path
    - training output dir containing checkpoint-* subdirs (uses latest by step)
    """
    p = Path(model_arg)
    if not p.exists():
        return model_arg

    if p.is_file():
        return str(p)

    if p.is_dir():
        # If user already passed checkpoint dir, use it directly.
        if p.name.startswith("checkpoint-"):
            return str(p)

        ckpts = []
        for child in p.iterdir():
            if child.is_dir() and child.name.startswith("checkpoint-"):
                try:
                    step = int(child.name.split("-")[-1])
                except ValueError:
                    step = -1
                ckpts.append((step, child))
        if ckpts:
            ckpts.sort(key=lambda x: x[0])
            return str(ckpts[-1][1])

    return model_arg


def load_model_and_tokenizer(model_name: str, chat_template: str):
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name,
        load_in_4bit=True,
        dtype=None,
    )
    tokenizer = get_chat_template(tokenizer, chat_template=chat_template)
    FastLanguageModel.for_inference(model)

    model.config.use_cache = False

    return model, tokenizer


def generate_code(
    model,
    tokenizer,
    prompt: str,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
    do_sample: bool,
) -> str:
    messages = [{"role": "user", "content": prompt}]
    model_inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
    )
    model_inputs = model_inputs.to("cuda")

    # Depending on tokenizer/transformers versions, this can be either:
    # - a Tensor (input_ids)
    # - a BatchEncoding with input_ids (+ optional attention_mask)
    if isinstance(model_inputs, torch.Tensor):
        input_ids = model_inputs
        attention_mask = None
    else:
        input_ids = model_inputs["input_ids"]
        attention_mask = model_inputs.get("attention_mask")

    with torch.no_grad():
        generate_kwargs = dict(
            input_ids=input_ids,
            max_new_tokens=max_new_tokens,
            use_cache=False,
            do_sample=False,
            temperature=1.0,
            top_p=1.0,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.eos_token_id,
        )
        if attention_mask is not None:
            generate_kwargs["attention_mask"] = attention_mask
        outputs = model.generate(**generate_kwargs)

    # decode only generated tokens
    prompt_len = input_ids.shape[-1]
    gen_tokens = outputs[0][prompt_len:]
    text = tokenizer.decode(gen_tokens, skip_special_tokens=True)
    return text.strip()


def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def is_code_only_heuristic(text: str) -> bool:
    lowered = text.lower()
    bad_phrases = [
        "here is",
        "sure",
        "this code",
        "explanation",
        "let me know",
    ]
    if any(p in lowered for p in bad_phrases):
        return False
    if "```" in text:
        return False
    return True


def contains_plotly_usage(text: str) -> bool:
    lower = text.lower()
    signals = ["plotly", "px.", "go.", "figure(", "fig ="]
    return any(s in lower for s in signals)


def syntax_valid(text: str) -> bool:
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False


def infer_expected_chart(prompt: str) -> str | None:
    p = prompt.lower()
    mapping = {
        "bar": ["bar chart", "bar plots", " bar "],
        "line": ["line chart", "line plot", " line "],
        "scatter": ["scatter"],
        "histogram": ["histogram"],
        "box": ["box plot", "box"],
        "violin": ["violin"],
        "heatmap": ["heatmap"],
        "pie": ["pie chart", "pie"],
        "choropleth": ["choropleth"],
        "treemap": ["treemap"],
        "sunburst": ["sunburst"],
        "sankey": ["sankey"],
        "candlestick": ["candlestick"],
        "waterfall": ["waterfall"],
        "funnel": ["funnel"],
        "surface": ["surface"],
        "map": ["map", "mapbox", "geo"],
        "3d": ["3d"],
    }
    for label, keys in mapping.items():
        if any(k in p for k in keys):
            return label
    return None


def chart_match(prompt: str, code: str) -> bool | None:
    expected = infer_expected_chart(prompt)
    if expected is None:
        return None

    c = code.lower()
    checks = {
        "bar": ["px.bar", "go.bar", "bar("],
        "line": ["px.line", "go.scatter", "mode='lines'", 'mode="lines"'],
        "scatter": ["px.scatter", "go.scatter"],
        "histogram": ["px.histogram", "go.histogram"],
        "box": ["px.box", "go.box"],
        "violin": ["px.violin", "go.violin"],
        "heatmap": ["px.imshow", "go.heatmap", "density_heatmap"],
        "pie": ["px.pie", "go.pie"],
        "choropleth": ["px.choropleth", "go.choropleth"],
        "treemap": ["px.treemap", "go.treemap"],
        "sunburst": ["px.sunburst", "go.sunburst"],
        "sankey": ["go.sankey"],
        "candlestick": ["go.candlestick"],
        "waterfall": ["go.waterfall"],
        "funnel": ["go.funnel", "px.funnel"],
        "surface": ["go.surface"],
        "map": ["scatter_geo", "scattermap", "px.scatter_map", "px.choropleth"],
        "3d": ["scatter3d", "surface(", "cone(", "streamtube("],
    }
    return any(token in c for token in checks.get(expected, []))


def execute_code_safely(code: str, timeout_sec: int = 20) -> tuple[bool, str]:
    harness = textwrap.dedent(
        """
        import warnings
        warnings.filterwarnings('ignore')

        import plotly.graph_objects as go
        import plotly.express as px
        import numpy as np
        import pandas as pd

        # Prevent opening browser / notebook render during eval
        from plotly.basedatatypes import BaseFigure
        BaseFigure.show = lambda *args, **kwargs: None
        """
    )

    payload = harness + "\n" + code + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(payload)
        temp_path = tf.name

    try:
        proc = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        ok = proc.returncode == 0
        err = (proc.stderr or "").strip()
        if len(err) > 1200:
            err = err[:1200] + "..."
        return ok, err
    except subprocess.TimeoutExpired:
        return False, f"Timeout after {timeout_sec}s"


def evaluate_model(
    model_name: str,
    samples: list[EvalSample],
    chat_template: str,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
    do_sample: bool,
    run_execution: bool,
    exec_timeout: int,
    print_every: int,
) -> dict[str, Any]:
    print(f"[eval] Loading model: {model_name}", flush=True)
    model, tokenizer = load_model_and_tokenizer(model_name=model_name, chat_template=chat_template)
    print(f"[eval] Loaded model. Starting generation on {len(samples)} samples...", flush=True)

    rows: list[dict[str, Any]] = []
    start = time.time()

    iterator = enumerate(samples, start=1)
    if tqdm is not None:
        iterator = enumerate(
            tqdm(samples, total=len(samples), desc=f"Evaluating {Path(model_name).name}", unit="sample"),
            start=1,
        )

    for i, sample in iterator:
        raw = generate_code(
            model,
            tokenizer,
            sample.prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=do_sample,
        )
        pred = strip_markdown_fences(raw)

        code_only = is_code_only_heuristic(pred)
        plotly_ok = contains_plotly_usage(pred)
        syntax_ok = syntax_valid(pred)
        match = chart_match(sample.prompt, pred)

        exec_ok = None
        exec_err = ""
        if run_execution and syntax_ok:
            exec_ok, exec_err = execute_code_safely(pred, timeout_sec=exec_timeout)

        rows.append(
            {
                "idx": sample.idx,
                "prompt": sample.prompt,
                "reference": sample.reference,
                "prediction": pred,
                "metrics": {
                    "code_only": code_only,
                    "plotly_usage": plotly_ok,
                    "syntax_ok": syntax_ok,
                    "chart_match": match,
                    "execution_ok": exec_ok,
                },
                "execution_error": exec_err,
            }
        )

        if print_every > 0 and i % print_every == 0:
            print(f"[{model_name}] done {i}/{len(samples)}", flush=True)

    elapsed = time.time() - start

    def rate_bool(key: str) -> float:
        vals = [r["metrics"][key] for r in rows if r["metrics"][key] is not None]
        if not vals:
            return 0.0
        return sum(bool(v) for v in vals) / len(vals)

    summary = {
        "model": model_name,
        "num_samples": len(rows),
        "elapsed_sec": elapsed,
        "avg_sec_per_sample": elapsed / max(1, len(rows)),
        "code_only_rate": rate_bool("code_only"),
        "plotly_usage_rate": rate_bool("plotly_usage"),
        "syntax_ok_rate": rate_bool("syntax_ok"),
        "chart_match_rate": rate_bool("chart_match"),
        "execution_ok_rate": rate_bool("execution_ok") if run_execution else None,
    }
    print(
        f"[eval] Completed {model_name}: "
        f"code_only={summary['code_only_rate']:.3f}, "
        f"plotly={summary['plotly_usage_rate']:.3f}, "
        f"syntax={summary['syntax_ok_rate']:.3f}, "
        f"match={summary['chart_match_rate']:.3f}, "
        f"exec={summary['execution_ok_rate'] if summary['execution_ok_rate'] is not None else 'N/A'}",
        flush=True,
    )

    return {"summary": summary, "rows": rows}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate fine-tuned Plotly model on JSONL val set")
    parser.add_argument("--val-path", type=Path, required=True)
    parser.add_argument("--model", type=str, required=True, help="FT model path/name")
    parser.add_argument("--base-model", type=str, default="", help="Optional baseline model path/name")
    parser.add_argument("--chat-template", type=str, default="qwen-3")
    parser.add_argument("--limit", type=int, default=0, help="0 means all")
    parser.add_argument("--max-new-tokens", type=int, default=640)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--do-sample", action="store_true")
    parser.add_argument("--run-exec", action="store_true", help="Run subprocess execution checks")
    parser.add_argument("--exec-timeout", type=int, default=20)
    parser.add_argument("--print-every", type=int, default=25)
    parser.add_argument("--out-dir", type=Path, default=Path("eval_outputs"))
    args = parser.parse_args()

    samples = load_eval_samples(args.val_path, limit=args.limit or None)
    if not samples:
        raise ValueError(f"No valid samples found in {args.val_path}")

    args.out_dir.mkdir(parents=True, exist_ok=True)

    ft_model = resolve_model_name(args.model)
    base_model = resolve_model_name(args.base_model) if args.base_model else ""
    print(f"Using fine-tuned model path/name: {ft_model}")
    if base_model:
        print(f"Using baseline model path/name: {base_model}")

    ft = evaluate_model(
        model_name=ft_model,
        samples=samples,
        chat_template=args.chat_template,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        do_sample=args.do_sample,
        run_execution=args.run_exec,
        exec_timeout=args.exec_timeout,
        print_every=args.print_every,
    )

    ft_rows_path = args.out_dir / "finetuned_rows.jsonl"
    ft_summary_path = args.out_dir / "finetuned_summary.json"
    write_jsonl(ft_rows_path, ft["rows"])
    ft_summary_path.write_text(json.dumps(ft["summary"], ensure_ascii=False, indent=2), encoding="utf-8")

    out = {"finetuned": ft["summary"], "baseline": None, "delta": None}

    if base_model:
        base = evaluate_model(
            model_name=base_model,
            samples=samples,
            chat_template=args.chat_template,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
            do_sample=args.do_sample,
            run_execution=args.run_exec,
            exec_timeout=args.exec_timeout,
            print_every=args.print_every,
        )
        base_rows_path = args.out_dir / "baseline_rows.jsonl"
        base_summary_path = args.out_dir / "baseline_summary.json"
        write_jsonl(base_rows_path, base["rows"])
        base_summary_path.write_text(json.dumps(base["summary"], ensure_ascii=False, indent=2), encoding="utf-8")

        delta = {}
        for key in [
            "code_only_rate",
            "plotly_usage_rate",
            "syntax_ok_rate",
            "chart_match_rate",
            "execution_ok_rate",
        ]:
            a = ft["summary"].get(key)
            b = base["summary"].get(key)
            if a is None or b is None:
                delta[key] = None
            else:
                delta[key] = a - b

        out["baseline"] = base["summary"]
        out["delta"] = delta

    report_path = args.out_dir / "report.json"
    report_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
