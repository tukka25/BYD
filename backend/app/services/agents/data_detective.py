import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.services.tools.langgraph_detective_agent import (
    build_detective_agent,
    build_dataframe_builder_agent,
    run_detective_agent,
    run_dataframe_builder_agent,
)


class DataDetective:
    """
    Two-agent data resolver:
    1) Tool-calling source detection agent
    2) Tool-calling dataframe builder agent
    """

    AUTO_PICK_THRESHOLD = 0.55

    def __init__(self, data_dir: str = "data", llm=None, use_cli_validation: bool = True):
        self.data_dir = Path(data_dir)
        self.llm = llm
        self.use_cli_validation = use_cli_validation
        self.keyword_tool_agent = None
        self.dataframe_builder_agent = None
        if self.llm is not None:
            self._build_chains()

    def _build_chains(self) -> None:
        self.keyword_tool_agent = build_detective_agent(
            llm=self.llm,
            data_dir=str(self.data_dir),
            db_url=os.getenv("DATABASE_URL", ""),
        )
        print("agent_1(tool-calling) is called")
        self.dataframe_builder_agent = build_dataframe_builder_agent(
            llm=self.llm,
            data_dir=str(self.data_dir),
            db_url=os.getenv("DATABASE_URL", ""),
        )
        print("agent_2(dataframe-builder tool-calling) is called")

    def list_files(self) -> List[str]:
        if not self.data_dir.exists():
            return []
        files: List[str] = []
        for file_name in os.listdir(self.data_dir):
            if file_name.lower().endswith((".csv", ".xlsx", ".xls")):
                files.append(file_name)
        return files

    def _normalize(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", (value or "").lower())

    def _tokenize(self, value: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", (value or "").lower()))

    def _resolve_path(self, filename_or_path: str) -> Path:
        candidate = Path(filename_or_path)
        if candidate.exists():
            return candidate.resolve()
        return (self.data_dir / filename_or_path).resolve()

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
                path = item.get("path") or item["name"]
                item["path"] = str(self._resolve_path(str(path)))
                if not item.get("columns"):
                    schema = self.get_schema(item["path"])
                    item["columns"] = schema.get("columns", [])
            prepared.append(item)
        return prepared

    def _score_candidate(self, query: str, candidate: Dict[str, Any]) -> float:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return 0.0

        name_tokens = self._tokenize(candidate.get("name", ""))
        column_tokens: set[str] = set()
        for col in candidate.get("columns", []):
            column_tokens |= self._tokenize(str(col))

        name_overlap = len(query_tokens & name_tokens) / max(1, len(query_tokens))
        col_overlap = len(query_tokens & column_tokens) / max(1, len(query_tokens))

        score = (0.7 * name_overlap) + (0.3 * col_overlap)
        return min(1.0, score)

    def get_schema(self, filename_or_path: str) -> Dict[str, Any]:
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

    def _find_candidate_by_source_hint(
        self,
        source_hint: str,
        candidates: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not source_hint:
            return None
        target = self._normalize(source_hint)
        target_name = self._normalize(Path(source_hint).name)
        for candidate in candidates:
            name_norm = self._normalize(str(candidate.get("name", "")))
            id_norm = self._normalize(str(candidate.get("id", "")))
            path_norm = self._normalize(str(candidate.get("path", "")))
            if target in {name_norm, id_norm, path_norm} or target_name in {name_norm, id_norm, path_norm}:
                return candidate
        return None

    def _fallback_pick_candidate(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None
        ranked = sorted(
            [{**c, "score": self._score_candidate(query, c)} for c in candidates],
            key=lambda item: item["score"],
            reverse=True,
        )
        return ranked[0] if ranked else None

    def detect_source(
        self,
        query: str,
        plan: Optional[Dict[str, Any]] = None,
        selected_source: Optional[str] = None,
        available_sources: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        candidates = self._prepare_candidates(available_sources)
        if not candidates:
            return {
                "selected": None,
                "confidence": 0.0,
                "reason": "no_candidates",
                "candidates": [],
                "analysis": {},
                "files_needed": {"count": 0, "names": []},
            }

        print("[detective] step_1: running source-detection agent (always)")
        available_source_names = [str(c.get("name", "")) for c in candidates if c.get("name")]
        source_hint_for_agent = f"available_sources={available_source_names}"
        source_detection_run = run_detective_agent(
            agent=self.keyword_tool_agent,
            query=f"{query}\nplan={str(plan or {})}\n{source_hint_for_agent}",
            selected_source=selected_source or "",
            thread_id="detective-source-detection-stage",
        )
        step1 = source_detection_run.get("structured_output", {}) or {}
        print(f"step1: {step1}")
        chosen_source = str(step1.get("chosen_source", "")).strip()
        required_fields = [str(v).strip() for v in step1.get("required_fields_for_next_step", []) if str(v).strip()]

        chosen_candidate = self._find_candidate_by_source_hint(chosen_source, candidates)
        if not chosen_candidate:
            checked_sources = [str(v).strip() for v in step1.get("checked_sources", []) if str(v).strip()]
            for hint in checked_sources:
                chosen_candidate = self._find_candidate_by_source_hint(hint, candidates)
                if chosen_candidate:
                    break
        if not chosen_candidate:
            chosen_candidate = self._fallback_pick_candidate(query, candidates)
        if not chosen_candidate:
            return {
                "selected": None,
                "confidence": float(step1.get("confidence", 0.0) or 0.0),
                "reason": "agent1_no_resolved_candidate",
                "candidates": candidates[:3],
                "analysis": step1,
                "files_needed": {"count": 0, "names": []},
                "tool_execution": {"source_detection": step1},
            }

        print("[detective] step_2: running dataframe-builder agent")
        source_for_step2 = str(chosen_candidate.get("name") or chosen_candidate.get("path") or chosen_source)
        dataframe_builder_run = run_dataframe_builder_agent(
            agent=self.dataframe_builder_agent,
            query=f"{query}\nplan={str(plan or {})}",
            chosen_source=source_for_step2,
            required_fields_for_next_step=required_fields,
            thread_id="detective-dataframe-builder-stage",
        )
        print(f"dataframe_builder_run: {dataframe_builder_run}")
        step2 = dataframe_builder_run.get("structured_output", {}) or {}
        confidence = float(step2.get("confidence", step1.get("confidence", 0.0)) or 0.0)
        selected_columns = [str(v) for v in step2.get("selected_columns", [])]
        missing_fields = [str(v) for v in step2.get("missing_fields", [])]
        dataframe_schema = dict(step2.get("dataframe_schema", {}) or {})
        df_query_or_code = str(step2.get("df_query_or_code", ""))
        load_type = str(step2.get("load_type", ""))

        analysis = {
            "analysis_keywords": list(self._tokenize(query))[:20],
            "filename_hints": [str(chosen_candidate.get("name", ""))],
            "datasource_keywords": required_fields,
            "intent_summary": str(step1.get("rationale", "source_detection_complete")),
        }

        if selected_columns or confidence >= self.AUTO_PICK_THRESHOLD:
            return {
                "selected": chosen_candidate,
                "confidence": confidence,
                "reason": "agent2_dataframe_builder_selected",
                "candidates": [chosen_candidate],
                "analysis": analysis,
                "tool_execution": {
                    "source_detection": step1,
                    "dataframe_builder": step2,
                },
                "files_needed": {"count": 1, "names": [chosen_candidate.get("name")]},
                "dataframe_plan": {
                    "schema": dataframe_schema,
                    "query_or_code": df_query_or_code,
                    "load_type": load_type,
                    "selected_columns": selected_columns,
                    "missing_fields": missing_fields,
                },
                "stage_sequence": [
                    "step_1_source_detection_agent",
                    "step_2_dataframe_builder_agent",
                ],
            }

        return {
            "selected": None,
            "confidence": confidence,
            "reason": "agent2_dataframe_builder_ambiguous",
            "candidates": [chosen_candidate],
            "analysis": analysis,
            "tool_execution": {
                "source_detection": step1,
                "dataframe_builder": step2,
                "missing_fields": missing_fields,
                "selected_columns": selected_columns,
            },
            "files_needed": {"count": 1, "names": [chosen_candidate.get("name")]},
            "dataframe_plan": {
                "schema": dataframe_schema,
                "query_or_code": df_query_or_code,
                "load_type": load_type,
                "selected_columns": selected_columns,
                "missing_fields": missing_fields,
            },
            "stage_sequence": [
                "step_1_source_detection_agent",
                "step_2_dataframe_builder_agent",
            ],
        }
