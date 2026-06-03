# ldd-operator-sinks Specification

## Purpose
First-class operator/wire fan-out for LDD emissions plus four
built-in operator sinks (stderr_pretty, stderr_json, otel, live).
Operator sinks run in parallel with per-sink failure isolation
(WARN-log + drop). A single level threshold gates both channels.

## Requirements

### Requirement: Emission fan-out runs in parallel across operator and wire channels

After the level threshold accepts an emission, the LDD primitive SHALL dispatch the emission to the wire sink (FastMCP `ctx.log` when present) AND to every registered operator sink. Operator-channel and wire-channel dispatch SHALL run concurrently via `asyncio.gather(..., return_exceptions=True)`. The producer SHALL NOT await sink completion in a way that lets one slow sink throttle the producer rate; fan-out runs in a fire-and-forget task per emission.

#### Scenario: Slow operator sink does not block the wire sink

- **GIVEN** an operator sink that awaits `asyncio.sleep(5)` before returning
- **WHEN** a tool emits an event
- **THEN** the wire sink (`ctx.log`) receives the emission within milliseconds
- **AND** the operator sink eventually receives the same emission

#### Scenario: Failing operator sink does not abort others

- **GIVEN** operator sinks A, B, C registered in that order, where B always raises `RuntimeError`
- **WHEN** a tool emits an event
- **THEN** A and C both receive the emission
- **AND** the exception from B is logged at WARN on the "a2kit.log.sink_failed" logger with handler name + record name
- **AND** no exception propagates to the producer

#### Scenario: Failing wire sink does not abort operator fan-out

- **GIVEN** the wire `ctx.log` raises (e.g. closed transport)
- **WHEN** a tool emits an event
- **THEN** every registered operator sink receives the emission
- **AND** the wire failure is logged at WARN

### Requirement: Four built-in operator sinks ship under `a2kit.packages.log.handlers`

The package SHALL expose `stderr_pretty_sink`, `stderr_json_sink`, `otel_sink`, and `live_sink` as importable async callables. Each SHALL be a pure async consumer that drains every emission even when its backend is unavailable.

#### Scenario: Sinks are importable from the documented surface

- **WHEN** code does `from a2kit.packages.log.handlers import stderr_pretty_sink, stderr_json_sink, otel_sink, live_sink`
- **THEN** all four imports succeed

#### Scenario: stderr_pretty writes one line per emission

- **WHEN** a tool emits an event at level `info` with payload `{"k": 1}`
- **THEN** `stderr_pretty_sink` writes exactly one human-readable line to stderr
- **AND** the line includes the level token and the event name

#### Scenario: stderr_json writes one valid JSON record per line

- **WHEN** a tool emits 3 events
- **THEN** `stderr_json_sink` writes exactly 3 lines to stderr
- **AND** each line round-trips through `json.loads(...)` to a dict

### Requirement: `otel_sink` drains every emission when the SDK is missing

When `opentelemetry` is not importable, `otel_sink(emission)` SHALL accept every call without raising and without producing any output. When the SDK is present, the sink SHALL start one span per `*Ended` event, set attributes (`step`, `verdict` when present, `dur_ms` / `t_ms` when numeric), and end the span synchronously within the call. `*Started` and `*Heartbeat` events SHALL be consumed silently.

#### Scenario: SDK absent — sink is a silent drain

- **GIVEN** `opentelemetry` raises `ImportError` on import
- **WHEN** any emission is fed to `otel_sink`
- **THEN** no exception is raised
- **AND** no output is produced

#### Scenario: SDK present — one span per `*Ended`

- **GIVEN** OTel SDK installed and `OTEL_EXPORTER_*` configured
- **WHEN** events `CellStarted`, `CellEnded` (with `step="x"`, `dur_ms=42`) are emitted
- **THEN** exactly one span named `a2web.x` (or `a2kit.x` — namespace TBD in implementation) is created, with `a2kit.dur_ms=42` attribute, and ended

### Requirement: `live_sink` is concurrency-safe and emits a configurable heartbeat

`live_sink` SHALL serialise its stdout writes via an `asyncio.Lock` so that concurrent emissions never produce character-level interleave. It SHALL emit a heartbeat line every `live_heartbeat_seconds` (default 30) while at least one cell is in flight, showing `running: K, done: N/total` where `total` is supplied via initial setup or derived from emission counts. The set of event names triggering line output SHALL be controlled by `event_prefixes: tuple[str, ...]` (default `("",)` — every `*Started`/`*Ended` pair).

#### Scenario: Concurrent emissions produce atomic lines

- **GIVEN** `live_sink` registered with no filter
- **WHEN** 100 concurrent tasks each emit one `*Started` event
- **THEN** stdout contains 100 distinct, atomic lines
- **AND** no two lines share characters from different emissions

#### Scenario: Heartbeat fires while work is in flight

- **GIVEN** `live_heartbeat_seconds=0.1` and one emitted `*Started` not yet matched by `*Ended`
- **WHEN** 200ms elapse
- **THEN** at least one heartbeat line appears
- **AND** the heartbeat line shows `running >= 1`

### Requirement: Config registers built-in sinks before user-added sinks

`LddConfig` SHALL carry fields `stderr_sink: Literal["none", "pretty", "json"]` (default `"none"`), `otel_sink: Literal["auto", "on", "off"]` (default `"auto"`), `live_sink: Literal["off", "on"]` (default `"off"`), `live_heartbeat_seconds: float` (default `30.0`), and `live_event_prefixes: tuple[str, ...]` (default `("",)`). Env mapping SHALL follow the existing `A2KIT_LDD__` prefix. At app boot, every enabled built-in sink SHALL be registered BEFORE any user-added sinks. Registration order is the dispatch order.

#### Scenario: Default config registers no built-in stderr or live sink

- **GIVEN** no `A2KIT_LDD__*` env overrides
- **WHEN** the app boots
- **THEN** neither `stderr_pretty_sink` nor `stderr_json_sink` nor `live_sink` is registered
- **AND** `otel_sink` is registered iff the auto-heuristic matches

#### Scenario: `LDD_OTEL_SINK=auto` requires both SDK and exporter env

- **GIVEN** `LDD_OTEL_SINK=auto`
- **WHEN** OTel SDK is importable AND any `OTEL_EXPORTER_*` env var is set
- **THEN** `otel_sink` is registered
- **AND** when EITHER condition is false, `otel_sink` is NOT registered

#### Scenario: `LDD_OTEL_SINK=on` overrides the heuristic

- **GIVEN** `LDD_OTEL_SINK=on` and OTel SDK missing
- **WHEN** the app boots
- **THEN** `otel_sink` IS registered (its drain-on-missing behaviour makes this safe)
