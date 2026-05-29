## MODIFIED Requirements

### Requirement: Built-in operator sinks
The framework SHALL ship built-in operator sinks expressed as stdlib
`logging.Handler`s — stderr (pretty and JSON), OpenTelemetry, live
progress, and the durable call journal — registerable via configuration
without consumer code. Re-expressing sinks as handlers SHALL preserve
their existing observable behaviour.

#### Scenario: stderr pretty handler emits one line per emission
- **WHEN** `LddConfig.stderr_sink` is `"pretty"` and a tool emits an event
- **THEN** one human-readable line per emission is written to stderr with the level shown

#### Scenario: OTel handler emits one span per *Ended event
- **WHEN** the OTel SDK is present and a tool emits a `*Ended` event
- **THEN** one span is created with the event payload as attributes

#### Scenario: journal handler persists a record
- **WHEN** `LddConfig.journal_sink` is `"on"` and a tool dispatches
- **THEN** one durable journal record is written for the call

### Requirement: Operator sink failure isolation
A failing handler SHALL NOT abort the wire path, other handlers, or the
producing tool. Failures SHALL be logged at WARN under
`a2kit.ldd.sink_failed`.

#### Scenario: one handler raising does not abort others
- **WHEN** a handler raises during fan-out
- **THEN** the remaining handlers and the wire path still receive the record
- **AND** the failure is logged at WARN with the handler name and record name
