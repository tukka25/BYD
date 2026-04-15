from __future__ import annotations

import ast
import re
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Set, Tuple

from .io_utils import normalize_text


KEYWORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_+-]{2,}")
STOPWORDS = {
    "create", "build", "plotly", "python", "return", "only", "code", "example",
    "details", "focus", "including", "with", "and", "for", "the", "this", "that",
    "from", "into", "using", "show", "make", "visualization", "chart", "plot",
}


def extract_keywords(text: str) -> Set[str]:
    words = {w.lower() for w in KEYWORD_RE.findall(text)}
    return {w for w in words if w not in STOPWORDS}


def keyword_overlap(a: str, b: str) -> float:
    ka, kb = extract_keywords(a), extract_keywords(b)
    if not ka:
        return 1.0
    return len(ka & kb) / max(1, len(ka))


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(a=normalize_text(a), b=normalize_text(b)).ratio()


def validate_rephrase(original_user: str, rephrased_user: str, cfg: Dict) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    v = cfg["validation"]

    if not rephrased_user or len(rephrased_user) < v["min_rephrase_chars"]:
        reasons.append("rephrase_too_short")
    if len(rephrased_user) > v["max_rephrase_chars"]:
        reasons.append("rephrase_too_long")

    overlap = keyword_overlap(original_user, rephrased_user)
    if overlap < v["intent_min_keyword_overlap"]:
        reasons.append(f"intent_overlap_low:{overlap:.2f}")

    sim = similarity(original_user, rephrased_user)
    if sim > v["max_user_similarity"]:
        reasons.append(f"too_similar:{sim:.3f}")

    return len(reasons) == 0, reasons


def validate_python_plotly_code(code: str, cfg: Dict) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    v = cfg["validation"]
    stripped = code.strip()

    if len(stripped) < v["min_code_chars"]:
        reasons.append("code_too_short")
    if len(stripped) > v["max_code_chars"]:
        reasons.append("code_too_long")

    try:
        tree = ast.parse(stripped)
    except SyntaxError:
        reasons.append("python_syntax_error")
        return False, reasons

    imports_plotly = False
    assigns_fig = False
    render_call = False

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = []
            if isinstance(node, ast.Import):
                names = [n.name for n in node.names]
            else:
                names = [node.module or ""]
            if any(name.startswith("plotly") for name in names):
                imports_plotly = True

        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "fig":
                    assigns_fig = True

        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr in {"show", "write_html", "to_html"}:
                render_call = True

    if v["require_plotly_import"] and not imports_plotly:
        reasons.append("missing_plotly_import")
    if v["require_figure_variable"] and not assigns_fig:
        reasons.append("missing_fig_assignment")
    if v["require_render_call"] and not render_call:
        reasons.append("missing_render_call")

    return len(reasons) == 0, reasons


def is_duplicate_pair(user: str, assistant: str, seen_pairs: Set[str]) -> bool:
    pair_key = normalize_text(user) + "\n###\n" + normalize_text(assistant)
    if pair_key in seen_pairs:
        return True
    seen_pairs.add(pair_key)
    return False


def seed_seen_pairs(rows: Iterable[Dict], seen_pairs: Set[str]) -> None:
    for row in rows:
        messages = row.get("messages", [])
        user = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
        assistant = next((m.get("content", "") for m in messages if m.get("role") == "assistant"), "")
        _ = is_duplicate_pair(user, assistant, seen_pairs)
