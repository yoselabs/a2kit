## MODIFIED Requirements

### Requirement: OTel sink is a framework-default opt-in with drain-on-missing semantics

The `otel_sink` SHALL ship in-framework under `a2kit.packages.ldd.sinks` and be auto-registered at app boot when `LddConfig.otel_sink` is `"auto"` (default) AND both the `opentelemetry` SDK is importable AND at least one `OTEL_EXPORTER_*` env var is set. Consumers SHALL NOT need to hand-port the sink into their own repo. The sink SHALL drain every emission when the SDK is missing (no exception, no output, no backlog) so that turning it `"on"` explicitly is always safe.

This requirement subsumes the prior "consumer hand-wires OTel" pattern that a2web carried in `src/a2web/events/sinks.py`. Once this requirement lands, the consumer-side file becomes redundant and is retired in a follow-up change on the consumer repo.

#### Scenario: Auto mode registers when both conditions hold

- **GIVEN** `LddConfig.otel_sink="auto"`, `opentelemetry` importable, `OTEL_EXPORTER_OTLP_ENDPOINT` set
- **WHEN** the app boots
- **THEN** `otel_sink` is registered as a built-in operator sink

#### Scenario: Auto mode skips registration without exporter env

- **GIVEN** `LddConfig.otel_sink="auto"`, `opentelemetry` importable, no `OTEL_EXPORTER_*` env
- **WHEN** the app boots
- **THEN** `otel_sink` is NOT registered

#### Scenario: Explicit `on` registers even without SDK

- **GIVEN** `LddConfig.otel_sink="on"` and `opentelemetry` not importable
- **WHEN** the app boots
- **THEN** `otel_sink` IS registered
- **AND** every emission fed to it is silently drained (no exception, no output)

#### Scenario: One span per `*Ended` event when SDK present

- **GIVEN** OTel SDK installed and exporter configured
- **WHEN** the framework emits a `CellEnded` event with `step="x"` and `dur_ms=42`
- **THEN** exactly one OTel span is started, attributed (`a2kit.step="x"`, `a2kit.dur_ms=42`), and ended within the sink call
