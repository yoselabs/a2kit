## ADDED Requirements

### Requirement: `Pushdown` Protocol + `Query[T]` wrapper in core

`a2kit.pushdown` SHALL define:

- `Pushdown(Protocol[Q])` — `runtime_checkable` Protocol with methods
  `filter(query, expr) -> query`, `fields(query, names) -> query`,
  `page(query, cursor, size) -> query`, and async `execute(query) -> list[dict]`.
- `Query[T]` — generic wrapper carrying an adapter and the current
  query state. Tool bodies return `Query[T]` to opt into pushdown.
- `PushdownNotSupported` — exception class adapters raise when CEL /
  kwargs can't translate.

#### Scenario: Protocol is runtime_checkable
- **WHEN** an adapter is instantiated and `isinstance(adapter, Pushdown)` is evaluated
- **THEN** the result is True for any object exposing the four required methods

#### Scenario: Query wrapper exposes adapter + state
- **WHEN** a `Query(adapter, state)` is constructed and `q.adapter` / `q.state` are accessed
- **THEN** the original adapter and state are returned unchanged

#### Scenario: PushdownNotSupported is a documented exception
- **WHEN** an adapter's translator encounters CEL it cannot translate
- **THEN** raising `PushdownNotSupported` is the documented escape hatch; the middleware catches it and falls back to post-hoc

### Requirement: listview middleware reroutes on `Query[T]`

The MCP listview middleware (`a2kit.packages.mcp.listview`) AND the
CLI runtime path (`a2kit.packages.cli.runtime`) SHALL both detect a
tool result of type `Query[T]` and:

1. Apply `filter` / `fields` / `page` from the listview kwargs through
   the adapter.
2. Call `await adapter.execute(state)` to materialize the result.
3. Return the materialized list to the formatter.

If `PushdownNotSupported` is raised at any rewrite step, the
middleware SHALL call `adapter.execute(state)` to materialize the
un-pushed query and apply post-hoc filter / fields / page on the
result.

#### Scenario: pushdown path is taken when Query[T] returned
- **WHEN** a tool returns `Query(adapter, state)` and the agent supplies `filter="status==open"`, `page_size=10`
- **THEN** the middleware calls `adapter.filter(state, "status==open")`, then `adapter.page(...)`, then `await adapter.execute(...)` — `_post_hoc` is not invoked

#### Scenario: post-hoc fallback on PushdownNotSupported
- **WHEN** an adapter raises `PushdownNotSupported` from `filter()`
- **THEN** the middleware calls `await adapter.execute(state)` (un-pushed) and applies the post-hoc filter on the materialized rows

#### Scenario: list-returning tools take the existing path
- **WHEN** a tool returns `list[dict]`
- **THEN** the middleware applies post-hoc filter / fields / page (existing v1.0 behavior)

#### Scenario: Both branches share a `_post_hoc` helper
- **WHEN** the listview module is inspected
- **THEN** the in-memory implementation lives in a single `_post_hoc(...)` helper consumed by both the pushdown-fallback path and the list-result path

### Requirement: backwards compatibility

The pushdown layer SHALL NOT change the agent-facing surface of
existing tools. Tools that return `list[dict]` SHALL continue working
without modification.

#### Scenario: Existing tracker example is unaffected
- **WHEN** the tracker example (which returns `list[Project]` / `list[Task]`) is run
- **THEN** behavior is byte-identical to v1.0 — no `Query[T]` involvement, no listview semantic changes

### Requirement: lint rule A2K-PUSHDOWN-MISMATCH

A new static rule SHALL warn when a tool's return annotation contains
`Query[T]` but the `@a2kit.list_()` decorator does not declare a
`list_view=ListViewSettings(...)` configuration.

#### Scenario: Mismatch fires
- **WHEN** a tool fn declared as `@a2kit.list_()` (no `list_view=...` kwarg) returns `Query[T]`
- **THEN** A2K-PUSHDOWN-MISMATCH fires pointing at the decorator

#### Scenario: Match silent
- **WHEN** a tool fn declared as `@a2kit.list_(list_view=ListViewSettings(default_fields=("id","title")))` returns `Query[T]`
- **THEN** A2K-PUSHDOWN-MISMATCH does not fire
