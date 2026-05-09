## MODIFIED Requirements

### Requirement: Verb decorators map to MCP `ToolAnnotations` + tags

`@a2kit.read`, `@a2kit.write`, and `@a2kit.list_` SHALL be thin sugar
over `FastMCP.tool(annotations=ToolAnnotations(...), tags=...)`. Each
verb decorator SHALL be implementable in ≤ 10 lines.

`@a2kit.list_()` tools MAY return either:

- `list[dict]` / `list[BaseModel]` — the existing v1.0 behavior;
  listview semantics applied **post-hoc** by the middleware.
- `Query[T]` from `a2kit.pushdown` — the **pushdown** path; listview
  semantics applied through the wrapped adapter, then `execute()`d
  against the underlying service.

#### Scenario: read maps to readOnlyHint=True
- **WHEN** a function is decorated with `@a2kit.read`
- **THEN** the underlying FastMCP tool registration receives `ToolAnnotations(readOnlyHint=True, destructiveHint=False)`

#### Scenario: write maps to readOnlyHint=False, destructiveHint=True
- **WHEN** a function is decorated with `@a2kit.write`
- **THEN** the underlying FastMCP tool registration receives `ToolAnnotations(readOnlyHint=False, destructiveHint=True)`

#### Scenario: list_ accepts Query[T] return
- **WHEN** an `@a2kit.list_()` tool returns `Query(adapter, state)`
- **THEN** the listview middleware delegates filter / fields / page semantics to the adapter, calls `await adapter.execute(state)`, and returns the materialized rows

#### Scenario: list_ still accepts list[dict] return
- **WHEN** an `@a2kit.list_()` tool returns `list[dict]` (the v1.0 shape)
- **THEN** the listview middleware applies post-hoc filter / fields / page on the in-memory list (existing v1.0 behavior, byte-identical)

### Requirement: Enrichers are protocol-neutral; both MCP and CLI honor them

`packages/enrichers/` SHALL ship a generic `wrap(fn, enricher)` helper
that wraps a tool function with try/except → enricher transform. Both
the MCP adapter (`packages/mcp/build_mcp_server`) and the CLI adapter
(`packages/cli/build_cli`) SHALL apply this wrapping when registering
tools. Enrichers SHALL NOT be implemented as FastMCP `Middleware`
subclasses.

The enricher wrap SHALL run **before** the listview branch — that
is, `wrap(fn, enricher)` first transforms exceptions raised by the
tool body OR by the pushdown adapter's `execute(...)`. Pushdown
errors are tool errors from the agent's perspective.

#### Scenario: Enricher fires identically for MCP and CLI invocations
- **WHEN** a tool fn declared with an `enricher=` decorator argument raises an exception
- **THEN** the enricher transforms the exception identically whether invoked via `tracker tasks list-tasks` (CLI) or `tracker serve` (MCP)

#### Scenario: Enricher catches pushdown adapter errors
- **WHEN** a tool returns `Query[T]` and the adapter's `execute()` raises an exception
- **THEN** the enricher (if configured) transforms the exception before it surfaces to the agent
