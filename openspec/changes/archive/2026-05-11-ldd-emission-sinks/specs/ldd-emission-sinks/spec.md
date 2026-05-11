## ADDED Requirements

### Requirement: `LddEmission` payload and `LddSink` protocol

`a2kit.ldd` SHALL define:

- `LddEmission` — a frozen dataclass with fields `kind: Literal["event", "report"]`,
  `name: str`, `payload: dict[str, Any]`, `elapsed_ms: int`, `tool_name: str | None`,
  `ctx: Any`.
- `LddSink` — a Protocol with a single async `__call__(self, emission: LddEmission, /) -> None`.

#### Scenario: LddEmission is immutable
- **WHEN** an `LddEmission` is constructed and a caller attempts to mutate a field
- **THEN** a `FrozenInstanceError` is raised

#### Scenario: LddSink is satisfied by an async callable
- **WHEN** an async function with the signature `async def f(e: LddEmission) -> None` exists
- **THEN** it can be passed wherever `LddSink` is expected (structural typing)

### Requirement: `app.ldd.add_sink` / `remove_sink` API

The `_AppLdd` namespace (mounted on `App` as `app.ldd`) SHALL expose:

- `add_sink(sink: LddSink) -> None` — appends to the App's sink list
- `remove_sink(sink: LddSink) -> None` — removes a previously added sink
- `sinks` (property) — returns an immutable tuple snapshot of currently registered sinks

#### Scenario: Add and remove round-trip
- **WHEN** `app.ldd.add_sink(s)` is called and then `app.ldd.remove_sink(s)` is called
- **THEN** `app.ldd.sinks` is empty

#### Scenario: Sinks property is immutable
- **WHEN** a caller accesses `app.ldd.sinks` and attempts to append to the result
- **THEN** the attempt raises (it's a tuple, not a list)

### Requirement: Sink fan-out after wire emit

The `a2kit.ldd.event` and `a2kit.ldd.report` free functions SHALL,
after their wire emit completes, build a single `LddEmission` instance and
await each registered sink in registration order. Sink exceptions
SHALL be caught and logged via stdlib `logger.exception(...)`. The
wire emit MUST happen regardless of sink registration; sink fan-out
MUST happen regardless of wire-emit outcome.

#### Scenario: Sink sees event after wire emit
- **WHEN** a tool calls `event(ctx, "x", k=1)` and a sink is registered
- **THEN** the wire receives the emission AND the sink is called with an `LddEmission` whose `kind="event"`, `name="x"`, `payload={"k": 1}`

#### Scenario: Bad sink does not break dispatch
- **WHEN** a registered sink raises `RuntimeError`
- **THEN** the tool dispatch completes normally, the wire still received the emission, and a stdlib log records the failure

#### Scenario: Sinks fan out in registration order
- **WHEN** sinks A, B, C are registered in order
- **THEN** for each emission, A is awaited before B before C

#### Scenario: Kill-switch gates both wire and sinks symmetrically
- **WHEN** the LDD events kill-switch is engaged (events disabled)
- **THEN** neither the wire emit nor the sink fan-out runs

### Requirement: Dispatch sites propagate App sinks

Both the CLI runtime and MCP middleware dispatch sites SHALL pass `app.ldd.sinks` into the `ldd_state_for_call(sinks=…)` context manager, and the `_LddState` SHALL carry the tuple for the lifetime of the call.

#### Scenario: CLI dispatch propagates sinks
- **WHEN** a tool is invoked via the CLI runtime and the App has a sink registered
- **THEN** the sink is called during the tool body's `event()` calls

#### Scenario: MCP dispatch propagates sinks
- **WHEN** a tool is invoked via the MCP middleware and the App has a sink registered
- **THEN** the sink is called during the tool body's `event()` calls

#### Scenario: State resets after dispatch
- **WHEN** a tool completes (success or exception) and a follow-up call to `event(...)` is made outside a dispatch
- **THEN** no sinks are called (the per-call state has been reset)
