## Why

`a2kit`'s **list-view kit** (filter, field selection, pagination) currently
runs **post-hoc** at the MCP layer: the tool body returns a `list[dict]`
and the listview middleware filters / projects / paginates it client-side.
That's correct for in-memory data (the tracker example's JSONL store
loads everything anyway), but it's **wrong for any tool that wraps a
SQL database, a Jira / Confluence API, a Kubernetes REST endpoint,
Salesforce SOQL, or any backend that already supports those primitives
natively**.

Concrete waste:

- A `list_tasks(filter="status=open and priority>3")` against Jira
  loads **every issue** the connection can see, then filters in
  Python. Jira's JQL handles the same predicate in the database; the
  MCP could push the filter down via JQL and load only matching rows.
- A `query_users(fields=["id", "email"], limit=20, cursor=...)` against
  Postgres loads `SELECT *` for every user, projects two columns
  in Python, and slices. The DB already speaks `SELECT id, email FROM
  users LIMIT 20 OFFSET …`.
- A `search_pages(filter=..., page_size=50)` against Confluence loads
  page 1 of 1000 (Confluence's default), iterates manually. Confluence
  REST exposes `start=` and `limit=` parameters that map exactly to
  cursor + page_size.

The list-view post-hoc layer is a **fallback for tools without
backend pushdown**. Tools that **can** push down should be able to
declare it via a typed adapter interface. The middleware detects
the adapter, hands off filter / fields / page semantics, and executes
the rewritten query. Result: agents pay for what they ask for, not
what the database happens to hold.

## What Changes

### Core surface — `Pushdown` Protocol + `Query[T]` wrapper

- New module `a2kit.pushdown` (or `a2kit.list_view`) ships:
  - `class Query[T]: ...` — a generic wrapper a tool body returns to
    signal "the listview kit should rewrite + execute this query, not
    consume my result".
  - `class Pushdown(Protocol[T])` — interface a tool's adapter implements:
    `filter(query, expr)`, `fields(query, names)`, `page(query, cursor, size)`, `execute(query) -> list[dict]`.
  - `from_callable(adapter, query)` — convenience to build a `Query[T]`
    from any object with a compatible adapter.

### Per-tool adapter — opt-in via decorator

```python
from a2kit.pushdown import Query
from .jira_pushdown import jql_adapter

@TasksRouter.list_()
async def list_tasks(
    *,
    conn: JiraConn = Depends(get_conn),
    project: str,
) -> Query[Issue]:
    return jql_adapter.start(conn).where(f"project = {project}")
```

The middleware sees `Query[T]`, calls
`adapter.filter(...).fields(...).page(...).execute(...)` based on the
listview parameters the agent supplied. Tool body stays declarative —
it builds a query, the kit ships it.

### Listview middleware: rewrite-then-execute path

`packages/mcp/listview.py` and the equivalent CLI runtime path SHALL:

1. Call the wrapped tool fn.
2. **If the result is a `Query[T]`** — extract its adapter, apply
   filter / fields / page from the listview kwargs, call `execute()`,
   return the resulting list.
3. **Otherwise** — fall back to the current post-hoc behavior (filter
   / project / paginate the in-memory list).

### Adapters ship as plugin packages

To keep core dependency-free, concrete adapters are **plugin packages**:

- `a2kit.packages.pushdown_sql` — generic SQL pushdown (SELECT clause
  rewriting; works with sqlite3, psycopg, asyncpg, etc.).
- `a2kit.packages.pushdown_jql` — Jira / Confluence JQL adapter.
- `a2kit.packages.pushdown_rest` — generic REST pushdown for APIs
  with `?fields=`, `?cursor=`, `?limit=` query params.

Each adapter ships with its own pyproject extra:
`pip install 'a2kit[pushdown-sql]'`, `pip install 'a2kit[pushdown-jql]'`, etc.
None are required for the in-memory fallback.

### Listview parameter contract

The listview middleware already accepts `filter`, `fields`, `cursor`,
`page_size` as kwargs on every `@a2kit.list_()`-decorated tool.
Pushdown does not change this surface. Agent authoring stays
identical; only the *execution path* differs.

### CEL → adapter translation

`filter` arrives as a CEL expression (`a2kit.packages.select`). Each
adapter SHALL translate CEL to its native filter language:

- SQL adapter: CEL `tool.foo == "bar" && cap.write` → SQL `tool.foo = 'bar' AND cap.write IS TRUE`.
- JQL adapter: CEL `project == "API"` → JQL `project = "API"`.
- REST adapter: CEL → URL-encoded query params per its config.

Translations are best-effort. Unsupported CEL features raise
`PushdownNotSupported`; the middleware catches it and falls back to
post-hoc filtering on the executed result. Documented escape hatch.

### Lint rule — A2K-PUSHDOWN-MISMATCH

When a tool returns `Query[T]` but the Router's `@list_()` decorator
declares no listview kit configuration (no `filter` / `fields` /
`page_size`), warn the author. Pushdown without listview kwargs is
likely a mistake.

### Documentation

- New section in `README.md`: "When listview runs at the backend".
- New example: `examples/sql_pushdown/` demonstrating the SQL adapter
  against an in-memory sqlite database.
- Migration guide for existing tracker example: stays in-memory (no
  pushdown), documents *why* — JSONL files don't have a query engine.

## Capabilities

### New Capabilities

- `pushdown-listview`: introduces `Query[T]` wrapper, `Pushdown` Protocol,
  and the listview middleware's rewrite-then-execute path.
- `pushdown-sql-adapter`: opt-in SQL adapter package with CEL→SQL
  translation.
- `pushdown-jql-adapter`: opt-in Jira / Confluence JQL adapter package.
- `pushdown-rest-adapter`: opt-in generic REST adapter package.

### Modified Capabilities

- `thin-core-surface`: refines the listview-kit contract — tool bodies
  MAY return `Query[T]` to delegate filtering / projection /
  pagination to the underlying service. The post-hoc fallback path
  remains unchanged for tools that return plain lists.

## Impact

- **Affected code**: `src/a2kit/pushdown.py` (new core file —
  `Query[T]` + `Pushdown` Protocol; ~30 LOC),
  `src/a2kit/packages/mcp/listview.py` (rewrite-then-execute branch),
  `src/a2kit/packages/cli/runtime.py` (mirror branch for CLI),
  `src/a2kit/packages/pushdown_sql/`, `pushdown_jql/`, `pushdown_rest/`
  (new plugin packages),
  `src/a2kit/packages/lint/rules/pushdown.py` (new A2K-PUSHDOWN-MISMATCH rule),
  `examples/sql_pushdown/` (new example), `pyproject.toml` (new extras),
  `README.md`, `ANTIPATTERNS.md`, `CHANGELOG.md`.
- **APIs**: backwards compatible. Tools returning `list[dict]` keep
  working; only the *new* `Query[T]` return type triggers the
  pushdown path.
- **Dependencies**: each adapter has its own optional extra. SQL
  adapter has zero hard deps (works with stdlib `sqlite3`); JQL and
  REST adapters depend on `httpx` (already a transitive dep via
  fastmcp).
- **Cold-start budget**: `import a2kit` cost unchanged (Pushdown
  Protocol is type-only). Adapter packages lazy-load like
  `a2kit.packages.otel`.
- **Test coverage**: the listview rewrite path needs both the
  pushdown branch (e2e against an in-memory sqlite database) and the
  fallback branch (existing post-hoc tests).
- **Risk**: CEL → backend-language translation is the hard part.
  Mitigation: each adapter raises `PushdownNotSupported` for
  untranslatable expressions; middleware falls back to post-hoc.
- **Out of scope**: write-side pushdown (e.g. bulk UPDATE). Only
  read-side `@list_()` semantics are affected.
- **Out of scope**: cross-adapter joins. Each adapter operates on a
  single backend.
