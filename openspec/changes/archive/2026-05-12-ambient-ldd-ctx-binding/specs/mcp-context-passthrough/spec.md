## MODIFIED Requirements

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

## ADDED Requirements

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
