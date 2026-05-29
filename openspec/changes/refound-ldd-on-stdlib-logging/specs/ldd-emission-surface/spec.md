## ADDED Requirements

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

### Requirement: Single structured event primitive
The author surface SHALL expose `event(payload | "name", **fields)` as
the one structured-emission primitive, carrying the payload on the
stdlib record's `extra`. Typed payloads (pydantic / dataclass) SHALL be
dumped to a JSON-safe dict with enum values unwrapped. Loose
`info` / `debug` / `warning` / `error` shorthands SHALL route through the
same logger at the named level.

#### Scenario: typed event carries dumped payload
- **WHEN** `event(TierEnded(step="extract", dur_ms=300))` is called
- **THEN** one record is emitted carrying the dumped payload, enum fields unwrapped to their values

#### Scenario: loose shorthand routes at level
- **WHEN** `warning("cookies stale", host="x.com")` is called
- **THEN** one record at WARNING level is emitted with the fields attached

## REMOVED Requirements

### Requirement: report() typed-report primitive
**Reason**: zero callers (census 2026-05-27); validated payload types
even when disabled to serve test determinism (production API carrying a
test concern). The durable, typed shape it implied is delivered by
`ldd-call-journal` instead.
**Migration**: none required — no consumer imports `report` / `@reports`.
The journal record is the durable typed shape going forward.

### Requirement: EventRegistry typed-event registry
**Reason**: zero callers; the progress-callback path (`emit_typed` →
`report_progress`) is unused (a2web `report_progress` count: 0).
**Migration**: emit via `event(instance)` directly; no registration step.
