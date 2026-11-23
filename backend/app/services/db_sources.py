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
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import MetaData, Table, and_, create_engine, func, inspect, select
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


# Joined tables offered per connection. Each is one more table the planner reads.
MAX_JOINS = 6


@dataclass(frozen=True)
class Link:
    """A declared foreign key: each child row points at one parent row."""

    child: str
    child_columns: tuple[str, ...]
    parent: str
    parent_columns: tuple[str, ...]
    by_key: bool = False  # another declared key joins the same two tables

    @property
    def label(self) -> str:
        """The joined table's name, as the planner and the checks see it. When two
        keys join the same two tables (who pays, who receives), the child's key
        columns tell the two apart."""
        name = f"{self.child}+{self.parent}"
        return f"{name}_by_{'_'.join(self.child_columns)}" if self.by_key else name

    def to_dict(self) -> Dict[str, Any]:
        return {"child": self.child, "child_columns": list(self.child_columns),
                "parent": self.parent, "parent_columns": list(self.parent_columns), "by_key": self.by_key}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Link":
        return cls(str(data["child"]), tuple(data["child_columns"]), str(data["parent"]),
                   tuple(data["parent_columns"]), bool(data.get("by_key", False)))


def links_on(connection: Any, tables: List[str]) -> List[Link]:
    """Declared foreign keys among `tables`, child to parent. Only declared ones:
    a join guessed from column names would be a name rule, and often wrong.

    A key into another schema (Postgres) or another database (MySQL) is left
    out. The parent is reflected by its bare name, so a same-named table here
    would be joined instead: plausible, wrong numbers and no error."""
    inspector = inspect(connection)
    home = inspector.default_schema_name
    known = set(tables)
    found: List[Link] = []
    for table in tables:
        for fk in inspector.get_foreign_keys(table):
            parent = fk.get("referred_table")
            elsewhere = fk.get("referred_schema")
            child_columns = fk.get("constrained_columns") or []
            parent_columns = fk.get("referred_columns") or []
            if elsewhere and elsewhere != home:
                continue
            if (parent in known and parent != table and child_columns
                    and len(child_columns) == len(parent_columns)):
                found.append(Link(table, tuple(child_columns), parent, tuple(parent_columns)))
    pairs = Counter((link.child, link.parent) for link in found)
    return [replace(link, by_key=True) if pairs[(link.child, link.parent)] > 1 else link for link in found]


def foreign_keys(source: Any, tables: List[str]) -> List[Link]:
    """Declared foreign keys of a stored connection; none if they cannot be read."""
    engine = engine_for_source(source)
    try:
        with engine.connect() as connection:
            return links_on(connection, tables)
    except Exception as exc:  # noqa: BLE001 - a connection without readable keys still charts its tables
        logger.warning("[db_sources] could not read foreign keys for %s: %s", source.id, exc)
        return []
    finally:
        engine.dispose()

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
    """Each table of a connection, and each table joined to its parent through a
    declared foreign key, in the shape the data detective ranks.

    A connection is not itself a candidate: a chart is built from one table (or
    one joined table), so tables are what the detective and planner choose between.
    """
    entries = tables_with_columns(source, limit=max_tables)
    out: List[Dict[str, Any]] = [
        {
            "id": f"{source.id}:{entry['table']}",
            "name": f"{entry['table']} · {source.display_name}",
            "type": "db",
            "source_id": source.id,
            "table": entry["table"],
            "columns": entry["columns"],
        }
        for entry in entries
    ]
    columns = {entry["table"]: entry["columns"] for entry in entries}
    for link in foreign_keys(source, list(columns))[:MAX_JOINS]:
        out.append(
            {
                "id": f"{source.id}:{link.label}",
                "name": f"{link.label} · {source.display_name}",
                "type": "db",
                "source_id": source.id,
                "table": link.label,
                "join": link.to_dict(),
                "columns": columns[link.child] + [f"{link.parent}.{c}" for c in columns[link.parent]],
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


def load_joined_on(connection: Any, link: Link, limit: Optional[int] = None) -> pd.DataFrame:
    """The child table with its parent's columns: a left join on the declared
    key, so one row per child row. Parent columns are named `parent.column`, so
    nothing collides. Tables and columns come from reflection and are quoted by
    SQLAlchemy, never interpolated."""
    child = Table(link.child, MetaData(), autoload_with=connection)
    parent = Table(link.parent, MetaData(), autoload_with=connection)
    if limit is None:
        rows = connection.execute(select(func.count()).select_from(child)).scalar_one()
        if rows > MAX_ROWS:
            raise ValueError(
                f"{link.child} has {rows:,} rows, above the {MAX_ROWS:,} row limit for a chart. "
                "Chart a view that aggregates it instead."
            )
    on = and_(*[child.c[c] == parent.c[p] for c, p in zip(link.child_columns, link.parent_columns)])
    columns = [*child.c, *[column.label(f"{link.parent}.{column.name}") for column in parent.c]]
    query = select(*columns).select_from(child.outerjoin(parent, on))
    if limit is not None:
        query = query.limit(limit)
    return pd.read_sql(query, connection)


def load_joined(source: Any, link: Link, limit: Optional[int] = None) -> pd.DataFrame:
    """A joined table of a stored connection. Raises with a reason a user can act on."""
    engine = engine_for_source(source)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            present = set(inspector.get_table_names()) | set(inspector.get_view_names())
            for table in (link.child, link.parent):
                if table not in present:
                    raise ValueError(f"{table} is not a table in {source.db_name}")
            return load_joined_on(connection, link, limit)
    finally:
        engine.dispose()


def load_joined_by_id(source_id: str, link: Link, limit: Optional[int] = None) -> pd.DataFrame:
    """Same, from a source id: for code that runs outside a request session."""
    from app.core.database import SessionLocal
    from app.models.data_source import DataSource

    session = SessionLocal()
    try:
        source = session.query(DataSource).filter(DataSource.id == source_id).first()
        if source is None:
            raise ValueError("That database connection no longer exists")
        return load_joined(source, link, limit)
    finally:
        session.close()


def joined_schema(source: Any, link: Link, sample_rows: int = 3) -> Dict[str, Any]:
    """Columns, dtypes and a few rows of a joined table, in schema_of's shape."""
    try:
        frame = load_joined(source, link, limit=5)
    except Exception as exc:  # noqa: BLE001
        return {"error": _readable(exc)}
    return {
        "filename": f"{link.label} · {source.display_name}",
        "columns": list(frame.columns),
        "dtypes": {column: str(dtype) for column, dtype in frame.dtypes.items()},
        "sample": frame.head(sample_rows).to_dict(orient="records"),
    }


def split_candidate_id(candidate_id: str) -> Optional[tuple[str, str]]:
    """`<source id>:<table>` -> (source id, table), or None if it is not one."""
    if ":" not in candidate_id:
        return None
    source_id, table = candidate_id.split(":", 1)
    return (source_id, table) if source_id and table else None
