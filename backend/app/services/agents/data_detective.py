"""Resolves which data source answers a question, and reads its schema.

Rewritten for a small local model. The previous version ran **two ReAct
tool-calling agents** per request — one to choose a source, one to "build a
dataframe plan". Three problems, in order of severity:

1. **Multi-turn tool calling is the hardest thing to ask of a small model.** It
   needs the model to emit well-formed tool calls, read results, and decide when
   to stop, several times over. The old code already carried keyword-overlap
   fallbacks for when the agents returned nothing usable, which is the tell.
2. **Both agents used a fixed `thread_id`** (`"detective-source-detection-stage"`
   and `"detective-dataframe-builder-stage"`) against a `MemorySaver`. Every
   request appended to the *same* conversation thread, so memory grew without
   bound and request N could see request N-1's messages — a correctness and a
   privacy problem, not just a leak.
3. **Two LLM round-trips** before a single line of chart code was written.

What it does now, cheapest path first:

* An explicitly selected source is used directly — **no LLM call at all**, which
  is the common case when a user picks a file in the UI.
* One candidate means one answer.
* Otherwise candidates are ranked by token overlap between the question and each
  source's name and columns. A clear winner is taken as-is.
* Only a genuine near-tie reaches the model, as **one single-shot
  multiple-choice question** ("reply with only the number"). That is the shape
  small models are reliable at, and there is no tool protocol to get wrong.
* If even that is unusable, the top-ranked candidate wins.

Column selection is deliberately not asked of the model either. The chartist is
fine-tuned to read a schema block and choose its own columns — that is precisely
what its 1,926 training rows taught it — so a second opinion here would add a
round-trip and a disagreement to resolve.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Splits a run of characters into words, including across camelCase. Without
# this, "squareFootage" tokenises as one opaque token and a question asking about
# "square footage" can never overlap it -- which made every candidate score 0.0
# and the ranking fall back to alphabetical order.
_WORDS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")

# Dropped from the QUESTION only. They match nothing and inflate the denominator,
# so a perfect three-word match on a seven-word question scored 0.43.
_STOPWORDS = frozenset(
    """a an and are as at by for from how in into is it me my of on or over per
    show the their there these this to us using versus vs what when which with
    chart graph plot plots please give make build display view data dataset""".split()
)


class DataDetective:
    """Picks a data source deterministically, asking the model only on a tie."""

    # How far ahead the best candidate must be to win without asking the model.
    AUTO_PICK_MARGIN = 0.15
    # Candidates offered to the model when it does have to choose.
    MAX_CHOICES = 6

    def __init__(self, data_dir: str = "data", llm=None, use_cli_validation: bool = True):
        self.data_dir = Path(data_dir)
        self.llm = llm
        self.use_cli_validation = use_cli_validation

    # --- file helpers ----------------------------------------------------

    def list_files(self) -> List[str]:
        if not self.data_dir.exists():
            return []
        return sorted(
            name
            for name in (p.name for p in self.data_dir.iterdir() if p.is_file())
            if name.lower().endswith((".csv", ".xlsx", ".xls"))
        )

    def _normalize(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", (value or "").lower())

    def _tokenize(self, value: str) -> set[str]:
        """Word tokens, camelCase-aware, with crude singularisation.

        `snapshotMonth` -> {snapshot, month}; `salePrice` -> {sale, price};
        `property_sales` -> {property, sales, sale}. The singular form is added
        alongside the plural so "sale price" matches a `sales` column.
        """
        tokens: set[str] = set()
        for part in _WORDS.findall(value or ""):
            word = part.lower()
            if len(word) < 2:
                continue
            tokens.add(word)
            if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
                tokens.add(word[:-1])
        return tokens

    def _query_tokens(self, query: str) -> set[str]:
        """Question tokens with stopwords removed, so scores mean something."""
        return {t for t in self._tokenize(query) if t not in _STOPWORDS}

    def _resolve_path(self, filename_or_path: str) -> Path:
        candidate = Path(filename_or_path)
        if candidate.exists():
            return candidate.resolve()
        return (self.data_dir / filename_or_path).resolve()

    def get_schema(self, filename_or_path: str) -> Dict[str, Any]:
        """Columns, dtypes and three sample rows — the chartist's whole input."""
        filepath = self._resolve_path(filename_or_path)
        if not filepath.exists():
            return {"error": f"File {filename_or_path} not found"}
        try:
            suffix = filepath.suffix.lower()
            if suffix == ".csv":
                df = pd.read_csv(filepath, nrows=5)
            elif suffix in (".xlsx", ".xls"):
                df = pd.read_excel(filepath, nrows=5)
            else:
                return {"error": "Unsupported file format"}
            return {
                "filename": filepath.name,
                "filepath": str(filepath),
                "columns": list(df.columns),
                "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
                "sample": df.head(3).to_dict(orient="records"),
            }
        except Exception as exc:
            return {"error": str(exc)}

    # --- candidates ------------------------------------------------------

    def _build_file_candidates(self) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for filename in self.list_files():
            full_path = self._resolve_path(filename)
            schema = self.get_schema(str(full_path))
            candidates.append(
                {
                    "id": filename,
                    "name": filename,
                    "type": "file",
                    "path": str(full_path),
                    "columns": schema.get("columns", []),
                }
            )
        return candidates

    def _prepare_candidates(
        self, available_sources: Optional[List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        if not available_sources:
            return self._build_file_candidates()
        prepared: List[Dict[str, Any]] = []
        for source in available_sources:
            item = dict(source)
            name = item.get("name") or item.get("id") or ""
            item["name"] = str(name)
            item["id"] = str(item.get("id") or name)
            item["type"] = str(item.get("type") or "file")
            if item["type"] == "file":
                item["path"] = str(self._resolve_path(str(item.get("path") or item["name"])))
                if not item.get("columns"):
                    item["columns"] = self.get_schema(item["path"]).get("columns", [])
            prepared.append(item)
        return prepared

    def _score_candidate(self, query: str, candidate: Dict[str, Any]) -> float:
        """Overlap between the question and a source's name and column words.

        Columns are weighted above the filename: a question names the fields it
        wants far more often than it names the file, and "sessions by weekday"
        should find web_traffic.csv on its columns alone.
        """
        query_tokens = self._query_tokens(query)
        if not query_tokens:
            return 0.0
        # Stem of the filename, so ".csv" does not count as a word.
        name_tokens = self._tokenize(Path(str(candidate.get("name", ""))).stem)
        column_tokens: set[str] = set()
        for col in candidate.get("columns", []):
            column_tokens |= self._tokenize(str(col))
        name_overlap = len(query_tokens & name_tokens) / len(query_tokens)
        col_overlap = len(query_tokens & column_tokens) / len(query_tokens)
        return min(1.0, (0.4 * name_overlap) + (0.6 * col_overlap))

    def _find_candidate_by_source_hint(
        self, source_hint: str, candidates: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not source_hint:
            return None
        target = self._normalize(source_hint)
        target_name = self._normalize(Path(source_hint).name)
        for candidate in candidates:
            fields = {
                self._normalize(str(candidate.get("name", ""))),
                self._normalize(str(candidate.get("id", ""))),
                self._normalize(str(candidate.get("path", ""))),
            }
            if target in fields or target_name in fields:
                return candidate
        return None

    # --- the one LLM call ------------------------------------------------

    def _llm_pick(self, query: str, ranked: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Single-shot multiple choice. Returns None if the reply is unusable.

        Deliberately not tool calling and not JSON: a number is the smallest,
        most reliable thing to ask a small model for, and it either parses or it
        does not.
        """
        if self.llm is None or len(ranked) < 2:
            return None
        choices = ranked[: self.MAX_CHOICES]
        listing = "\n".join(
            f"{i}. {c.get('name')} — columns: {', '.join(str(x) for x in (c.get('columns') or [])[:12])}"
            for i, c in enumerate(choices, start=1)
        )
        prompt = (
            "Pick the data source that can answer the question.\n"
            "Reply with only the number, nothing else.\n\n"
            f"Question: {query}\n\n"
            f"{listing}\n"
        )
        try:
            reply = self.llm.invoke(prompt)
            text = getattr(reply, "content", reply)
            match = re.search(r"\d+", str(text))
            if not match:
                logger.warning("[detective] tiebreak reply had no number: %r", str(text)[:120])
                return None
            index = int(match.group()) - 1
            if 0 <= index < len(choices):
                return choices[index]
            logger.warning("[detective] tiebreak number %s out of range", index + 1)
        except Exception:
            logger.exception("[detective] tiebreak call failed")
        return None

    # --- result shaping --------------------------------------------------

    def _selected_columns(self, query: str, candidate: Dict[str, Any]) -> List[str]:
        """Columns the question mentions, as a hint only. Not a restriction."""
        query_tokens = self._query_tokens(query)
        return [
            str(col)
            for col in (candidate.get("columns") or [])
            if self._tokenize(str(col)) & query_tokens
        ]

    def _decision(
        self,
        candidate: Dict[str, Any],
        confidence: float,
        reason: str,
        query: str,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        logger.info(
            "[detective] selected=%s via=%s confidence=%.2f of %d candidate(s)",
            candidate.get("name"),
            reason,
            confidence,
            len(candidates),
        )
        return {
            "selected": candidate,
            "confidence": round(float(confidence), 3),
            "reason": reason,
            "candidates": [candidate],
            "analysis": {
                "analysis_keywords": sorted(self._query_tokens(query))[:20],
                "filename_hints": [str(candidate.get("name", ""))],
                "intent_summary": reason,
            },
            "files_needed": {"count": 1, "names": [candidate.get("name")]},
            "dataframe_plan": {
                "selected_columns": self._selected_columns(query, candidate),
                # Left empty on purpose: we cannot know which fields a user
                # wanted that the data lacks, and the chartist was trained on
                # missing-field cases, so it copes without being told.
                "missing_fields": [],
                "load_type": str(candidate.get("type", "file")),
                "schema": {},
            },
            "stage_sequence": [f"resolve_source:{reason}"],
        }

    # --- entry point -----------------------------------------------------

    def detect_source(
        self,
        query: str,
        plan: Optional[Dict[str, Any]] = None,
        selected_source: Optional[str] = None,
        available_sources: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        candidates = self._prepare_candidates(available_sources)
        if not candidates:
            logger.warning("[detective] no candidates under %s", self.data_dir)
            return {
                "selected": None,
                "confidence": 0.0,
                "reason": "no_candidates",
                "candidates": [],
                "analysis": {},
                "files_needed": {"count": 0, "names": []},
                "stage_sequence": ["resolve_source:no_candidates"],
            }

        # 1. The user already told us. Cheapest and most reliable signal there is.
        if selected_source:
            hit = self._find_candidate_by_source_hint(selected_source, candidates)
            if hit:
                return self._decision(hit, 1.0, "explicit_selection", query, candidates)
            logger.warning(
                "[detective] selected_source=%r matched nothing; falling back to ranking",
                selected_source,
            )

        if len(candidates) == 1:
            return self._decision(candidates[0], 1.0, "only_candidate", query, candidates)

        # 2. Deterministic ranking.
        ranked = sorted(
            ({**c, "score": self._score_candidate(query, c)} for c in candidates),
            key=lambda item: item["score"],
            reverse=True,
        )
        top, runner_up = ranked[0], ranked[1]
        if top["score"] > 0.0 and (top["score"] - runner_up["score"]) >= self.AUTO_PICK_MARGIN:
            return self._decision(top, top["score"], "keyword_margin", query, candidates)

        # 3. A real tie. One question, one number.
        picked = self._llm_pick(query, ranked)
        if picked is not None:
            return self._decision(picked, max(top["score"], 0.5), "llm_tiebreak", query, candidates)

        # 4. Best effort beats refusing: the top candidate still ranked highest.
        return self._decision(top, top["score"], "keyword_best_effort", query, candidates)
