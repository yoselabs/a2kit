# mcp-context-passthrough Specification

## Purpose
TBD - created by archiving change fastmcp-context-passthrough. Update Purpose after archive.
## Requirements
### Requirement: a2kit.ToolContext is a re-export of fastmcp.Context

The library SHALL expose `a2kit.ToolContext` as a lazy re-export of `fastmcp.Context` via PEP 562 module-level `__getattr__` on the `a2kit` package. The library SHALL NOT define an independent `ToolContext` Protocol or subclass `fastmcp.Context`. `a2kit.ToolContext is fastmcp.Context` SHALL evaluate to `True` at runtime.

#### Scenario: Bare a2kit import does not pull fastmcp
- **WHEN** a process executes `import a2kit` and inspects `sys.modules`
- **THEN** `"fastmcp"` is not present in `sys.modules`

#### Scenario: Accessing ToolContext resolves to fastmcp.Context
- **WHEN** a process executes `import a2kit; t = a2kit.ToolContext`
- **THEN** `t is fastmcp.Context` is `True`

#### Scenario: ToolContext appears in a2kit __all__
- **WHEN** a user runs `from a2kit import *`
- **THEN** `ToolContext` is bound in their namespace

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

The CLI runtime SHALL bind a CLI-specific stub class (the rewritten `StderrToolContext`) to the `ctx` parameter. The stub SHALL expose every public method of `fastmcp.Context` as listed in the FastMCP version pinned in `pyproject.toml`. Stub behavior is defined per-method:

- `debug`, `info`, `warning`, `error` — emit a stderr line in the existing LDD wire format `[ +s.mmm LEVEL] msg key=val`.
- `report_progress(current, total)` — emit a stderr line `[ +s.mmm progress] current=N total=M`.
- `elicit(message, response_type)` — render the elicitation JSON schema as a sequence of `click.prompt` calls and return an `ElicitResult` with `action="accept"` and validated `data`. Ctrl-D (EOF) returns `action="cancel"`. A literal sentinel input `--decline` returns `action="decline"`.
- `read_resource(uri)` — for `file://` URIs, read and return the file contents; for any other scheme, raise `MCPOnlyError`.
- `set_state(key, value)`, `get_state(key)`, `delete_state(key)` — operate on a per-instance in-memory dict scoped to one CLI invocation.
- `send_log_message(level, logger, data)` — emit a stderr line in LDD wire format `[ +s.mmm <LEVEL>] <logger> <key=value pairs>` where `data` dict entries are rendered as space-separated `key=value` (non-JSON-serializable values coerced via `str(v)`). Honors the LDD events kill-switch: when `app.ldd_events()` is `False` (or env `A2KIT_LDD=off`), the call is a no-op. This primitive backs `a2kit.ldd.event`'s CLI rendering.
- `sample`, `list_resources`, `list_prompts`, `get_prompt`, `list_roots`, `send_notification` — raise `MCPOnlyError` (subclass of `RuntimeError`) with a message identifying the method and pointing the user at MCP transport.

#### Scenario: Logging works in CLI
- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext) -> str` calling `ctx.info("hi", x=1)`
- **WHEN** the tool runs via `<app> tasks t`
- **THEN** stderr contains a line matching `[ +\d+\.\d+ INFO    ] hi x=1`

#### Scenario: Elicit prompts on stdin
- **GIVEN** a tool calling `await ctx.elicit("info", response_type=UserInfo)` where `UserInfo` is a dataclass `(name: str, age: int)`
- **WHEN** the tool runs via CLI with stdin `Alice\n42\n`
- **THEN** the call returns `ElicitResult(action="accept", data=UserInfo(name="Alice", age=42))`

#### Scenario: Sample raises MCPOnlyError
- **GIVEN** a tool calling `await ctx.sample("hello")`
- **WHEN** the tool runs via CLI
- **THEN** the call raises `MCPOnlyError` with a message containing `"sample"` and `"MCP transport"`

#### Scenario: read_resource handles file:// URIs only
- **WHEN** a tool calls `ctx.read_resource("file:///tmp/x.txt")` in CLI
- **THEN** the file is read and its contents returned
- **WHEN** a tool calls `ctx.read_resource("https://example.com/")` in CLI
- **THEN** the call raises `MCPOnlyError`

#### Scenario: State scoped to a single invocation
- **WHEN** a tool calls `ctx.set_state("k", "v")` then `ctx.get_state("k")` in the same CLI invocation
- **THEN** the second call returns `"v"`
- **WHEN** a separate CLI invocation of the same tool calls `ctx.get_state("k")`
- **THEN** the call returns `None`

#### Scenario: Stub stays in lockstep with fastmcp.Context surface
- **WHEN** the CLI stub class is inspected at test time against `dir(fastmcp.Context)`
- **THEN** every public method (non-`_` prefixed) on `fastmcp.Context` is either implemented on the stub or in the documented MCP-only allowlist

### Requirement: ctx parameter excluded from input schema

When a tool function declares a parameter typed `a2kit.ToolContext` (i.e. `fastmcp.Context`), schema generation, CLI option synthesis, and MCP wire-input synthesis SHALL exclude that parameter from the user-facing input surface.

#### Scenario: ctx omitted from MCP schema
- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext, name: str) -> str`
- **WHEN** the MCP tool schema is generated
- **THEN** the schema input properties include `name` only

#### Scenario: ctx omitted from CLI options
- **GIVEN** the same tool registered in a CLI app
- **WHEN** the user runs `<app> tasks t --help`
- **THEN** the option list shows `--name` and not `--ctx`

### Requirement: LDD event and report primitives are protocol-neutral functions

The library SHALL expose `a2kit.ldd.event(payload, *, name=None, **kw)`, `a2kit.ldd.report(payload)`, and `a2kit.ldd.log(level, msg_or_instance, **fields)` (with shorthands `a2kit.ldd.debug`, `a2kit.ldd.info`, `a2kit.ldd.warning`, `a2kit.ldd.error`) as free functions. These functions SHALL NOT take a `ctx` parameter. Each function SHALL resolve the live transport context from the ambient `_LddState` set by the active `ldd_state_for_call` dispatch scope.

The `event` function SHALL accept either form:

1. **Kwargs form**: `event("name_string", key=value, ...)`. First positional is the event name; remaining kwargs are the payload.
2. **Typed form**: `event(instance)`. First positional is any class instance. Name defaults to `type(instance).__name__`; explicit `name=` overrides. Payload derived from the instance:
   - `dataclasses.asdict(instance)` if dataclass.
   - `instance.model_dump(mode="json")` if pydantic `BaseModel`.
   - `vars(instance)` fallback.
   - Any `Enum` value in the payload is replaced by `value.value`.

The library SHALL NOT add `event`, `report`, or `log` methods to the `a2kit.ToolContext` re-export. Existing `--no-events` / `--no-reports` CLI flags and the `A2KIT_LDD` env var SHALL continue to gate these primitives. The library SHALL NOT offer an explicit-`ctx` overload of any LDD primitive.

#### Scenario: Kwargs form delivers an event using ambient ctx

- **GIVEN** a tool body executing inside an active dispatch (`ldd_state_for_call` entered with the live `ctx`)
- **WHEN** the tool calls `await a2kit.ldd.event("api.fetched", count=30)`
- **THEN** the MCP client receives a `notifications/message` whose `data={"name": "api.fetched", "count": 30, "elapsed_ms": ...}`
- **AND** the tool body did not pass `ctx` to `event`

#### Scenario: Typed form delivers an event by class

- **GIVEN** `@dataclass class ApiFetched: count: int` and a tool body inside an active dispatch
- **WHEN** the tool calls `await a2kit.ldd.event(ApiFetched(count=30))`
- **THEN** the MCP client receives a `notifications/message` whose `data={"name": "ApiFetched", "count": 30, "elapsed_ms": ...}`

#### Scenario: Typed form with enum field

- **GIVEN** `class Verdict(Enum): OK = "ok"` and `@dataclass class TierEnded: verdict: Verdict`
- **WHEN** `await a2kit.ldd.event(TierEnded(verdict=Verdict.OK))` is called inside a dispatch
- **THEN** the delivered payload contains `"verdict": "ok"` (the enum value, not the enum instance)

#### Scenario: Explicit name override

- **WHEN** `await a2kit.ldd.event(ApiFetched(count=30), name="api.custom_name")` is called inside a dispatch
- **THEN** the delivered `data["name"]` is `"api.custom_name"`, not `"ApiFetched"`

#### Scenario: --no-events suppresses both forms

- **WHEN** the same tool runs with `--no-events`
- **THEN** neither form delivers an event, but neither call raises

#### Scenario: log primitive resolves ambient ctx

- **GIVEN** a tool body inside an active dispatch
- **WHEN** the tool calls `await a2kit.ldd.log("info", "msg", k=1)` (no `ctx` argument)
- **THEN** the rendered emission carries `"msg"` and `k=1` on the active transport (MCP `ctx.log` or CLI stderr line)

### Requirement: LDD wire-format invariants are owned by `a2kit.ldd`

Every event delivered via `a2kit.ldd.event(ctx, name, **kw)` SHALL carry an `elapsed_ms` integer in its structured payload, computed as `int((monotonic() - app_start_monotonic) * 1000)` where `app_start_monotonic` is captured at first emit (or at `App.on_startup` dispatch when the lifecycle ran). The CLI rendering SHALL prefix every line with `+s.mmm` relative time using zero-padded three-decimal milliseconds. The human-readable text portion of any LDD line SHALL be capped at 60 characters with `…` elision when truncated. The CLI stub `send_log_message` rendering and the MCP `notifications/message` payload (carrying the same `level`, `logger`, `data`) SHALL agree on the structured `data` field's contents key-for-key — transports may differ on framing only, never on the structured payload.

#### Scenario: elapsed_ms increases monotonically

- **WHEN** two `a2kit.ldd.event` calls happen 50 ms apart in the same process
- **THEN** the second emission's `elapsed_ms` is greater than the first's by approximately 50 (within OS scheduler tolerance)

#### Scenario: text capped at 60 chars

- **WHEN** a payload would render a 200-character text portion
- **THEN** the rendered text is exactly 60 characters and ends with `…`

#### Scenario: Same wire format on both transports

- **GIVEN** identical `a2kit.ldd.event(ctx, "X", n=42)` calls under MCP and CLI
- **THEN** the structured `data` payload (or its CLI key=value rendering) carries the same fields with the same values, except for transport-specific framing

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

The three dispatch sites SHALL pass `ctx` into `ldd_state_for_call`:

- MCP runtime (`_wrap_with_ldd_state` in `a2kit.packages.mcp.server`) passes the `fastmcp.Context` injected by FastMCP.
- CLI runtime (`_invoke_tool_in_process` in `a2kit.packages.cli.runtime`) passes the `StderrToolContext` instance.
- In-process test client (`TestClient.call_tool` in `a2kit.packages.testing.client`) passes the test stub.

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

### Requirement: LDD primitives raise when called outside a dispatch

If any of `a2kit.ldd.event`, `a2kit.ldd.report`, `a2kit.ldd.log`, `a2kit.ldd.debug`, `a2kit.ldd.info`, `a2kit.ldd.warning`, `a2kit.ldd.error`, or `EventRegistry.emit_typed` is invoked while `_LDD_STATE.get()` is `None` (i.e. no active `ldd_state_for_call` scope on the current `contextvars.Context`), the call SHALL raise `AmbientContextMissing` (a subclass of `RuntimeError`). The exception message SHALL name the invoked function and SHALL indicate that the primitive must be called from inside a tool body. The library SHALL NOT silently no-op and SHALL NOT synthesize a fallback context.

#### Scenario: Calling event outside a dispatch raises

- **GIVEN** a module-level coroutine that calls `await a2kit.ldd.event("x", k=1)` without first entering `ldd_state_for_call`
- **WHEN** the coroutine is awaited
- **THEN** `AmbientContextMissing` is raised
- **AND** the message contains `"a2kit.ldd.event"` and references the tool-body dispatch contract

#### Scenario: Calling log from a lifecycle hook raises

- **GIVEN** an `on_startup` hook that calls `await a2kit.ldd.info("starting")`
- **WHEN** the app starts up
- **THEN** `AmbientContextMissing` is raised

#### Scenario: emit_typed raises outside a dispatch

- **GIVEN** a coroutine that calls `await app.ldd.events.emit_typed(TierEnded(...))` outside any dispatch
- **WHEN** the coroutine is awaited
- **THEN** `AmbientContextMissing` is raised

