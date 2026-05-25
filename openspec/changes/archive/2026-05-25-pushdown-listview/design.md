## Context

Today, the v1.0 list-view kit implements **post-hoc** filter / fields /
pagination. The flow:

```
agent → MCP server → tool body → list[dict] → ListViewMiddleware →
    filter (CEL) → project fields → slice (cursor + page_size) → wire
```

Every step after `tool body` runs in the MCP process against the
**full materialized result**. This is the right shape when:

- The data source is in-memory (the tracker example's JSONL).
- The dataset is small enough that "load all + filter in Python" is
  acceptable.
- The backend has no native filter / projection / pagination.

It is the **wrong shape** when:

- Backend supports SQL `WHERE` / `SELECT` / `LIMIT OFFSET`.
- Backend supports JQL (`project = "API" AND status != "Done"`).
- Backend supports REST query params (`?fields=`, `?cursor=`,
  `?limit=`).
- Datasets are large enough that loading all rows is wasteful or
  outright infeasible (Jira instances with 1M issues; Postgres tables
  with 100M rows).

The user's framing is correct: **the MCP layer should be able to
delegate listview to the underlying service when the service can do
it natively, falling back to post-hoc only when it can't**.

The shape we want is an interface adapters implement, plus a thin
sentinel a tool body returns to opt in. This is the `Pushdown`
Protocol + `Query[T]` wrapper. The middleware's branch on
`isinstance(result, Query)` is the only code path that changes in
core.

## Goals / Non-Goals

### Goals

- A typed `Pushdown` Protocol in core (`a2kit.pushdown`) — agnostic
  to backend, opt-in, ~30 LOC.
- A `Query[T]` wrapper sentinel that tool bodies return to delegate
  listview semantics to the adapter.
- Three reference adapters under `a2kit.packages.pushdown_*`:
  generic SQL, JQL (Jira/Confluence), generic REST. Each is its own
  pip extra.
- The MCP listview middleware (and the CLI runtime equivalent) detects
  `Query[T]`, applies filter / fields / page through the adapter,
  executes, returns the result. Post-hoc behavior preserved for
  list-returning tools.
- Backwards compatible — every existing tool returning `list[dict]`
  keeps working unchanged.
- Cold-start budget unchanged. Adapters lazy-load like
  `packages.otel`.
- An `examples/sql_pushdown/` demo against in-memory sqlite proving
  the e2e flow.

### Non-Goals

- Replacing the post-hoc layer. Most tools won't have a backend with
  native listview; the fallback IS the default.
- Universal CEL → SQL translator. Each adapter handles a subset of
  CEL — the simple comparison / boolean ops — and raises
  `PushdownNotSupported` on the rest. Middleware catches it and
  falls back to post-hoc on the materialized result.
- Cross-adapter joins. One adapter, one backend, one query.
- Write-side pushdown. `@a2kit.write()` tools still return their
  result directly; this change is read-side only.
- Caching / memoization of pushed-down queries. Cross-cutting concern;
  belongs in a separate adapter (e.g. `pushdown_cache`).
- Streaming results. Adapters return materialized lists. Streaming
  pagination via `report_progress` / cursor-based generators is a
  follow-up.

## Decisions

### D-PUSHDOWN-PROTOCOL: thin Protocol in core

```python
# src/a2kit/pushdown.py
from typing import Protocol, TypeVar, Generic, runtime_checkable

T = TypeVar("T")
Q = TypeVar("Q")  # adapter-specific query type


@runtime_checkable
class Pushdown(Protocol[Q]):
    """Adapter interface — implemented by SQL/JQL/REST/etc. plugins.

    Each method receives the current query state and returns the
    new state. `execute` materializes the query into rows.
    """
    def filter(self, query: Q, expr: str) -> Q: ...
    def fields(self, query: Q, names: tuple[str, ...]) -> Q: ...
    def page(self, query: Q, cursor: str | None, size: int) -> Q: ...
    async def execute(self, query: Q) -> list[dict]: ...


class Query(Generic[T]):
    """Sentinel wrapper a tool body returns to opt into pushdown.

    The middleware unwraps to access the adapter and the query state,
    applies listview kwargs through the adapter, then calls execute().
    """
    __slots__ = ("_adapter", "_state")

    def __init__(self, adapter: Pushdown[T], state: T) -> None:
        self._adapter = adapter
        self._state = state

    @property
    def adapter(self) -> Pushdown[T]:
        return self._adapter

    @property
    def state(self) -> T:
        return self._state


class PushdownNotSupported(Exception):
    """Raised by an adapter when CEL / kwargs can't translate.

    Middleware catches this, falls back to post-hoc on the executed
    rows.
    """
```

`Pushdown` is `runtime_checkable` so the middleware can `isinstance`-test
adapters. `Query[T]` is a thin `Generic[T]` wrapper — no business logic.

### D-LISTVIEW-BRANCH: middleware reroutes on `Query[T]`

`packages/mcp/listview.py` and `packages/cli/runtime.py` currently
take a `result: list[dict]` and apply listview semantics. The new
shape:

```python
async def apply_listview(result, *, filter_expr, fields, cursor, page_size):
    if isinstance(result, Query):
        adapter, state = result.adapter, result.state
        try:
            if filter_expr:
                state = adapter.filter(state, filter_expr)
            if fields:
                state = adapter.fields(state, fields)
            if cursor is not None or page_size is not None:
                state = adapter.page(state, cursor, page_size or DEFAULT_PAGE_SIZE)
            return await adapter.execute(state)
        except PushdownNotSupported:
            # Fall back: execute the full query, apply post-hoc.
            rows = await adapter.execute(state)
            return _post_hoc(rows, filter_expr=filter_expr, fields=fields, cursor=cursor, page_size=page_size)
    return _post_hoc(result, filter_expr=filter_expr, fields=fields, cursor=cursor, page_size=page_size)
```

`_post_hoc` is the existing in-memory implementation, extracted from
`listview.py` so both branches reuse it.

### D-ADAPTER-PACKAGES: each adapter is a plugin package

Per the v1.0 thin-core principle, adapters live under
`a2kit.packages.pushdown_*`. Each:

- Has its own optional dep (`pip install 'a2kit[pushdown-sql]'`).
- Lazy-imports its backend library inside fn bodies / methods.
- Ships zero re-exports of the backend library's symbols.
- Includes its own README documenting CEL coverage and limitations.

### D-SQL-ADAPTER: generic SQL adapter

`a2kit.packages.pushdown_sql.SqlPushdown` works against any DB-API 2.0
connection. State `Q` is a query-builder dict:

```python
{"table": "tasks", "where": [...], "select": [...], "limit": int, "offset": int}
```

Methods:

- `filter(state, expr)` — CEL → SQL `WHERE` clause via a
  `cel_to_sql(expr)` helper. Supports `==`, `!=`, `<`, `<=`, `>`,
  `>=`, `&&`, `||`, `!`, `in`, member access (one level).
  Untranslatable CEL → `PushdownNotSupported`.
- `fields(state, names)` — appends to `select`.
- `page(state, cursor, size)` — `LIMIT size OFFSET cursor`. Cursor is
  base64-encoded offset for stable pagination.
- `execute(state)` — builds `SELECT … FROM … WHERE … LIMIT … OFFSET …`,
  parameterizes safely, runs against the DB-API connection, returns
  list of dicts.

Backend-agnostic: works with sqlite3, psycopg2, asyncpg (with sync
shim), etc. The user supplies the connection; the adapter just does
SQL.

### D-JQL-ADAPTER: Jira / Confluence

`a2kit.packages.pushdown_jql.JqlPushdown` wraps an Atlassian REST
client. State `Q` is the JQL string + REST params dict.

CEL → JQL translation:
- `project == "API"` → `project = "API"`
- `status != "Done"` → `status != "Done"`
- `labels.contains("urgent")` → `labels = "urgent"`
- `priority > 3` → `priority > 3`
- `created > "2026-01-01"` → `created > "2026-01-01"`

Untranslatable CEL → `PushdownNotSupported`.

`fields(state, names)` → REST `fields=` query param.
`page(state, cursor, size)` → REST `startAt=` + `maxResults=`.

### D-REST-ADAPTER: generic REST

`a2kit.packages.pushdown_rest.RestPushdown` wraps `httpx.AsyncClient`.
Configured per-tool with:

- `endpoint: str` — base URL.
- `filter_param: str | None` — name of the query param for filtering
  (e.g. `"q"` for ElasticSearch-style).
- `fields_param: str | None` — name of the projection param (e.g.
  `"fields"`).
- `cursor_param: str | None` — name of the cursor param (e.g.
  `"cursor"` or `"page_token"`).
- `size_param: str | None` — name of the page-size param (e.g.
  `"limit"` or `"per_page"`).

CEL → REST translation: defers to a user-provided `cel_to_query(expr)`
callable; default raises `PushdownNotSupported` for everything (bring
your own translator).

This is the "configure-by-data" adapter for arbitrary REST APIs.

### D-LINT-RULE: A2K-PUSHDOWN-MISMATCH

```python
@a2kit.list_()
async def list_users(*, conn) -> Query[User]:
    return sql_adapter.start("users")
```

If the tool returns `Query[T]` but the `@a2kit.list_()` decorator has
no `list_view=ListViewSettings(...)` config (no `default_fields`,
`page_size`, `selectable_fields`), the lint rule warns:
"Tool returns `Query[T]` but no listview config is declared. Pushdown
needs `list_view=...` so the agent surface advertises the listview
kwargs."

### D-FALLBACK-CONTRACT: adapters can give up gracefully

`PushdownNotSupported` is the documented escape hatch. Adapters raise
it when:
- CEL contains a function call the adapter can't translate.
- A field name in `fields=` doesn't exist on the backend schema.
- Cursor format doesn't match the adapter's expectation.

Middleware catches the exception, calls `adapter.execute(state)` to
materialize the (un-pushed) query, and applies post-hoc semantics on
the result. Worst case: pushdown didn't help, but the agent gets the
right answer.

A debug log line at this fallback boundary helps adapter authors find
gaps: `logger.debug("pushdown gave up", reason=str(exc))`.

### D-CLI-PARITY: CLI runtime mirrors the branch

`packages/cli/runtime.py` already invokes `enrichers.wrap` and
`format_response`. Add the listview branch in the same place:

```python
async def _invoke_tool_in_process(fn, kwargs, *, fmt, ctx_param_name=None):
    # ... existing setup ...
    raw = await wrapped(**kwargs)
    listview_kwargs = _extract_listview_kwargs(kwargs, fn._a2kit.list_view)
    if listview_kwargs:
        raw = await apply_listview(raw, **listview_kwargs)
    response = format_response(raw, format_hint=fmt)
    print(response.data)
```

`apply_listview` is the shared helper from D-LISTVIEW-BRANCH;
identical code in MCP and CLI.

### D-EXAMPLE-CHOICE: SQL pushdown demo

`examples/sql_pushdown/` ships an in-memory sqlite database with
tasks + projects, demonstrates `@list_()` returning
`Query[Task]`, walks the agent through filter / fields / cursor /
page_size — showing how the SQL adapter rewrites each into native
SQL.

JQL and REST adapters get unit tests but no full example (real Jira /
generic REST endpoints aren't reproducible in CI without secrets).
README links to `examples/sql_pushdown/` as the canonical reference.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| CEL → SQL injection if translator concatenates user input | Translators MUST parameterize via DB-API placeholders. Lint rule (`pushdown_sql_safety`) flags string concatenation. Audit every `cel_to_sql` translator before merge. |
| `PushdownNotSupported` fallback hides slow paths | Debug log at fallback; adapter authors should aim for ≥ 90 % CEL coverage. Document expected coverage in each adapter's README. |
| `Query[T]` adds a new return-type shape tools must learn | Optional. Tools that don't need pushdown ignore it entirely. README explicitly frames `Query[T]` as "opt-in for backends that natively support listview". |
| Adapter packages drift from CEL spec changes | Pin `cel-python` minor version; regenerate translation tables on bumps. |
| Per-adapter test fixtures (sqlite is easy; Jira is hard) | SQL adapter tests run against in-memory sqlite — fully reproducible. JQL adapter tests use `vcrpy` cassettes (already a dev dep). REST adapter tests use `httpx.MockTransport`. |
| Pagination cursor schemes vary across backends | Each adapter defines its own cursor format (SQL: base64 offset; JQL: `startAt` integer; REST: opaque per config). The agent receives an opaque cursor; only the originating adapter parses it. Document this. |
| Adapter's `execute` may need an event loop / async context | All `execute` methods are `async def`. SQL adapter wraps DB-API in `asyncio.to_thread` for sync drivers. |
| Listview parameters may be ambiguous (e.g. should `fields` push down to SQL `SELECT` or post-hoc-project the result?) | Pushdown wins if available. Lint warns if both pushdown adapter AND post-hoc `list_view.fields` are declared (A2K-PUSHDOWN-DOUBLED). |

## Open questions (decide during implementation)

- Whether `Pushdown` lives at `a2kit.pushdown` (top-level core) or
  `a2kit.packages.pushdown` (plugin namespace). Lean: **core**, since
  the Protocol is the contract every adapter implements; only the
  concrete adapters are plugins. Counter-argument: keeping `a2kit/`
  ≤ 12 files. The Protocol is ~30 LOC and is opt-in, but it widens
  the core surface. Final call during apply.
- Whether `Query[T]` should be `__slots__` for memory or use
  `dataclass(frozen=True)` for ergonomics. Lean: **dataclass(frozen=True)**
  — ergonomic + the slot savings don't matter for short-lived sentinels.
- Whether the SQL adapter should support a `JOIN` clause in `state`,
  or stay single-table. Lean: **stay single-table** for v1; document
  the join workaround (subquery; or build joins in the tool body
  before wrapping).
- Whether to ship a `pushdown_graphql` adapter alongside the three
  proposed. Lean: **no**, GraphQL's pushdown semantics are
  query-shape-specific and don't map cleanly to filter / fields /
  page. Defer to a future change.
- Whether the lint rule fires only when `Query[T]` is the *return
  type annotation* or also when it's just returned at runtime. Lean:
  **annotation-driven** — agent surface is the annotation, the lint
  rule mirrors that.
