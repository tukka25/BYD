"""Reading a report's data out of a SQL database instead of a file.

The rest of the pipeline has one contract: a pandas DataFrame named `df`. A
database source honours exactly that contract — a table is loaded into a
DataFrame and from there the detective, the chartist and the executor cannot
tell where it came from. Nothing downstream needed changing.

Only databases whose driver actually installs cleanly are offered, because a
connection form listing engines the server cannot reach is a form that lies.

Identifiers are never interpolated into SQL: tables are reflected and queried
through SQLAlchemy, which quotes them, and a table is checked against the live
table list before it is reflected at all.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL

from app.core.security import decrypt_secret

logger = logging.getLogger(__name__)

# Charting reads a whole table, because a LIMIT would silently chart a subset
# and call it a total. Above this we refuse and say the row count instead.
MAX_ROWS = 500_000

# How many tables of one connection are offered to the detective. A chart is
# built from one table; enumerating hundreds costs a metadata query each.
MAX_TABLES = 40

CONNECT_TIMEOUT_SECONDS = 6


@dataclass(frozen=True)
class DatabaseKind:
    id: str
    label: str
    driver: str
    default_port: int
    module: str


SUPPORTED: Dict[str, DatabaseKind] = {
    "postgresql": DatabaseKind(
        id="postgresql",
        label="PostgreSQL",
        driver="postgresql+psycopg2",
        default_port=5432,
        module="psycopg2",
    ),
    "mysql": DatabaseKind(
        id="mysql",
        label="MySQL / MariaDB",
        driver="mysql+pymysql",
        default_port=3306,
        module="pymysql",
    ),
}


def driver_available(kind: DatabaseKind) -> bool:
    try:
        __import__(kind.module)
        return True
    except ImportError:
        return False


def catalogue() -> List[Dict[str, Any]]:
    """The databases this server can actually connect to, for the UI to offer."""
    return [
        {
            "id": kind.id,
            "label": kind.label,
            "default_port": kind.default_port,
            "available": driver_available(kind),
        }
        for kind in SUPPORTED.values()
    ]


def make_engine(
    *,
    db_type: str,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
) -> Engine:
    kind = SUPPORTED.get(db_type)
    if kind is None:
        raise ValueError(f"{db_type} is not one of the databases this server supports")
    if not driver_available(kind):
        raise ValueError(
            f"The driver for {kind.label} ({kind.module}) is not installed on the server"
        )

    url = URL.create(
        kind.driver,
        username=username,
        password=password,
        host=host,
        port=port or kind.default_port,
        database=database,
    )
    # Both drivers spell the timeout the same way, which is why only these two
    # are offered without per-driver special-casing.
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


def probe(
    *,
    db_type: str,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
) -> Dict[str, Any]:
    """Connect for real and report what is there. Never raises."""
    try:
        engine = make_engine(
            db_type=db_type,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "tables": []}

    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            tables = sorted(inspector.get_table_names())
            views = sorted(inspector.get_view_names())
        return {
            "ok": True,
            "error": None,
            "tables": (tables + views)[:MAX_TABLES],
            "table_count": len(tables) + len(views),
        }
    except Exception as exc:  # noqa: BLE001 - the reason is the whole answer here
        logger.info("[db_sources] probe failed for %s@%s: %s", db_type, host, exc)
        return {"ok": False, "error": _readable(exc), "tables": []}
    finally:
        engine.dispose()


def _readable(exc: Exception) -> str:
    """The driver's first line, which names the real problem; the rest is noise."""
    text = str(exc).strip()
    first = text.splitlines()[0] if text else exc.__class__.__name__
    return first[:300]


def engine_for_source(source: Any) -> Engine:
    """An engine for a stored DataSource row, decrypting its password."""
    return make_engine(
        db_type=source.db_type or "",
        host=source.db_host or "",
        port=source.db_port or 0,
        database=source.db_name or "",
        username=source.db_username or "",
        password=decrypt_secret(source.db_password_encrypted or ""),
    )


def tables_with_columns(source: Any, limit: int = MAX_TABLES) -> List[Dict[str, Any]]:
    """Table names and their columns — metadata only, no rows read."""
    engine = engine_for_source(source)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            names = (sorted(inspector.get_table_names()) + sorted(inspector.get_view_names()))[
                :limit
            ]
            return [
                {"table": name, "columns": [c["name"] for c in inspector.get_columns(name)]}
                for name in names
            ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[db_sources] could not list tables for %s: %s", source.id, exc)
        return []
    finally:
        engine.dispose()


def load_table(source: Any, table: str) -> pd.DataFrame:
    """One table as a DataFrame. Raises with a reason a user can act on."""
    engine = engine_for_source(source)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            if table not in set(inspector.get_table_names()) | set(inspector.get_view_names()):
                raise ValueError(f"{table} is not a table in {source.db_name}")

            reflected = Table(table, MetaData(), autoload_with=connection)

            rows = connection.execute(select(func.count()).select_from(reflected)).scalar_one()
            if rows > MAX_ROWS:
                raise ValueError(
                    f"{table} has {rows:,} rows. A chart reads the whole table so the totals "
                    f"are real, and this one is above the {MAX_ROWS:,} row limit. Chart a view "
                    "that aggregates it instead."
                )

            return pd.read_sql(select(reflected), connection)
    finally:
        engine.dispose()


def load_table_by_id(source_id: str, table: str) -> pd.DataFrame:
    """Same, from a source id — for code that runs outside a request session."""
    from app.core.database import SessionLocal
    from app.models.data_source import DataSource

    session = SessionLocal()
    try:
        source = session.query(DataSource).filter(DataSource.id == source_id).first()
        if source is None:
            raise ValueError("That database connection no longer exists")
        return load_table(source, table)
    finally:
        session.close()


def candidates_for(source: Any, max_tables: int = MAX_TABLES) -> List[Dict[str, Any]]:
    """Each table of a connection, in the shape the data detective ranks.

    A connection is not itself a candidate: a chart is built from one table, so
    the tables are what the detective chooses between.
    """
    out: List[Dict[str, Any]] = []
    for entry in tables_with_columns(source, limit=max_tables):
        out.append(
            {
                "id": f"{source.id}:{entry['table']}",
                "name": f"{entry['table']} · {source.display_name}",
                "type": "db",
                "source_id": source.id,
                "table": entry["table"],
                "columns": entry["columns"],
            }
        )
    return out


def schema_of(source: Any, table: str, sample_rows: int = 3) -> Dict[str, Any]:
    """Columns, dtypes and a few rows — the same shape the file path returns."""
    engine = engine_for_source(source)
    try:
        with engine.connect() as connection:
            reflected = Table(table, MetaData(), autoload_with=connection)
            frame = pd.read_sql(select(reflected).limit(5), connection)
        return {
            "filename": f"{table} · {source.display_name}",
            "columns": list(frame.columns),
            "dtypes": {col: str(dtype) for col, dtype in frame.dtypes.items()},
            "sample": frame.head(sample_rows).to_dict(orient="records"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": _readable(exc)}
    finally:
        engine.dispose()


def split_candidate_id(candidate_id: str) -> Optional[tuple[str, str]]:
    """`<source id>:<table>` -> (source id, table), or None if it is not one."""
    if ":" not in candidate_id:
        return None
    source_id, table = candidate_id.split(":", 1)
    return (source_id, table) if source_id and table else None
