from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, inspect, text

SUPPORTED_FILE_EXTENSIONS = (".csv", ".xlsx", ".xls")


def _to_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, default=str)


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (value or "").lower()))


def _list_files(data_dir: Path) -> List[Path]:
    if not data_dir.exists():
        return []
    return [
        file_path
        for file_path in sorted(data_dir.iterdir())
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_FILE_EXTENSIONS
    ]


def _read_source_to_df(
    source: str,
    data_dir: Path,
    db_url: str = "",
    limit_rows: int = 200,
) -> pd.DataFrame:
    if source.startswith("db:"):
        if not db_url:
            raise ValueError("db_url is required for db:<table_name> source")
        table_name = source.replace("db:", "", 1).strip()
        if not table_name:
            raise ValueError("db source must be db:<table_name>")
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table_name):
            raise ValueError("Invalid table name")
        engine = create_engine(db_url)
        query = text(f"SELECT * FROM {table_name} LIMIT :limit")
        return pd.read_sql(query, engine, params={"limit": limit_rows})

    source_path = Path(source)
    if not source_path.exists():
        source_path = data_dir / source
    if not source_path.exists():
        raise FileNotFoundError(f"Source not found: {source}")

    suffix = source_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(source_path, nrows=limit_rows)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(source_path, nrows=limit_rows)
    raise ValueError(f"Unsupported source format: {source}")


def list_sources(data_dir: str, db_url: str = "") -> str:
    """List available file sources from a directory and database tables if db_url is provided."""
    root = Path(data_dir)
    files = _list_files(root)
    payload: Dict[str, Any] = {
        "data_dir": str(root.resolve()),
        "files": [
            {"name": f.name, "path": str(f.resolve()), "source": f.name, "type": "file"}
            for f in files
        ],
        "db_tables": [],
    }

    if db_url:
        try:
            engine = create_engine(db_url)
            inspector = inspect(engine)
            payload["db_tables"] = [
                {"name": table, "source": f"db:{table}", "type": "db"}
                for table in inspector.get_table_names()
            ]
        except Exception as exc:
            payload["db_error"] = str(exc)

    return _to_json(payload)


def read_source_headers(source: str, data_dir: str, db_url: str = "") -> str:
    """Read headers/columns and preview rows for CSV, Excel, or db:<table_name> source."""
    try:
        df = _read_source_to_df(source=source, data_dir=Path(data_dir), db_url=db_url, limit_rows=5)
        return _to_json(
            {
                "source": source,
                "columns": list(df.columns),
                "sample": df.head(2).to_dict(orient="records"),
            }
        )
    except Exception as exc:
        return _to_json({"source": source, "error": str(exc)})


def verify_source_matches_query(
    source: str,
    query: str,
    data_dir: str,
    db_url: str = "",
    limit_rows: int = 200,
) -> str:
    """Verify if a source likely contains requested information using header/value token overlap confidence."""
    try:
        df = _read_source_to_df(
            source=source,
            data_dir=Path(data_dir),
            db_url=db_url,
            limit_rows=limit_rows,
        )
    except Exception as exc:
        return _to_json({"source": source, "confidence": 0.0, "error": str(exc)})

    query_tokens = _tokens(query)
    header_tokens: set[str] = set()
    for col in df.columns:
        header_tokens |= _tokens(str(col))

    sample_blob = " ".join(df.head(20).astype(str).fillna("").values.flatten().tolist())
    value_tokens = _tokens(sample_blob)

    header_overlap = len(query_tokens & header_tokens) / max(1, len(query_tokens))
    value_overlap = len(query_tokens & value_tokens) / max(1, len(query_tokens))
    confidence = min(1.0, (0.7 * header_overlap) + (0.3 * value_overlap))

    return _to_json(
        {
            "source": source,
            "confidence": confidence,
            "matched_header_tokens": sorted(query_tokens & header_tokens),
            "matched_value_tokens": sorted(query_tokens & value_tokens),
            "columns": list(df.columns),
        }
    )


class ListSourcesInput(BaseModel):
    limit: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of source entries to return",
    )


class ReadHeadersInput(BaseModel):
    source: str = Field(
        description="File source name/path or db source in format db:<table_name>"
    )
    sample_rows: int = Field(
        default=2,
        ge=1,
        le=20,
        description="Number of sample rows to include",
    )


class VerifySourceInput(BaseModel):
    source: str = Field(
        description="File source name/path or db source in format db:<table_name>"
    )
    query: str = Field(description="User analytical query to validate relevance against")
    limit_rows: int = Field(
        default=200,
        ge=10,
        le=2000,
        description="Number of rows to scan for relevance scoring",
    )


class BuildDataFramePlanInput(BaseModel):
    source: str = Field(
        description="File source name/path or db source in format db:<table_name>"
    )
    required_fields: List[str] = Field(
        default_factory=list,
        description="Required fields to include in dataframe plan",
    )
    sample_rows: int = Field(
        default=200,
        ge=1,
        le=5000,
        description="Target row count for dataframe preview/load",
    )


def build_dataframe_load_plan(
    source: str,
    data_dir: str,
    db_url: str = "",
    required_fields: Optional[List[str]] = None,
    sample_rows: int = 200,
) -> str:
    """
    Build a deterministic dataframe loading plan for CSV/Excel/DB.
    Returns pandas/python loading guidance and SQL query when source is DB.
    """
    required_fields = required_fields or []
    try:
        df = _read_source_to_df(
            source=source,
            data_dir=Path(data_dir),
            db_url=db_url,
            limit_rows=max(10, sample_rows),
        )
    except Exception as exc:
        return _to_json({"source": source, "error": str(exc)})

    available_columns = [str(c) for c in df.columns]
    selected_columns = []
    missing_fields = []
    for field in required_fields:
        field_norm = str(field).strip().lower()
        matched = next((col for col in available_columns if col.lower() == field_norm), None)
        if matched is None:
            matched = next((col for col in available_columns if field_norm in col.lower()), None)
        if matched:
            if matched not in selected_columns:
                selected_columns.append(matched)
        else:
            missing_fields.append(field)

    if not selected_columns:
        selected_columns = available_columns

    if source.startswith("db:"):
        table_name = source.replace("db:", "", 1).strip()
        cols_sql = ", ".join([f'"{c}"' for c in selected_columns]) if selected_columns else "*"
        sql_query = f'SELECT {cols_sql} FROM "{table_name}" LIMIT {int(sample_rows)};'
        pandas_code = (
            "from sqlalchemy import create_engine\n"
            "import pandas as pd\n"
            "engine = create_engine(DB_URL)\n"
            f'df = pd.read_sql("{sql_query}", engine)'
        )
        load_type = "sql"
    else:
        source_path = Path(source)
        if not source_path.exists():
            source_path = Path(data_dir) / source
        suffix = source_path.suffix.lower()
        if suffix == ".csv":
            pandas_code = (
                "import pandas as pd\n"
                f'df = pd.read_csv("{source_path}", usecols={selected_columns})'
            )
            load_type = "csv"
        else:
            pandas_code = (
                "import pandas as pd\n"
                f'df = pd.read_excel("{source_path}", usecols={selected_columns})'
            )
            load_type = "excel"
        sql_query = ""

    return _to_json(
        {
            "source": source,
            "load_type": load_type,
            "selected_columns": selected_columns,
            "missing_fields": missing_fields,
            "sql_query": sql_query,
            "pandas_code": pandas_code,
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items() if col in selected_columns},
            "sample": df[selected_columns].head(2).to_dict(orient="records") if selected_columns else [],
        }
    )


def get_detective_tools(data_dir: str, db_url: str = "") -> List[BaseTool]:
    """
    Build structured tools with bound runtime context (data_dir, db_url).
    Agent only provides task-specific fields (source/query), not infra fields.
    """
    root = str(Path(data_dir))

    def _list_sources_tool(limit: int = 100) -> str:
        payload = json.loads(list_sources(data_dir=root, db_url=db_url))
        payload["files"] = payload.get("files", [])[:limit]
        payload["db_tables"] = payload.get("db_tables", [])[:limit]
        return _to_json(payload)

    def _read_headers_tool(source: str, sample_rows: int = 2) -> str:
        try:
            df = _read_source_to_df(
                source=source,
                data_dir=Path(root),
                db_url=db_url,
                limit_rows=max(5, sample_rows),
            )
            return _to_json(
                {
                    "source": source,
                    "columns": list(df.columns),
                    "sample": df.head(sample_rows).to_dict(orient="records"),
                }
            )
        except Exception as exc:
            return _to_json({"source": source, "error": str(exc)})

    def _verify_source_tool(source: str, query: str, limit_rows: int = 200) -> str:
        return verify_source_matches_query(
            source=source,
            query=query,
            data_dir=root,
            db_url=db_url,
            limit_rows=limit_rows,
        )

    def _build_df_plan_tool(source: str, required_fields: List[str], sample_rows: int = 200) -> str:
        return build_dataframe_load_plan(
            source=source,
            data_dir=root,
            db_url=db_url,
            required_fields=required_fields,
            sample_rows=sample_rows,
        )

    return [
        StructuredTool.from_function(
            func=_list_sources_tool,
            name="list_sources",
            description=(
                "List available file sources (.csv/.xlsx/.xls) and DB tables "
                "from current workspace context."
            ),
            args_schema=ListSourcesInput,
        ),
        StructuredTool.from_function(
            func=_read_headers_tool,
            name="read_source_headers",
            description=(
                "Read headers and sample rows from source. "
                "Use to inspect schema before deciding relevance."
            ),
            args_schema=ReadHeadersInput,
        ),
        StructuredTool.from_function(
            func=_verify_source_tool,
            name="verify_source_matches_query",
            description=(
                "Score source relevance for user query using header/value overlap. "
                "Use to disambiguate between multiple sources."
            ),
            args_schema=VerifySourceInput,
        ),
        StructuredTool.from_function(
            func=_build_df_plan_tool,
            name="build_dataframe_load_plan",
            description=(
                "Generate dataframe load/query plan for chosen source (CSV/Excel/DB), "
                "including selected columns, missing fields, SQL query (for DB), "
                "and pandas loading code."
            ),
            args_schema=BuildDataFramePlanInput,
        ),
    ]


__all__ = [
    "list_sources",
    "read_source_headers",
    "verify_source_matches_query",
    "build_dataframe_load_plan",
    "get_detective_tools",
]
