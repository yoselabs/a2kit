# mcp-context-passthrough Specification

## Purpose
TBD - created by archiving change fastmcp-context-passthrough. Update Purpose after archive.
## Requirements
### Requirement: a2kit.ToolContext is a re-export of fastmcp.Context

`a2kit.ToolContext` SHALL be an a2kit-owned `@runtime_checkable` Protocol defined in `a2kit._context_protocol`, exposing the cross-transport ctx surface (log family, report_progress, request_id, client_id, elicit, state-store methods). The Protocol SHALL declare the contract; concrete implementations (fastmcp.Context, StderrToolContext, and any future transport's context class) SHALL satisfy it structurally — no subclassing required.

`a2kit.ToolContext is fastmcp.Context` SHALL evaluate to `False` at runtime (identity changes from the prior re-export). Consumer code annotating `ctx: a2kit.ToolContext` continues to work because both `fastmcp.Context` and `StderrToolContext` satisfy the Protocol structurally.

The library SHALL NOT import fastmcp at `a2kit._context_protocol` import time; bare `import a2kit` continues to leave `fastmcp` absent from `sys.modules`.

#### Scenario: Bare a2kit import does not pull fastmcp

- **WHEN** a process executes `import a2kit` and inspects `sys.modules`
- **THEN** `"fastmcp"` is not present in `sys.modules`

#### Scenario: ToolContext is a Protocol, not a fastmcp re-export

- **WHEN** a process executes `import a2kit; t = a2kit.ToolContext`
- **THEN** `t is fastmcp.Context` is `False` (after lazy-importing fastmcp for comparison)
- **AND** `t.__name__` is `"ToolContext"`
- **AND** introspection confirms `t` is a `typing.Protocol`

#### Scenario: fastmcp.Context satisfies the Protocol structurally

- **GIVEN** a process has lazy-imported `fastmcp.Context`
- **AND** an instance `real_ctx: fastmcp.Context` exists (built by the MCP transport)
- **WHEN** the consumer does `isinstance(real_ctx, a2kit.ToolContext)`
- **THEN** the result is `True`

#### Scenario: StderrToolContext satisfies the Protocol structurally

- **WHEN** the consumer does `isinstance(StderrToolContext(), a2kit.ToolContext)`
- **THEN** the result is `True`

#### Scenario: ToolContext appears in a2kit __all__

- **WHEN** a user runs `from a2kit import *`
- **THEN** `ToolContext` is bound in their namespace
- **AND** the value is the Protocol class

### Requirement: MCP transport passes fastmcp.Context through unwrapped

The MCP runtime adapter SHALL pass the live `fastmcp.Context` instance directly to a tool's `ctx` parameter without wrapping or translation. The library SHALL NOT ship `FastMCPContextAdapter` or any equivalent passthrough wrapper.

#### Scenario: Tool receives the live fastmcp.Context
- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext) -> dict`
- **WHEN** the tool is invoked under `<app> serve` and the framework binds `ctx`
- **THEN** `isinstance(ctx, fastmcp.Context)` is `True` and `ctx` is the same object FastMCP would pass to a `@mcp.tool` defined directly against FastMCP

#### Scenario: No FastMCPContextAdapter in the source tree
- **WHEN** the source tree is inspected after the change
- **THEN** no class named `FastMCPContextAdapter` exists under `src/a2kit/`

### Requirement: CLI transport supplies a fastmcp.Context-shaped stub

The CLI runtime SHALL bind a CLI-specific stub class (`StderrToolContext`)
to the `ctx` parameter. The stub SHALL expose every public method of
`fastmcp.Context` as listed in the FastMCP version pinned in
`pyproject.toml`, with **signatures matching `fastmcp.Context` exactly**
(modulo `self`). Stub behavior is defined per-method:

- `debug`, `info`, `warning`, `error` — signature
  `(message: str, logger_name: str | None = None, extra: Mapping[str, Any] | None = None)`.
  Emit a stderr line in the LDD wire format `[ +s.mmm LEVEL] message k=v ...`
  where `k=v` pairs come from `extra` (plus a synthesised `logger=...`
  pair when `logger_name` is provided). The stub SHALL NOT accept
  arbitrary `**fields` kwargs; the kwargs form is reserved for
  `a2kit.ldd.log` (see below).
- `report_progress(progress, total=None, message=None)` — emit a
  stderr line `[ +s.mmm progress] current=N total=M`.
- `elicit(message, response_type=None, *, response_title=None, response_description=None)` —
  render via stdin loop; sentinel `--decline` returns
  `DeclinedElicitation`; EOF/SIGINT returns `CancelledElicitation`;
  otherwise `AcceptedElicitation(data=...)`.
- `read_resource(uri)` — `file://` URIs return contents; other schemes raise `MCPOnlyError`.
- `set_state`, `get_state`, `delete_state` — per-instance dict scoped to one CLI invocation.
- `send_log_message(level, logger, data)` — emit a stderr line in LDD wire format.
- `sample`, `list_resources`, `list_prompts`, `get_prompt`, `list_roots`,
  `send_notification` — raise `MCPOnlyError`.

#### Scenario: Plain logging works in CLI

- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext) -> str` calling `ctx.info("hi")`
- **WHEN** the tool runs via `<app> tasks t`
- **THEN** stderr contains a line matching `[ +\d+\.\d+ INFO    ] hi`

#### Scenario: Logging with extra works in CLI

- **GIVEN** a tool calling `await ctx.info("hi", extra={"x": 1})`
- **WHEN** the tool runs via CLI
- **THEN** stderr contains a line matching `[ +\d+\.\d+ INFO    ] hi x=1`

#### Scenario: Stub signatures match fastmcp.Context

- **WHEN** `inspect.signature(StderrToolContext.<method>)` is compared
  against `inspect.signature(fastmcp.Context.<method>)` for each of
  `info`, `warning`, `error`, `debug`, `log`, `report_progress`,
  `read_resource`, `elicit`, `set_state`, `get_state`, `delete_state`
- **THEN** the signatures are identical modulo the `self` parameter

#### Scenario: Kwargs on ctx.info are rejected

- **GIVEN** a tool calling `await ctx.info("hi", foo=1)`
- **WHEN** the tool runs via CLI **or** MCP
- **THEN** the call raises `TypeError`. The tool is expected to use
  `await a2kit.ldd.info(ctx, "hi", foo=1)` instead.

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

### Requirement: LDD event and report primitives are protocol-neutral functions

The library SHALL expose `a2kit.ldd.event(ctx, ...)`,
`a2kit.ldd.report(ctx, ...)`, and `a2kit.ldd.log(ctx, level, msg_or_instance, **fields)`
as free functions that accept any `fastmcp.Context`-shaped object. The
three SHALL share a single dispatch shape (identity-check against the
live ctx type and route to either `ctx.log(extra=...)` on MCP or
`StderrToolContext._emit(...)` on CLI).

`a2kit.ldd.log` SHALL accept two call forms, matching `event`'s
shape verbatim:

- **String form**: `log(ctx, "info", "msg", k=v, ...)`. Third
  positional is the message; remaining kwargs are fields.
- **Instance form**: `log(ctx, "info", instance)`. Third positional
  is a dataclass / pydantic `BaseModel` / object. Message defaults
  to `type(instance).__name__`; fields derive via
  `model_dump(mode="json")` (pydantic), `dataclasses.asdict`
  (dataclass), or `vars(instance)` (fallback). `Enum` values
  are unwrapped to `.value`.

Convenience aliases `a2kit.ldd.info`, `warning`, `error`, `debug`
forward to `log` with the appropriate level literal and accept the
same two forms.

The library SHALL NOT add `event`, `report`, or `log` methods to the
`a2kit.ToolContext` re-export. Existing `--no-events` / `--no-reports`
CLI flags and the `A2KIT_LDD` env var SHALL gate these primitives;
`log` SHALL share the events flag's kill-switch.

#### Scenario: a2kit.ldd.info delivers a structured message on MCP

- **GIVEN** a tool calling `await a2kit.ldd.info(ctx, "starting", batch=2)`
- **WHEN** the tool runs under `<app> serve` via `fastmcp.Client`
- **THEN** the client receives a `notifications/message` whose
  `level="info"`, `message="starting"`, `extra={"batch": 2, "elapsed_ms": ...}`

#### Scenario: a2kit.ldd.info renders the same line on CLI

- **GIVEN** the same tool
- **WHEN** the tool runs via `<app> tasks t`
- **THEN** stderr contains a line matching `[ +\d+\.\d+ INFO    ] starting batch=2`

#### Scenario: Both transports agree on payload contents

- **GIVEN** identical `a2kit.ldd.info(ctx, "x", n=42)` calls under
  MCP and CLI
- **THEN** the structured `extra` payload (or its CLI `key=value`
  rendering) carries the same fields with the same values, except
  for transport-specific framing. `elapsed_ms` appears in both.

#### Scenario: Instance form derives message and fields

- **GIVEN** `@dataclass class ImportStarted: file: str; batch: int`
- **WHEN** `await a2kit.ldd.info(ctx, ImportStarted(file="/x.csv", batch=2))` is called
- **THEN** the delivered payload has `message="ImportStarted"` and
  `extra={"file": "/x.csv", "batch": 2, "elapsed_ms": ...}` on MCP,
  rendering as `[ +s.mmm INFO    ] ImportStarted file=/x.csv batch=2` on CLI

#### Scenario: Instance form and string form produce identical wire payload

- **GIVEN** `MyDC(x=1, y=2)` as a dataclass
- **WHEN** `a2kit.ldd.info(ctx, MyDC(x=1, y=2))` and
  `a2kit.ldd.info(ctx, "MyDC", x=1, y=2)` are called
- **THEN** the delivered `extra` (MCP) or rendered key=value pairs
  (CLI) are identical key-for-key, except `elapsed_ms`

#### Scenario: msg is capped at 60 chars before transport

- **WHEN** `a2kit.ldd.info(ctx, "<200-char string>", k=1)` is called on either transport
- **THEN** the delivered `message` (MCP) or rendered text (CLI) is
  exactly 60 characters with the final character `…`

### Requirement: LDD wire-format invariants are owned by `a2kit.ldd`

Every event delivered via `a2kit.ldd.event(ctx, name, **kw)` SHALL carry an `elapsed_ms` integer in its structured payload, computed as `int((monotonic() - app_start_monotonic) * 1000)` where `app_start_monotonic` is captured at first emit (or at App `__aenter__` when the lifecycle ran). The CLI rendering SHALL prefix every line with `+s.mmm` relative time using zero-padded three-decimal milliseconds. The human-readable text portion of any LDD line SHALL be capped at 60 characters with `…` elision when truncated. The CLI stub `send_log_message` rendering and the MCP `notifications/message` payload (carrying the same `level`, `logger`, `data`) SHALL agree on the structured `data` field's contents key-for-key — transports may differ on framing only, never on the structured payload.

#### Scenario: elapsed_ms increases monotonically

- **WHEN** two `a2kit.ldd.event` calls happen 50 ms apart in the same process
- **THEN** the second emission's `elapsed_ms` is greater than the first's by approximately 50 (within OS scheduler tolerance)

#### Scenario: text capped at 60 chars

- **WHEN** `a2kit.ldd.info(ctx, "<200-char string>", k=1)` is called
- **THEN** the delivered/rendered text portion is exactly 60 characters with the final character `…`

### Requirement: Typed event registry on `app.ldd.events`

The `App` class SHALL expose `app.ldd.events: EventRegistry`. The registry SHALL provide `register(model: type[BaseModel], *, progress: Callable[[BaseModel], float] | None = None) -> None` and `async emit_typed(event: BaseModel) -> None`. `emit_typed` SHALL NOT take a `ctx` argument; it resolves the live context from the ambient `_LddState`. `emit_typed` SHALL serialize `event` via `event.model_dump(mode="json")`, call the underlying `a2kit.ldd.event(event.__class__.__name__, **dumped)`, and — if a `progress` callback is registered for `event.__class__` — additionally call `ctx.report_progress(progress(event), 1.0)` on the ambient context. Re-registration is last-write-wins. One progress callback per event class; consumers compose at the callback level if they need composite progress.

#### Scenario: Register and emit typed event

- **GIVEN** `app.ldd.events.register(TierEnded, progress=lambda e: 0.5)` registered
- **AND** an active dispatch with live `ctx`
- **WHEN** `await app.ldd.events.emit_typed(TierEnded(step="raw", verdict="ok"))` is called
- **THEN** `a2kit.ldd.event("TierEnded", step="raw", verdict="ok")` runs first using the ambient ctx
- **AND** `ctx.report_progress(0.5, 1.0)` runs immediately after on the same ambient ctx

#### Scenario: Unregistered model emits without progress

- **GIVEN** no registration for `OtherEvent`
- **WHEN** `await app.ldd.events.emit_typed(OtherEvent(...))` is called inside a dispatch
- **THEN** the underlying `event` is invoked but no progress call is made

#### Scenario: Re-registration is last-write-wins

- **WHEN** `register(TierEnded, progress=fn_a)` is followed by `register(TierEnded, progress=fn_b)`
- **THEN** subsequent `emit_typed` for `TierEnded` uses `fn_b`

#### Scenario: model_dump uses JSON mode

- **GIVEN** an event model whose fields include a `datetime` value
- **WHEN** `emit_typed` is called inside a dispatch
- **THEN** the underlying `event` call receives the datetime serialized as an ISO-8601 string (the `model_dump(mode="json")` coercion)

### Requirement: Ambient context binding via dispatch contextvar

The library SHALL bind the live transport context (`fastmcp.Context` under MCP, the CLI stub under CLI, the test-client stub under in-process tests) into the per-call `_LddState` carried by `_LDD_STATE: ContextVar[_LddState | None]`. The `ldd_state_for_call(...)` contextmanager SHALL take a required `ctx` keyword argument and store it on the `_LddState` instance set on entry. All LDD primitives SHALL resolve their transport context from `_LDD_STATE.get().ctx` rather than accepting `ctx` as a parameter.

The three dispatch sites SHALL pass `ctx` into `ldd_state_for_call` **only when the tool declared a ctx parameter** (i.e. `meta.context_param_name` is truthy):

- MCP runtime (`_wrap_with_ldd_state` in `a2kit.packages.mcp.server`) installs the wrapper only when `meta.context_param_name` is truthy and passes the `fastmcp.Context` injected by FastMCP.
- CLI runtime (`_invoke_tool_in_process` in `a2kit.packages.cli.runtime`) opens `ldd_state_for_call` only when `ctx_param_name` is truthy and passes the `StderrToolContext` instance bound on the call kwargs. The CLI runtime SHALL NOT synthesize a `StderrToolContext` for tools that did not declare `ctx`.
- In-process test client (`TestClient.invoke` in `a2kit.packages.testing.client`) opens `ldd_state_for_call` only when `meta.context_param_name` is truthy and passes the `_CapturingContext` bound on the call kwargs. The test client SHALL NOT synthesize a capturing context for tools that did not declare `ctx`.

A tool that calls any LDD primitive (`a2kit.ldd.event`, `a2kit.ldd.log`, `a2kit.ldd.info`, etc.) but did NOT declare `ctx: a2kit.ToolContext` SHALL therefore raise `AmbientContextMissing` uniformly across MCP, CLI, and TestClient — there is no transport on which the missing-ctx case silently succeeds.

`contextvars.ContextVar.set` / `.reset` token semantics SHALL be honored — every entry into `ldd_state_for_call` is paired with an exit that resets to the prior state. Nested dispatch (e.g. tool A invokes tool B via the test client) SHALL be supported by the token stack with no additional locking.

#### Scenario: MCP dispatch binds the live fastmcp.Context

- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext) -> None: await a2kit.ldd.event("x", k=1)`
- **WHEN** the tool runs under `<app> serve` and FastMCP injects `ctx`
- **THEN** the MCP client receives the `notifications/message` for `"x"` carrying `k=1`
- **AND** the `event` call did not pass `ctx` and did not raise

#### Scenario: CLI dispatch binds the StderrToolContext

- **GIVEN** a tool calling `await a2kit.ldd.info("msg", k=1)` with no `ctx` argument
- **WHEN** the tool runs via `<app> tasks t`
- **THEN** stderr contains a line matching `[ +\d+\.\d+ INFO    ] msg k=1`

#### Scenario: TestClient dispatch binds the test stub

- **GIVEN** a tool calling `await a2kit.ldd.event("x", k=1)` and the in-process `TestClient`
- **WHEN** `await client.call_tool("t", {})` is awaited
- **THEN** the captured emission carries `name="x"` and `k=1` with the test stub as the bound ctx

#### Scenario: Concurrent gather sees the same ambient ctx

- **GIVEN** a tool body that runs `await asyncio.gather(sub_a(), sub_b())` where both sub-coroutines call `a2kit.ldd.event(...)`
- **WHEN** the tool runs under MCP
- **THEN** both emissions resolve to the same ambient `ctx` (the dispatcher's injected `fastmcp.Context`) and neither raises

#### Scenario: Nested dispatch shadows then restores ambient ctx

- **GIVEN** tool A whose body invokes tool B via the in-process test client, where both A and B call `a2kit.ldd.event(...)`
- **WHEN** A runs and B is dispatched mid-way
- **THEN** events emitted from inside B resolve to B's dispatch ctx
- **AND** events emitted from A after B returns resolve again to A's dispatch ctx

#### Scenario: CLI dispatch on a no-ctx tool does not synthesize StderrToolContext

- **GIVEN** a tool `async def t() -> None: await a2kit.ldd.event("x", k=1)` that did NOT declare `ctx`
- **WHEN** the tool runs via `<app> tasks t`
- **THEN** the LDD call raises `AmbientContextMissing` with a message naming `a2kit.ldd.event`
- **AND** the CLI runtime did not synthesize a `StderrToolContext` for the call

#### Scenario: TestClient dispatch on a no-ctx tool does not synthesize a capturing context

- **GIVEN** a tool `async def t() -> None: await a2kit.ldd.event("x", k=1)` that did NOT declare `ctx`
- **WHEN** a test runs `await client.invoke("t")`
- **THEN** the LDD call raises `AmbientContextMissing` with a message naming `a2kit.ldd.event`
- **AND** `client.events` remains empty (no synthesized capturing-context binding)

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

### Requirement: Decoration-time invariant — rewritten MCP signature contains ctx

When the MCP runtime wraps a tool function with the dispatch-hook signature rewrite, the rewritten `__signature__` SHALL contain the tool's ctx parameter name whenever `A2KitMeta.context_param_name` is non-None for that tool. The rewrite SHALL raise `a2kit.exceptions.A2KitContextBindingBroken` at App-construction time if the invariant does not hold.

The check is framework-internal: user code cannot cause it to fire. Its purpose is to catch wrapper-chain regressions immediately when the App is constructed, before any tool call reaches a real transport.

#### Scenario: App fails to build when wrapper chain drops ctx

- **GIVEN** a hypothetical regression in `_wrap_with_dispatch_hook` that produces a rewritten signature missing the ctx parameter
- **WHEN** `App.add_router` runs and the MCP wrapper chain is assembled for a tool with `ctx: a2kit.ToolContext`
- **THEN** the call raises `A2KitContextBindingBroken` with `fn_name` and `ctx_param_name` attributes
- **AND** the error message identifies the regression as framework-internal and instructs the user to file an issue

#### Scenario: Normal apps build without raising

- **GIVEN** a correctly-functioning a2kit installation (post fix-mcp-dispatch-strips-ctx)
- **WHEN** any App with any tool combination is built
- **THEN** no `A2KitContextBindingBroken` exception is raised

### Requirement: Optional-ctx annotation form rejected at decoration time

A tool function's ctx parameter annotation MUST be exactly `a2kit.ToolContext` (or equivalent re-export of `fastmcp.Context`). Annotations of the form `ctx: ToolContext | None`, `ctx: Optional[ToolContext]`, or `ctx: Union[ToolContext, None]` SHALL be rejected at decoration time with `a2kit.exceptions.A2KitInvalidContextAnnotation`.

The rejection enforces the runtime invariant that ctx is always bound by the dispatcher when declared: there is no transport or test path that produces a `None` ctx for a declared parameter. The Optional form is misleading typing with no corresponding runtime semantics.

#### Scenario: Optional ctx rejected

- **GIVEN** a tool body `async def t(*, msg: str, ctx: a2kit.ToolContext | None = None) -> dict`
- **WHEN** `@a2kit.read()` decorates the function
- **THEN** the decoration raises `A2KitInvalidContextAnnotation`
- **AND** the message identifies the parameter name and includes the hint "ctx is always bound by the dispatcher when declared; drop '| None' from the annotation, or remove ctx entirely if the tool does not need it."

#### Scenario: Plain ToolContext accepted

- **GIVEN** a tool body `async def t(*, msg: str, ctx: a2kit.ToolContext) -> dict`
- **WHEN** `@a2kit.read()` decorates the function
- **THEN** the decoration succeeds and `A2KitMeta.context_param_name == "ctx"`

#### Scenario: No ctx declaration accepted

- **GIVEN** a tool body `async def t(*, msg: str) -> dict`
- **WHEN** `@a2kit.read()` decorates the function
- **THEN** the decoration succeeds and `A2KitMeta.context_param_name is None`

### Requirement: Transport-parity matrix

A test suite SHALL pin the contract that a tool's behavior is identical across the CLI and MCP transports for the four canonical declaration combinations of `(state-DI present, ctx-DI present)`. The suite SHALL drive the MCP transport through `fastmcp.Client(transport=build_mcp_server(app))` (not the in-process test client) so the full production wrapper chain — including `_wrap_with_dispatch_hook`'s signature rewrite and `_wrap_with_ldd_state`'s ambient binding — is exercised. The suite SHALL assert both successful-payload structural equality and exact exception-class parity on misuse cases.

#### Scenario: All four declaration combos pass parity

- **GIVEN** the test fixture App with four tools: `tool_none` (neither), `tool_state` (state only), `tool_ctx` (ctx only), `tool_both` (both)
- **WHEN** each tool is invoked over both CLI and MCP with the same kwargs
- **THEN** the returned payloads are structurally equal across transports for every tool

#### Scenario: Error class parity for unknown-kwarg misuse

- **GIVEN** a tool `tool_none` invoked with an unknown kwarg `extra="y"`
- **WHEN** invoked on each transport
- **THEN** both transports surface an error of the same Python exception class (`TypeError`)

### Requirement: Field-bearing logging lives on `a2kit.ldd.*`, not on `ctx.*`

The library SHALL document `a2kit.ldd.info` (and siblings) as the
canonical structured-narrative logging primitive. The library SHALL
treat `ctx.info(msg, **fields)` (with kwargs other than `logger_name`
/ `extra`) as an antipattern and reject it at runtime via fastmcp's
narrow signature.

#### Scenario: Antipattern is documented

- **WHEN** the ANTIPATTERNS.md is inspected
- **THEN** an entry exists titled "Kwargs on `ctx.info/warning/error/debug`"
  with the recommended replacement `a2kit.ldd.info(ctx, ...)` and a
  pointer to this requirement.

<!--
  Removed-requirement note: the legacy "Logging works in CLI with kwargs form"
  requirement is not present in the canonical mcp-context-passthrough spec at
  archive time (kwargs-on-ctx logging was never a SHALL-level requirement, only
  an asserted behaviour in prior tests). No REMOVED clause is emitted.

  Migration carried over:
  `s/await ctx\.(info|warning|error|debug)\("([^"]*)", ([^=)]+=.*)\)/await a2kit.ldd.\1(ctx, "\2", \3)/`
  catches the documented call shapes. `ctx.info("plain string")` and
  `ctx.info("msg", extra={...})` continue to work — they were always
  fastmcp-compatible.
-->

### Requirement: Unknown kwargs are rejected at both transport boundaries

The framework SHALL reject any kwarg that is not declared on the tool
signature at both the MCP transport boundary and the CLI runtime
dispatcher. Behaviour:

- **MCP transport** (`fastmcp.Client` → `build_mcp_server(app)`):
  unknown kwargs surface as a `ToolError(json)` whose decoded envelope
  carries `class: "TypeError"` and `message` naming the unexpected
  parameter(s).
- **CLI runtime dispatcher** (`_invoke_tool_in_process` and any
  caller of it that bypasses Typer's flag-parsing layer): unknown
  kwargs raise `TypeError` directly with the same message shape.
- **CLI Typer surface** (`<app> tasks <name> --known --unknown=...`):
  unknown CLI flags are rejected by Typer with `BadParameter`. This
  is upstream of the framework and continues to behave as today.

The contract is "both transport boundaries fail loudly on unknown
kwargs"; the consumer's choice of programmatic surface (`TestClient`,
direct `_invoke_tool_in_process`, real `fastmcp.Client`) does not
change the rejection semantics — only the error envelope shape.

#### Scenario: FastMCP rejects unknown kwarg over real transport

- **GIVEN** a tool declared as `async def t(*, msg: str) -> dict`
- **WHEN** the test calls `await c.call_tool("t", {"msg": "x", "extra": "y"})` over `fastmcp.Client(transport=build_mcp_server(app))`
- **THEN** the client receives a `ToolError` whose `json.loads(str(exc))` payload has `class == "TypeError"` and `message` references `"extra"`

#### Scenario: CLI runtime dispatcher rejects unknown kwarg

- **GIVEN** the same tool, called via `_invoke_tool_in_process(t.fn, {"msg": "x", "extra": "y"}, ...)`
- **WHEN** the call is awaited
- **THEN** `TypeError` is raised before `fn(**call_kwargs)` executes; the message references `"extra"`

#### Scenario: TestClient surfaces the same envelope shape as production MCP

- **GIVEN** the same tool, called via `async with a2kit.testing.client(app) as c: await c.invoke("t", msg="x", extra="y")`
- **WHEN** the call is awaited
- **THEN** `fastmcp.exceptions.ToolError` is raised; `json.loads(str(exc))["class"] == "TypeError"`

#### Scenario: Both transports produce the same class identity

- **GIVEN** identical calls to a tool with an undeclared kwarg over MCP and via the runtime dispatcher
- **THEN** both error paths surface a `TypeError` (directly, or wrapped in a `ToolError` envelope whose decoded `class` is `"TypeError"`); the consumer can write a single matcher that handles both

### Requirement: Ambient ctx is non-None inside any framework dispatch

The MCP wrapper and CLI runtime SHALL bind a non-None `ctx` into the ambient `_LDD_STATE` for every framework-dispatched tool, regardless of whether the tool's body declares `ctx: a2kit.ToolContext`.

Implementation:

- **MCP**: the rewritten wrapper signature SHALL always include a
  ctx Parameter (named `_a2kit_ctx` when the tool body did not
  declare one) annotated `fastmcp.Context`. fastmcp injects the
  live context via its standard introspection. The wrapper extracts
  ctx from kwargs into ambient state.
- **CLI**: the runtime SHALL synthesize `StderrToolContext()` for
  ambient binding even when the tool body does not declare ctx.

In both transports, the ctx kwarg SHALL be passed to the tool body
ONLY when the tool's *original* signature declared it. The
synthesized `_a2kit_ctx` Parameter (MCP) is a framework-internal
mechanism for ambient binding and SHALL NOT leak into tool body
kwargs.

This requirement establishes the invariant: **inside any framework dispatch, the ambient context resolved from the `_LDD_STATE` ContextVar is non-None**, so every LDD primitive has a live transport context to dispatch against.

#### Scenario: MCP transport — tool without ctx param emits LDD

- **GIVEN** a tool `async def fetch(*, url: str) -> dict: await a2kit.ldd.event("fetch", url=url); return {}` registered on a Router
- **WHEN** a real `fastmcp.Client(transport=...)` invokes `fetch(url="https://example/")`
- **THEN** the invocation completes without raising `AmbientContextMissing`
- **AND** the captured event surfaces on the test client's `events` list with name `"fetch"` and payload `{"url": "https://example/"}`
- **AND** the tool body received no `ctx` kwarg (its signature did not declare one)

#### Scenario: CLI runtime — tool without ctx param emits LDD

- **GIVEN** the same tool shape
- **WHEN** invoked via the CLI runtime
- **THEN** the invocation completes without raising
- **AND** the stderr capture contains an LDD-formatted line matching the event

#### Scenario: Tool with ctx param — today's behaviour preserved

- **GIVEN** a tool `async def scrape(*, target: str, ctx: a2kit.ToolContext) -> dict: ...`
- **WHEN** invoked under any transport
- **THEN** the tool body receives the live ctx as a kwarg (unchanged from today)
- **AND** ambient state has the same ctx instance

#### Scenario: Synthesized ctx name does not collide with consumer params

- **GIVEN** a Router with tools declaring various param names (`url`, `target`, `state`, etc.)
- **WHEN** the framework synthesizes the `_a2kit_ctx` Parameter in rewritten signatures
- **THEN** no consumer-defined param name collides (the `_a2kit_*` prefix is reserved by the framework)
- **AND** the synthesized parameter never appears in any tool body's kwargs

