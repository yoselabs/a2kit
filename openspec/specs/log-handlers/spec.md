# log-handlers Specification

## Purpose
The refounding of `log-handlers` on stdlib logging (ADR 0027):
the operator/wire fan-out is re-expressed as stdlib `logging.Handler`s
attached to two distinct loggers — `a2kit` (author commentary: stderr,
OTel, live progress, MCP wire) and `a2kit.calls` (the non-streaming call
access-log, file handler only). Per-handler levels separate streamed from
file-only output; a failing handler is isolated (WARN-log + drop) and
never aborts the wire path or the producing tool.

## Requirements

### Requirement: Built-in handlers and their loggers
The framework SHALL ship built-in handlers expressed as stdlib
`logging.Handler`s, attached to two distinct loggers:

- On the `a2kit` logger (author commentary): stderr (pretty and JSON),
  OpenTelemetry, and live progress, plus the async MCP wire path.
- On the dedicated `a2kit.calls` logger (the call access-log): ONLY the
  call-log file handler (see the `call-log` capability). The record itself
  is produced by a transport-neutral dispatch stage, so it is identical
  across transports by construction; the handler only writes it.

The wire/stderr handlers SHALL NOT be attached to `a2kit.calls`, and
`a2kit.calls` SHALL set `propagate=False` — so call records cannot stream
to the agent or print to stdout. Re-expressing the operator sinks as
handlers SHALL preserve their existing observable behaviour.

#### Scenario: stderr pretty handler emits one line per emission
- **WHEN** `LogConfig.stderr_sink` is `"pretty"` and a tool emits a log record
- **THEN** one human-readable line per emission is written to stderr with the level shown

#### Scenario: OTel handler emits one span per *Ended payload
- **WHEN** the OTel SDK is present and a tool logs a `*Ended` payload instance
- **THEN** one span is created with the payload as attributes

### Requirement: Per-handler levels separate streamed from file-only
The streaming handlers (MCP wire, stderr) SHALL default to `INFO+` and the
call-log file handler SHALL default to `DEBUG+`, each configurable
independently (`WIRE_LEVEL`, `CALL_LOG_LEVEL`). Consequently a `debug`
record is captured durably (file) without streaming to the agent or
operator terminal. Severity (the level) therefore controls visibility for
the author's own logs; the dedicated-logger topology (above) controls it
for the always-on call records.

#### Scenario: a debug record is file-only by level
- **WHEN** a tool logs at `debug` with the wire/stderr at `INFO+` and the call-log at `DEBUG+`
- **THEN** the record is written to the call-log file but not to the wire or stderr

### Requirement: Operator sink failure isolation
A failing handler SHALL NOT abort the wire path, other handlers, or the
producing tool. Failures SHALL be logged at WARN under
`a2kit.log.sink_failed`.

#### Scenario: one handler raising does not abort others
- **WHEN** a handler raises during fan-out
- **THEN** the remaining handlers and the wire path still receive the record
- **AND** the failure is logged at WARN with the handler name and record name
