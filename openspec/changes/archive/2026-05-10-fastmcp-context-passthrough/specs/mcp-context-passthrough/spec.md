## ADDED Requirements

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

The library SHALL expose `a2kit.ldd.event(ctx, name, **kw)` and `a2kit.ldd.report(ctx, payload)` as free functions that accept any `fastmcp.Context`-shaped object. The library SHALL NOT add `event` or `report` methods to the `a2kit.ToolContext` re-export. Existing `--no-events` / `--no-reports` CLI flags and the `A2KIT_LDD` env var SHALL continue to gate these primitives.

#### Scenario: Event delivers in MCP
- **WHEN** a tool calls `await event(ctx, "api.fetched", count=30)` under `<app> serve`
- **THEN** the client receives an MCP notification carrying `name="api.fetched"` and `count=30`

#### Scenario: Event delivers in CLI
- **WHEN** the same tool runs via CLI
- **THEN** stderr contains a line `[ +s.mmm event   ] api.fetched count=30`

#### Scenario: --no-events suppresses both transports
- **WHEN** the same tool runs with `--no-events`
- **THEN** no event is delivered on either transport, but the call still type-checks (no `AttributeError`)

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

The `App` class SHALL expose `app.ldd.events: EventRegistry`. The registry SHALL provide `register(model: type[BaseModel], *, progress: Callable[[BaseModel], float] | None = None) -> None` and `async emit_typed(ctx, event: BaseModel) -> None`. `emit_typed` SHALL serialize `event` via `event.model_dump(mode="json")`, call the underlying `a2kit.ldd.event(ctx, event.__class__.__name__, **dumped)`, and — if a `progress` callback is registered for `event.__class__` — additionally call `ctx.report_progress(progress(event), 1.0)`. Re-registration is last-write-wins. One progress callback per event class; consumers compose at the callback level if they need composite progress.

#### Scenario: Register and emit typed event

- **GIVEN** `app.ldd.events.register(TierEnded, progress=lambda e: 0.5)` registered
- **WHEN** `await app.ldd.events.emit_typed(ctx, TierEnded(step="raw", verdict="ok"))` is called
- **THEN** `a2kit.ldd.event(ctx, "TierEnded", step="raw", verdict="ok")` runs first
- **AND** `ctx.report_progress(0.5, 1.0)` runs immediately after

#### Scenario: Unregistered model emits without progress

- **GIVEN** no registration for `OtherEvent`
- **WHEN** `await app.ldd.events.emit_typed(ctx, OtherEvent(...))` is called
- **THEN** the underlying `event` is invoked but no progress call is made

#### Scenario: Re-registration is last-write-wins

- **WHEN** `register(TierEnded, progress=fn_a)` is followed by `register(TierEnded, progress=fn_b)`
- **THEN** subsequent `emit_typed` for `TierEnded` uses `fn_b`

#### Scenario: model_dump uses JSON mode

- **GIVEN** an event model whose fields include a `datetime` value
- **WHEN** `emit_typed` is called
- **THEN** the underlying `event` call receives the datetime serialized as an ISO-8601 string (the `model_dump(mode="json")` coercion)
