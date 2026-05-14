# request-scoped-di — delta

## ADDED Requirements

### Requirement: Production dispatch routes through `Container.dispatch`

Both production dispatch sites (`mcp/server.py::_wrap_with_dispatch_hook` and `cli/runtime.py::_invoke_tool_in_process`) SHALL invoke tools through `app._resolver.dispatch(fn, wire_kwargs, pre_hook=<hook>)`. The async-CM opens a per-call child container, optionally calls the wire-side `pre_hook`, runs `resolve_params(fn)` for DI (Lazy[T] aware), merges, yields kwargs for the wrapper to call `fn(**kw)`, and unwinds the child's cleanup stack on exit.

#### Scenario: per_call resource cleaned up at MCP call exit

- **GIVEN** a tool dispatched through `fastmcp.Client(transport=build_mcp_server(app))`
- **AND** `app.provide(Transaction, per_call=True)` registered
- **AND** the tool body resolves `tx: Transaction`
- **WHEN** the tool returns normally
- **THEN** the `Transaction.__aexit__` runs with `exc=None` exactly once
- **WHEN** the tool raises
- **THEN** the `Transaction.__aexit__` runs with the propagating
  exception exactly once
- **AND** the wire error envelope reflects the body exception (not the
  cleanup state)

#### Scenario: Lazy[T] never invoked under real MCP wire

- **GIVEN** a tool `async def f(b: Lazy[Browser])` dispatched via real
  MCP transport
- **WHEN** the body completes without awaiting `b()`
- **THEN** `Browser.__aenter__` never runs
- **AND** the child container's cleanup stack has no Browser entry to unwind

#### Scenario: per_call resource cleaned up at CLI call exit

- **GIVEN** a tool dispatched via `<app> <tool> --args ...` (CLI runtime)
- **AND** `app.provide(Transaction, per_call=True)` registered
- **WHEN** the CLI invocation completes
- **THEN** `Transaction.__aexit__` ran exactly once, AFTER the tool body

### Requirement: Hookless dispatch composes without `identity_dispatch_hook`

Apps that install no dispatch hook (no connections, no custom hook) SHALL still route through `Container.dispatch(fn, wire_kwargs)` with no `pre_hook` argument. The framework MUST NOT require a sentinel identity function for the no-hook path.

#### Scenario: No-hook tool path

- **GIVEN** an App with no `install_connections` and no `app._dispatch_hook` override
- **WHEN** a tool is dispatched
- **THEN** the wrapper opens `app._resolver.dispatch(fn, wire)` without `pre_hook`
- **AND** the tool body sees DI-resolved kwargs merged with wire kwargs
