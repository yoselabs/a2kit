<!-- Archive note: this delta MODIFIES the canonical capability currently
named `ldd-operator-sinks`. At archive time the canonical capability is
RENAMED `ldd-operator-sinks` → `log-handlers` (no alias kept); these
modified requirements land under the new name. -->

## MODIFIED Requirements

### Requirement: Built-in operator sinks
The framework SHALL ship built-in operator sinks expressed as stdlib
`logging.Handler`s — stderr (pretty and JSON), OpenTelemetry, and live
progress — registerable via configuration without consumer code.
Re-expressing sinks as handlers SHALL preserve their existing observable
behaviour. The durable call journal is NOT in this set: it is a
transport-neutral dispatch-pipeline stage, not a logging handler (see the
`call-journal` capability) — a deliberate split so the captured record is
identical across transports by construction.

#### Scenario: stderr pretty handler emits one line per emission
- **WHEN** `LogConfig.stderr_sink` is `"pretty"` and a tool emits a log record
- **THEN** one human-readable line per emission is written to stderr with the level shown

#### Scenario: OTel handler emits one span per *Ended payload
- **WHEN** the OTel SDK is present and a tool logs a `*Ended` payload instance
- **THEN** one span is created with the payload as attributes

### Requirement: Operator sink failure isolation
A failing handler SHALL NOT abort the wire path, other handlers, or the
producing tool. Failures SHALL be logged at WARN under
`a2kit.log.sink_failed`.

#### Scenario: one handler raising does not abort others
- **WHEN** a handler raises during fan-out
- **THEN** the remaining handlers and the wire path still receive the record
- **AND** the failure is logged at WARN with the handler name and record name
