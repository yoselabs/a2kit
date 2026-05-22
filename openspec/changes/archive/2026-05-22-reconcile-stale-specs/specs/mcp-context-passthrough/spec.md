## MODIFIED Requirements

### Requirement: ctx parameter excluded from input schema

When a tool function declares a parameter typed `a2kit.ToolContext` (i.e. `fastmcp.Context`), schema generation, CLI option synthesis, and MCP wire-input synthesis SHALL exclude that parameter from the **user-facing input surface** — that is, the agent-supplied `inputSchema` over MCP and the `--option`-style command-line flags over CLI.

The exclusion SHALL apply only to the user-facing input surface. The **internal** call-time signature that the MCP transport introspects to bind framework-supplied parameters (notably the live `fastmcp.Context`) SHALL retain the ctx parameter so that FastMCP injects it at dispatch time. Wrapper code that rewrites a tool's `__signature__` for FastMCP introspection MUST include the ctx parameter when the tool declares one.

#### Scenario: ctx omitted from MCP schema

- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext, name: str) -> str`
- **WHEN** the MCP tool schema is generated
- **THEN** the schema input properties include `name` only

#### Scenario: ctx omitted from CLI options

- **GIVEN** the same tool registered in a CLI app
- **WHEN** the user runs `<app> tasks t --help`
- **THEN** the option list shows `--name` and not `--ctx`

#### Scenario: ctx preserved in internal call-time signature over MCP

- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext, name: str, state: AppState) -> str` where `state: AppState` is supplied via `app.provide(AppState, ...)`
- **WHEN** the MCP transport assembles the wrapper chain for `t` and FastMCP introspects the outermost wrapped function
- **THEN** the introspected signature contains both `name` and `ctx` (FastMCP-injected) as keyword-only parameters
- **AND** an `mcp` `tools/call` with `arguments={"name": "x"}` reaches `t`'s body with all three kwargs (`name`, `ctx`, `state`) bound and returns successfully

#### Scenario: ctx and container-DI combine cleanly over MCP

- **GIVEN** a tool that declares both `state: T` (container-resolved) AND `ctx: a2kit.ToolContext`
- **WHEN** the tool is invoked via `fastmcp.Client(transport=build_mcp_server(app))`
- **THEN** the response is a successful tool result (NOT `{isError: true}`)
- **AND** the body received both `state` (from the container) and `ctx` (from FastMCP)

### Requirement: LDD wire-format invariants are owned by `a2kit.ldd`

Every event delivered via `a2kit.ldd.event(ctx, name, **kw)` SHALL carry an `elapsed_ms` integer in its structured payload, computed as `int((monotonic() - app_start_monotonic) * 1000)` where `app_start_monotonic` is captured at first emit (or at App `__aenter__` when the lifecycle ran — there is no `App.on_startup` hook). The CLI rendering SHALL prefix every line with `+s.mmm` relative time using zero-padded three-decimal milliseconds. The human-readable text portion of any LDD line SHALL be capped at 60 characters with `…` elision when truncated. The CLI stub `send_log_message` rendering and the MCP `notifications/message` payload (carrying the same `level`, `logger`, `data`) SHALL agree on the structured `data` field's contents key-for-key — transports may differ on framing only, never on the structured payload.

#### Scenario: elapsed_ms increases monotonically

- **WHEN** two `a2kit.ldd.event` calls happen 50 ms apart in the same process
- **THEN** the second emission's `elapsed_ms` is greater than the first's by approximately 50 (within OS scheduler tolerance)

#### Scenario: text capped at 60 chars

- **WHEN** `a2kit.ldd.info(ctx, "<200-char string>", k=1)` is called
- **THEN** the delivered/rendered text portion is exactly 60 characters with the final character `…`

### Requirement: LDD primitives raise when called outside a dispatch

If any of `a2kit.ldd.event`, `a2kit.ldd.report`, `a2kit.ldd.log`, `a2kit.ldd.debug`, `a2kit.ldd.info`, `a2kit.ldd.warning`, `a2kit.ldd.error`, or `EventRegistry.emit_typed` is invoked while `_LDD_STATE.get()` is `None` (i.e. no active `ldd_state_for_call` scope on the current `contextvars.Context`), the call SHALL raise `AmbientContextMissing` (a subclass of `RuntimeError`). The exception message SHALL name the **invoked function** and SHALL indicate that the primitive must be called from inside a tool body. Shorthand primitives (`debug`, `info`, `warning`, `error`) that delegate internally to `log` SHALL still surface their own name in the message. The library SHALL NOT silently no-op and SHALL NOT synthesize a fallback context.

#### Scenario: Calling event outside a dispatch raises

- **GIVEN** a module-level coroutine that calls `await a2kit.ldd.event("x", k=1)` without first entering `ldd_state_for_call`
- **WHEN** the coroutine is awaited
- **THEN** `AmbientContextMissing` is raised
- **AND** the message contains `"a2kit.ldd.event"` and references the tool-body dispatch contract

#### Scenario: Calling log outside any dispatch scope raises

- **GIVEN** a coroutine that calls `await a2kit.ldd.info("starting")` outside any `ldd_state_for_call` scope (for example from imperative startup code run before `async with app:`)
- **WHEN** the coroutine is awaited
- **THEN** `AmbientContextMissing` is raised

#### Scenario: emit_typed raises outside a dispatch

- **GIVEN** a coroutine that calls `await app.ldd.events.emit_typed(TierEnded(...))` outside any dispatch
- **WHEN** the coroutine is awaited
- **THEN** `AmbientContextMissing` is raised

#### Scenario: Shorthand info names itself in the error message

- **GIVEN** a module-level coroutine that calls `await a2kit.ldd.info("x", k=1)` without first entering `ldd_state_for_call`
- **WHEN** the coroutine is awaited
- **THEN** `AmbientContextMissing` is raised whose message names `"a2kit.ldd.info"` (its own name, not `"a2kit.ldd.log"`)
