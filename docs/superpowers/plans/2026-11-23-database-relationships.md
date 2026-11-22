# Database Relationships and Joined Tables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find the foreign keys a database connection declares, tell the analyst and planner about them, and let a chart plan use a joined table (each child row with its parent's columns), which the chartist charts as one DataFrame.

**Architecture:** Today a database connection is a list of separate tables: `db_sources.candidates_for` offers each table, the planner plans one table per chart, and nothing reads foreign keys. This plan reads declared foreign keys with SQLAlchemy's inspector and turns each child-to-parent key into one more table, named `orders+customers`. That table is loaded with a left join that keeps one row per child row, with the parent's columns renamed `customers.region`. To everything downstream (profile, planner checks, chartist, executor) it is a table like any other. A short "Joined tables you can use" section tells the planner what each join means.

**Tech Stack:** SQLAlchemy 2 Core (reflection, `outerjoin`, labels), pandas `read_sql`, PostgreSQL and MySQL (production), SQLite in memory (tests), pytest.

**Order:** run this after `2026-11-23-planner-tools-and-memory.md`. It uses that plan's `architect.load_frame` (its Task 2) and `planning_contract.with_context` (its Task 5).

## Global Constraints

- Only declared foreign keys are used. No join is guessed from column names: that would be a name rule, and the project forbids them (AGENTS.md: "Never add name rules back").
- Joins go from child to parent only, one hop, as a left join on the declared key, so a joined table has exactly the child's row count. Keys from a table to itself are skipped.
- Identifiers are never interpolated into SQL: tables are reflected, columns come from reflection, and SQLAlchemy quotes them, as `db_sources` already does.
- `MAX_ROWS = 500_000` applies to the child table of a join, exactly as to a single table.
- At most `MAX_JOINS = 6` joined tables per connection, and at most `MAX_LINKS = 4` lines about them in a prompt.
- Never hardcode charts; every chart is the model's own code.
- Backend tests: `cd backend && .venv/bin/python -m pytest -q tests`. Three failures in `tests/test_chartist_contract.py` predate this plan, and no new failure is allowed.
- Commit after every task, with messages ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File Structure

- Modify `backend/app/services/db_sources.py`: the `Link` dataclass, `links_on`, `foreign_keys`, `load_joined_on`, `load_joined`, `load_joined_by_id` and `joined_schema`, plus join candidates in `candidates_for`.
- Modify `backend/app/services/agents/architect.py`: `load_frame` reads joined tables.
- Modify `backend/app/services/agents/workflow.py`: `_db_schema` and `run_chart_code` handle joined tables.
- Create `backend/app/services/agents/links.py`: `render_links`.
- Modify `backend/app/services/agents/planning_contract.py`: `with_context(..., links="")`.
- Modify `backend/app/services/agents/planning.py`: a `links` parameter.
- Modify `backend/app/services/agents/dashboard_flow.py`: collect and pass the links.
- Create `backend/scripts/make_relational_demo.py`: a `shop` database with declared keys.
- Tests: create `backend/tests/test_db_links.py` and `backend/tests/test_links_prompt.py`.

---

### Task 1: Find declared foreign keys

**Files:**
- Modify: `backend/app/services/db_sources.py`
- Test: `backend/tests/test_db_links.py`

**Interfaces:**
- Produces:
  - `Link(child: str, child_columns: tuple[str, ...], parent: str, parent_columns: tuple[str, ...])`, frozen, with `.label -> "child+parent"`, `.to_dict()` and `Link.from_dict(d)`.
  - `links_on(connection, tables: list[str]) -> list[Link]`.
  - `foreign_keys(source, tables: list[str]) -> list[Link]`.
  - `MAX_JOINS = 6`.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_db_links.py`)

```python
"""Foreign keys between a connection's tables: found, joined, offered to the planner."""
import pandas as pd
import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine

from app.services import db_sources
from app.services.db_sources import Link, links_on

ORDERS_CUSTOMERS = Link("orders", ("customer_id",), "customers", ("id",))


def shop_engine():
    """customers <- orders -> products, plus one order whose customer does not exist."""
    engine = create_engine("sqlite://")
    meta = MetaData()
    customers = Table("customers", meta, Column("id", Integer, primary_key=True), Column("region", String))
    products = Table("products", meta, Column("id", Integer, primary_key=True), Column("category", String))
    orders = Table("orders", meta, Column("id", Integer, primary_key=True),
                   Column("customer_id", Integer, ForeignKey("customers.id")),
                   Column("product_id", Integer, ForeignKey("products.id")),
                   Column("revenue", Integer))
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(customers.insert(), [{"id": 1, "region": "North"}, {"id": 2, "region": "South"}])
        conn.execute(products.insert(), [{"id": 1, "category": "Books"}])
        conn.execute(orders.insert(), [{"id": i, "customer_id": 1 + i % 2, "product_id": 1, "revenue": 10 * i}
                                       for i in range(1, 6)])
        conn.execute(orders.insert(), [{"id": 6, "customer_id": 99, "product_id": 1, "revenue": 5}])
    return engine


def test_declared_foreign_keys_are_found():
    with shop_engine().connect() as conn:
        links = links_on(conn, ["customers", "orders", "products"])
    assert sorted(links, key=lambda l: l.parent) == [
        ORDERS_CUSTOMERS, Link("orders", ("product_id",), "products", ("id",))]


def test_a_key_to_a_table_outside_the_list_is_left_out():
    with shop_engine().connect() as conn:
        links = links_on(conn, ["orders", "customers"])
    assert links == [ORDERS_CUSTOMERS]


def test_a_link_survives_a_round_trip_through_a_dict():
    assert Link.from_dict(ORDERS_CUSTOMERS.to_dict()) == ORDERS_CUSTOMERS
    assert ORDERS_CUSTOMERS.label == "orders+customers"
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_db_links.py`
Expected: an ImportError on `Link` or `links_on`.

- [ ] **Step 3: Implement** (in `db_sources.py`; add `and_` to the `sqlalchemy` import)

```python
# Joined tables offered per connection. Each is one more table the planner reads.
MAX_JOINS = 6


@dataclass(frozen=True)
class Link:
    """A declared foreign key: each child row points at one parent row."""

    child: str
    child_columns: tuple[str, ...]
    parent: str
    parent_columns: tuple[str, ...]

    @property
    def label(self) -> str:
        """The joined table's name, as the planner and the checks see it."""
        return f"{self.child}+{self.parent}"

    def to_dict(self) -> Dict[str, Any]:
        return {"child": self.child, "child_columns": list(self.child_columns),
                "parent": self.parent, "parent_columns": list(self.parent_columns)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Link":
        return cls(str(data["child"]), tuple(data["child_columns"]), str(data["parent"]), tuple(data["parent_columns"]))


def links_on(connection: Any, tables: List[str]) -> List[Link]:
    """Declared foreign keys among `tables`, child to parent. Only declared ones:
    a join guessed from column names would be a name rule, and often wrong."""
    inspector = inspect(connection)
    known = set(tables)
    found: List[Link] = []
    for table in tables:
        for fk in inspector.get_foreign_keys(table):
            parent = fk.get("referred_table")
            child_columns = fk.get("constrained_columns") or []
            parent_columns = fk.get("referred_columns") or []
            if (parent in known and parent != table and child_columns
                    and len(child_columns) == len(parent_columns)):
                found.append(Link(table, tuple(child_columns), parent, tuple(parent_columns)))
    return found


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
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_db_links.py`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/db_sources.py backend/tests/test_db_links.py
git commit -m "feat(db): read the foreign keys a connection declares

Link records one child-to-parent key; links_on reads them with
SQLAlchemy's inspector, declared keys only, never guessed from names.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Load a joined table

**Files:**
- Modify: `backend/app/services/db_sources.py`
- Test: `backend/tests/test_db_links.py` (append)

**Interfaces:**
- Consumes: `Link` (Task 1).
- Produces:
  - `load_joined_on(connection, link, limit: int | None = None) -> pd.DataFrame`.
  - `load_joined(source, link, limit=None) -> pd.DataFrame`.
  - `load_joined_by_id(source_id: str, link, limit=None) -> pd.DataFrame`.
  - `joined_schema(source, link, sample_rows: int = 3) -> dict`, in `schema_of`'s shape (`filename`, `columns`, `dtypes`, `sample`, or `error`).

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/test_db_links.py`)

```python
from app.services.db_sources import load_joined_on


def test_a_joined_table_has_one_row_per_child_row_and_named_parent_columns():
    with shop_engine().connect() as conn:
        frame = load_joined_on(conn, ORDERS_CUSTOMERS)
    assert len(frame) == 6  # every order, the one without a customer included
    assert list(frame.columns) == ["id", "customer_id", "product_id", "revenue", "customers.id", "customers.region"]
    assert frame.loc[frame["customer_id"] == 99, "customers.region"].isna().all()


def test_a_joined_table_over_the_row_limit_is_refused(monkeypatch):
    monkeypatch.setattr(db_sources, "MAX_ROWS", 3)
    with shop_engine().connect() as conn, pytest.raises(ValueError, match="row limit"):
        load_joined_on(conn, ORDERS_CUSTOMERS)


def test_a_schema_read_takes_only_a_few_rows():
    with shop_engine().connect() as conn:
        assert len(load_joined_on(conn, ORDERS_CUSTOMERS, limit=2)) == 2
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_db_links.py`
Expected: an ImportError on `load_joined_on`.

- [ ] **Step 3: Implement** (in `db_sources.py`)

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_db_links.py`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/db_sources.py backend/tests/test_db_links.py
git commit -m "feat(db): load a child table joined to its parent

A left join on the declared key keeps one row per child row; parent
columns are named parent.column. The child's row count is checked against
MAX_ROWS like any table, and a schema read takes 5 rows.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Joined tables as sources the whole pipeline reads

**Files:**
- Modify: `backend/app/services/db_sources.py` (`candidates_for`)
- Modify: `backend/app/services/agents/architect.py` (`load_frame`)
- Modify: `backend/app/services/agents/workflow.py` (`_db_schema`, `run_chart_code`)
- Test: `backend/tests/test_db_links.py` (append)

**Interfaces:**
- Consumes: Task 1's `Link` and `foreign_keys`; Task 2's `load_joined_by_id` and `joined_schema`; `architect.load_frame(source, data_dir)` from the planner-tools plan.
- Produces: join candidates, `{"id": "<source id>:child+parent", "name": "child+parent · <connection>", "type": "db", "source_id", "table": "child+parent", "join": Link.to_dict(), "columns": [...child, ...parent.col]}`, and a data context that carries `"join"`.

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/test_db_links.py`)

```python
def test_a_connection_offers_each_joined_table(monkeypatch):
    monkeypatch.setattr(db_sources, "tables_with_columns", lambda source, limit: [
        {"table": "customers", "columns": ["id", "region"]},
        {"table": "orders", "columns": ["id", "customer_id", "revenue"]}])
    monkeypatch.setattr(db_sources, "foreign_keys", lambda source, tables: [ORDERS_CUSTOMERS])
    source = type("Source", (), {"id": "s1", "display_name": "Shop"})()
    joined = [c for c in db_sources.candidates_for(source) if c.get("join")]
    assert [c["table"] for c in joined] == ["orders+customers"]
    assert joined[0]["columns"] == ["id", "customer_id", "revenue", "customers.id", "customers.region"]
    assert joined[0]["join"] == ORDERS_CUSTOMERS.to_dict() and joined[0]["id"] == "s1:orders+customers"


def test_load_frame_reads_a_joined_table(monkeypatch):
    from app.services.agents.architect import load_frame

    seen = {}

    def fake(source_id, link, limit=None):
        seen.update(source_id=source_id, link=link)
        return pd.DataFrame({"revenue": [1], "customers.region": ["North"]})

    monkeypatch.setattr(db_sources, "load_joined_by_id", fake)
    frame = load_frame({"type": "db", "source_id": "s1", "table": "orders+customers",
                        "join": ORDERS_CUSTOMERS.to_dict()}, "")
    assert list(frame.columns) == ["revenue", "customers.region"]
    assert seen == {"source_id": "s1", "link": ORDERS_CUSTOMERS}


def test_a_chart_runs_on_a_joined_table(monkeypatch):
    from app.services.agents.workflow import run_chart_code
    from app.utils.executor import SafeExecutor

    joined = pd.DataFrame({"revenue": [10, 20, 30], "customers.region": ["North", "South", "North"]})
    monkeypatch.setattr(db_sources, "load_joined_by_id", lambda source_id, link, limit=None: joined)
    code = ("import plotly.express as px\n"
            "d = df.groupby('customers.region', as_index=False)['revenue'].sum()\n"
            "fig = px.bar(d, x='customers.region', y='revenue')\n"
            "print(fig.to_json())\n")
    out = run_chart_code({"source_id": "s1", "table": "orders+customers", "join": ORDERS_CUSTOMERS.to_dict()},
                         code, SafeExecutor())
    assert out["execution_result"]["figure"]["data"][0]["type"] == "bar"
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_db_links.py`
Expected: the 3 new tests fail. There are no join candidates yet, and `load_frame` and `run_chart_code` read `table` as a plain table.

- [ ] **Step 3: Implement**

In `db_sources.py`, replace `candidates_for`:

```python
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
```

In `architect.load_frame`, make the database branch:

```python
    if source.get("type") == "db":
        from app.services import db_sources

        if source.get("join"):
            return db_sources.load_joined_by_id(str(source["source_id"]), db_sources.Link.from_dict(source["join"]))
        return db_sources.load_table_by_id(str(source["source_id"]), str(source["table"]))
```

In `workflow._db_schema`, replace the `schema = db_sources.schema_of(...)` line and the block after it:

```python
        if selected.get("join"):
            schema = db_sources.joined_schema(source, db_sources.Link.from_dict(selected["join"]))
        else:
            schema = db_sources.schema_of(source, str(selected.get("table")))
        if "error" not in schema:
            # Carried so the executor can load the same table without
            # resolving the source a second time.
            schema["source_id"] = source.id
            schema["table"] = selected.get("table")
            if selected.get("join"):
                schema["join"] = selected["join"]
        return schema
```

In `workflow.run_chart_code`, add as its first branch:

```python
    if data_context.get("source_id") and data_context.get("join"):
        try:
            df = db_sources.load_joined_by_id(
                str(data_context["source_id"]), db_sources.Link.from_dict(data_context["join"])
            )
        except Exception as exc:
            logger.error("[workflow/executor] joined table load failed: %s", exc)
            return {"error": f"Failed to read that joined table: {exc}"}
        return run_on_frame(executor, code, df, repair)
```

- [ ] **Step 4: Run the tests and the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_db_links.py && .venv/bin/python -m pytest -q tests`
Expected: 9 passed, and only the 3 known failures in the suite.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/db_sources.py backend/app/services/agents/architect.py backend/app/services/agents/workflow.py backend/tests/test_db_links.py
git commit -m "feat(db): joined tables are sources like any other

Each declared key becomes one more candidate (orders+customers) whose
columns are the child's plus parent.col. The profile, the schema read and
the executor load it through the join, so the planner, the checks and the
chartist see one DataFrame and nothing downstream changed.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Tell the planner what each joined table is

**Files:**
- Create: `backend/app/services/agents/links.py`
- Modify: `backend/app/services/agents/planning_contract.py` (`with_context`)
- Modify: `backend/app/services/agents/planning.py`
- Modify: `backend/app/services/agents/dashboard_flow.py`
- Test: `backend/tests/test_links_prompt.py`

**Interfaces:**
- Consumes: join sources carrying `"join"` (Task 3); `with_context` and the planning functions from the planner-tools plan.
- Produces:
  - `links.render_links(links: list[dict]) -> str` and `MAX_LINKS = 4`.
  - `with_context(text, facts="", memory="", links="")`, which puts links right after the tables.
  - `propose_directions_steps(..., facts="", memory="", links="")` and `plan_charts_steps(..., facts="", validate=None, links="")`, plus the matching drains.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_links_prompt.py`)

```python
"""The planner is told what each joined table is, in a line each."""
import pandas as pd

from app.services import db_sources
from app.services.agents.dashboard_flow import build_dashboard
from app.services.agents.links import render_links
from app.services.agents.planning_contract import with_context

LINK = {"child": "orders", "child_columns": ["customer_id"], "parent": "customers", "parent_columns": ["id"]}


class Recorder:
    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def invoke(self, messages):
        self.seen.append(list(messages))
        return type("Reply", (), {"content": self.replies.pop(0)})()


def test_each_join_is_one_line_naming_its_key_and_how_columns_are_named():
    text = render_links([LINK])
    assert "orders+customers" in text and "orders.customer_id = customers.id" in text
    assert "customers.<column>" in text


def test_no_links_adds_nothing():
    assert render_links([]) == "" and with_context("Tables: t", links="") == "Tables: t"


def test_links_come_right_after_the_tables():
    message = with_context("Tables:\n...", facts="- a fact", links=render_links([LINK]))
    assert message.index("Tables:") < message.index("Joined tables") < message.index("Facts checked")


def test_the_analyst_is_told_about_a_joined_table(monkeypatch):
    joined = pd.DataFrame({"revenue": [10, 20], "customers.region": ["North", "South"]})
    monkeypatch.setattr(db_sources, "load_joined_by_id", lambda source_id, link, limit=None: joined)
    source = {"type": "db", "source_id": "s1", "table": "orders+customers",
              "name": "orders+customers · Shop", "join": LINK}
    analyst = Recorder("{}", "{}", "{}")  # unusable on purpose: only the first message matters
    list(build_dashboard("revenue by region", [source], "", analyst, Recorder(), None))
    assert "Joined tables you can use" in analyst.seen[0][-1].content
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_links_prompt.py`
Expected: an ImportError on `app.services.agents.links`.

- [ ] **Step 3: Implement**

`backend/app/services/agents/links.py`:

```python
"""Joined tables, told to the planner in a line each.

A connection's declared foreign keys become joined tables (orders+customers: each
order with its customer's columns). The planner reads them like any other table;
this line says what each one is, so it knows `customers.region` is the region of
the order's customer.
"""
from __future__ import annotations

MAX_LINKS = 4


def render_links(links: list[dict]) -> str:
    if not links:
        return ""
    lines = ["Joined tables you can use (each row of the first table with its match in the second):"]
    for link in links[:MAX_LINKS]:
        on = ", ".join(f"{link['child']}.{c} = {link['parent']}.{p}"
                       for c, p in zip(link["child_columns"], link["parent_columns"]))
        lines.append(f"- {link['child']}+{link['parent']}: joined on {on}; "
                     f"columns from {link['parent']} are named {link['parent']}.<column>")
    return "\n".join(lines)
```

In `planning_contract.py`, replace `with_context`:

```python
def with_context(text: str, facts: str = "", memory: str = "", links: str = "") -> str:
    """A planning user message, with optional sections after the trained part.
    Links describe tables, so they come straight after them."""
    parts = [text]
    if links:
        parts.append(links)
    if facts:
        parts.append(f"{FACTS_HEADER}\n{facts}")
    if memory:
        parts.append(memory)
    return "\n\n".join(parts)
```

In `planning.py`, replace the four public functions with:

```python
def propose_directions_steps(
    llm: Any, request: str, profiles: list[TableProfile], facts: str = "", memory: str = "", links: str = ""
) -> Generator[Retry, None, PlanStep]:
    user = with_context(
        ANALYST_USER_TEMPLATE.format(request=(request or "").strip() or NO_REQUEST, profiles=render_profiles(profiles)),
        facts,
        memory,
        links,
    )
    return run_checked(llm, ANALYST_SYSTEM_PROMPT, user, check_directions, columns_by_table(profiles), "analyst")


def propose_directions(
    llm: Any, request: str, profiles: list[TableProfile], facts: str = "", memory: str = "", links: str = ""
) -> PlanStep:
    return finish(propose_directions_steps(llm, request, profiles, facts, memory, links))


def plan_charts_steps(
    llm: Any,
    directions: list[dict],
    profiles: list[TableProfile],
    facts: str = "",
    validate: Callable[[dict], list[str]] | None = None,
    links: str = "",
) -> Generator[Retry, None, PlanStep]:
    user = with_context(
        PLANNER_USER_TEMPLATE.format(profiles=render_profiles(profiles), directions=render_directions(directions)),
        facts,
        links=links,
    )
    check = check_specs if validate is None else (lambda payload, tables: check_specs(payload, tables, validate))
    return run_checked(llm, PLANNER_SYSTEM_PROMPT, user, check, columns_by_table(profiles), "planner")


def plan_charts(
    llm: Any,
    directions: list[dict],
    profiles: list[TableProfile],
    facts: str = "",
    validate: Callable[[dict], list[str]] | None = None,
    links: str = "",
) -> PlanStep:
    return finish(plan_charts_steps(llm, directions, profiles, facts, validate, links))
```

In `dashboard_flow.py`, import `render_links` and add after `profiles = [entry.profile for entry in tables]`:

```python
    links = render_links([entry.source["join"] for entry in tables if entry.source.get("join")])
```

Then pass `links=links` to both `propose_directions_steps(...)` and `plan_charts_steps(...)`.

- [ ] **Step 4: Run the tests and the suite**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_links_prompt.py && .venv/bin/python -m pytest -q tests`
Expected: 4 passed, and only the 3 known failures in the suite.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/links.py backend/app/services/agents/planning_contract.py backend/app/services/agents/planning.py backend/app/services/agents/dashboard_flow.py backend/tests/test_links_prompt.py
git commit -m "feat(planning): say what each joined table is

A short section after the tables names each join, its key, and how the
parent's columns are named, so the analyst and planner can use
orders+customers to answer 'revenue by customer region'.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: A relational demo database and a live check

**Files:**
- Create: `backend/scripts/make_relational_demo.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: everything above; `Settings.DATABASE_URL`.
- Produces: database `shop` with `customers`, `products` and `orders`, where `orders.customer_id` references `customers.id` and `orders.product_id` references `products.id`.

- [ ] **Step 1: Write the script**

```python
"""A small shop database with declared foreign keys, for trying joined tables.

    docker exec -i promptdash-api python /app/scripts/make_relational_demo.py

Creates database `shop` on the app's Postgres if it is missing, then rebuilds
its three tables. Seeded, so every run makes the same rows. Touches nothing
outside `shop`.
"""
import sys

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, "/app")
from app.core.config import get_settings  # noqa: E402

admin = make_url(get_settings().DATABASE_URL)
with create_engine(admin, isolation_level="AUTOCOMMIT").connect() as conn:
    if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'shop'")).scalar():
        conn.execute(text("CREATE DATABASE shop"))

engine = create_engine(admin.set(database="shop"))
rng = np.random.default_rng(7)
customers = pd.DataFrame({
    "id": range(1, 201),
    "name": [f"Customer {i}" for i in range(1, 201)],
    "region": rng.choice(["North", "South", "East", "West"], 200),
    "segment": rng.choice(["Consumer", "SMB", "Enterprise"], 200, p=[0.6, 0.3, 0.1]),
})
products = pd.DataFrame({
    "id": range(1, 41),
    "name": [f"Product {i}" for i in range(1, 41)],
    "category": rng.choice(["Books", "Games", "Home", "Garden", "Tech"], 40),
    "unit_price": rng.uniform(5, 300, 40).round(2),
})
orders = pd.DataFrame({
    "id": range(1, 5001),
    "customer_id": rng.integers(1, 201, 5000),
    "product_id": rng.integers(1, 41, 5000),
    "order_date": pd.to_datetime("2024-01-01") + pd.to_timedelta(rng.integers(0, 730, 5000), unit="D"),
    "quantity": rng.integers(1, 6, 5000),
})
orders["revenue"] = (orders["quantity"] * products.set_index("id").loc[orders["product_id"], "unit_price"].to_numpy()).round(2)

with engine.begin() as conn:
    conn.execute(text("DROP TABLE IF EXISTS orders; DROP TABLE IF EXISTS products; DROP TABLE IF EXISTS customers"))
    conn.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                      "region TEXT NOT NULL, segment TEXT NOT NULL)"))
    conn.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                      "category TEXT NOT NULL, unit_price NUMERIC(10,2) NOT NULL)"))
    conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, "
                      "customer_id INTEGER NOT NULL REFERENCES customers(id), "
                      "product_id INTEGER NOT NULL REFERENCES products(id), "
                      "order_date DATE NOT NULL, quantity INTEGER NOT NULL, revenue NUMERIC(12,2) NOT NULL)"))
customers.to_sql("customers", engine, if_exists="append", index=False)
products.to_sql("products", engine, if_exists="append", index=False)
orders.to_sql("orders", engine, if_exists="append", index=False)
print(f"shop: {len(customers)} customers, {len(products)} products, {len(orders)} orders")
```

- [ ] **Step 2: Run it and check the keys**

Run: `docker exec -i promptdash-api python /app/scripts/make_relational_demo.py`
Expected: `shop: 200 customers, 40 products, 5000 orders`

Run: `docker exec promptdash-postgres psql -U promptdash -d shop -c '\d orders'`
Expected: two `FOREIGN KEY` lines, to `customers(id)` and `products(id)`.

- [ ] **Step 3: Live check in the app**

1. Open `http://localhost:3000` and sign in.
2. Go to Data and add a database: PostgreSQL, host `postgres`, port `5432`, database `shop`, user `promptdash`, password `promptdash` (the compose defaults).
3. Create a report that reads only that connection.
4. Run "Generate dashboard" with the brief "revenue by customer region and product category".

Run: `docker compose logs api --since 10m --no-log-prefix | grep "\[dashboard\] planned"`
Expected: the plan names `orders+customers` or `orders+products` for at least one chart, and the canvas shows it drawn by the model.

If neither joined table is used, record it: the planner chose not to, which is an input for the next prompt revision, not a failure of this plan.

- [ ] **Step 4: Document and commit**

Add one bullet to `AGENTS.md` under "Database sources are real":

```markdown
- Declared foreign keys become joined tables (`db_sources.Link`, `candidates_for`): `orders+customers` is a left join keeping one row per order, with the customer's columns named `customers.region`; at most 6 per connection, one hop, child to parent, never guessed from names. The analyst and planner get one line per join (`agents/links.py`). Demo: `backend/scripts/make_relational_demo.py` builds a `shop` database with customers, products and orders.
```

```bash
git add backend/scripts/make_relational_demo.py AGENTS.md
git commit -m "chore(db): a shop demo with declared keys, and the joined-table notes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
