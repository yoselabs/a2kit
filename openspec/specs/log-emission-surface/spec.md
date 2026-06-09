# log-emission-surface Specification

## Purpose
The author-facing emission surface, refounded on stdlib `logging`
(ADR 0027): levels are logging levels, sinks are handlers, the wire line
is a formatter, and per-call context is injected by a filter — with no
third-party logging dependency on the emission path. The MCP wire streams
emissions live, mid-call. Level methods (`info`/`debug`/`warning`/`error`)
accept a string message OR a typed instance as the structured payload;
the removed `report()` primitive and `EventRegistry` (both zero-caller)
are superseded by the `call-log` capability and direct instance logging.

## Requirements

### Requirement: Emission surface built on stdlib logging
The emission surface SHALL be implemented on Python's stdlib `logging`:
levels are logging levels, sinks are `logging.Handler`s, the condensed
wire line is a `logging.Formatter`, and per-call context (`call_id`,
`tool_name`, `elapsed_ms`) is injected by a `logging.Filter` reading the
request-scope contextvar. The framework SHALL NOT add a third-party
logging dependency to the emission path.

#### Scenario: emission adds no import beyond stdlib logging
- **WHEN** `import a2kit` runs
- **THEN** the emission path imports only stdlib `logging` (no structlog, no third-party logging lib)

#### Scenario: per-call context is injected onto every record
- **WHEN** a tool emits during dispatch
- **THEN** the record carries `call_id`, `tool_name`, and `elapsed_ms` from the active request scope

### Requirement: The MCP wire streams emissions live, mid-call
The emission primitives SHALL remain asynchronous and the MCP wire
emission SHALL be an inline `await` on the connected context's log call,
delivered before the tool returns. The wire path SHALL NOT be deferred
behind a synchronous handler, a buffer, or an end-of-call flush, so a
long-running call surfaces its emissions as they happen.

#### Scenario: emission reaches the wire before the tool returns
- **WHEN** a tool emits an event partway through a long-running body
- **THEN** the wire log notification is delivered at emit time, before the tool's return value is produced

### Requirement: Level methods accept a message OR a typed instance
The author surface SHALL expose `info` / `debug` / `warning` / `error`
as the emission methods, each accepting EITHER a string message OR a
typed instance (pydantic / dataclass) as the first positional, plus
`**fields`. There is NO generic loose `log(...)` verb on the public
surface (severity is chosen by which level method is called). A typed instance is the structured payload:
it is dumped to a JSON-safe dict (enum values unwrapped) and carried on
the stdlib record's `extra`. There is NO separate `event()` verb — the
instance-as-payload shape (a2web's 28-site idiom) survives under the
level methods, preserving construction-time type-checking and IDE
autocomplete.

#### Scenario: a level method accepts a typed instance
- **WHEN** `info(TierEnded(step="extract", dur_ms=300))` is called
- **THEN** one INFO record is emitted carrying the dumped instance, enum fields unwrapped to their values

#### Scenario: a level method accepts a message + fields
- **WHEN** `warning("cookies stale", host="x.com")` is called
- **THEN** one WARNING record is emitted with the fields attached

#### Scenario: no event() verb exists
- **WHEN** code attempts to import or call `event` from the emission surface
- **THEN** it fails — the structured shape lives under the level methods, not a dedicated verb
