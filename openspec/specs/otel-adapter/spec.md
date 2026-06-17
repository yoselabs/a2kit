# otel-adapter Specification

## Purpose
TBD - created by archiving change v1-cleanup-debt. Update Purpose after archive.
## Requirements
### Requirement: OTel adapter is an opt-in plugin package

`a2kit.packages.otel` SHALL be an opt-in plugin package. OpenTelemetry
dependencies SHALL NOT appear in `[project] dependencies`; they SHALL be
declared under `[project.optional-dependencies] otel = [...]`.

#### Scenario: Optional install path
- **WHEN** a user installs `pip install 'a2kit[otel]'`
- **THEN** `opentelemetry-api` and `opentelemetry-sdk` are pulled as
  required deps for that install

#### Scenario: Default install excludes OTel
- **WHEN** a user runs `pip install a2kit` without the `[otel]` extra
- **THEN** `opentelemetry-api` is not in the install closure

#### Scenario: Lazy import — package load does not require OTel
- **WHEN** a user runs `import a2kit.packages.otel`
- **THEN** the import succeeds even when `opentelemetry-api` is not installed;
  no `ImportError` until the user calls `install(...)`

#### Scenario: Informative error on missing deps
- **WHEN** a user calls `a2kit.packages.otel.install(server)` without the
  `[otel]` extras installed
- **THEN** an `ImportError` is raised with a message pointing at
  `pip install 'a2kit[otel]'`

### Requirement: `install(server)` adds an OTel Middleware

`a2kit.packages.otel.install(server, ...)` SHALL register a FastMCP `Middleware` subclass that wraps every `on_call_tool` invocation in an OTel span. Signature: `install(server, *, tracer_name="a2kit", meter_name="a2kit", metrics=False)`.

#### Scenario: Span attributes from A2KitMeta

- **WHEN** a tool registered with `@a2kit.read(name="get_task", tags={"read"})` is invoked through the MCP server with the OTel middleware installed
- **THEN** the active span has these attributes, keyed by the literal OTel attribute-name strings the middleware emits:
  - the attribute named "a2kit.tool_name" with value `"get_task"`
  - the attribute named "a2kit.verb" with value `"read"`
  - the attribute named "a2kit.tags" with value `"read"` (sorted, comma-joined)
  - the attribute named "a2kit.router" with value the registered Router slug

#### Scenario: Span name shape

- **WHEN** a tool named `list_tasks` is invoked
- **THEN** the recorded span's name is `mcp.tool.list_tasks`

#### Scenario: Exception recording

- **WHEN** the wrapped tool raises an exception
- **THEN** the span's status is set to ERROR, `record_exception(exc)` is
  called, and the exception bubbles unchanged to the caller

#### Scenario: Metrics off by default

- **WHEN** a user calls `install(server)` without `metrics=True`
- **THEN** no OTel meter is created; only spans are emitted

#### Scenario: Metrics on demand

- **WHEN** a user calls `install(server, metrics=True)`
- **THEN** a counter whose OTel instrument name is the literal string "a2kit.tool.calls" increments per tool call with attribute set `{tool, verb, status}` where `status ∈ {"ok", "error"}`

### Requirement: Core stays OTel-free

`a2kit` core (top-level files in `src/a2kit/`) SHALL NOT import any `opentelemetry-*` symbol — direct or transitive. The same prohibition applies to every plugin package under `a2kit.packages.*` other than `otel`.

#### Scenario: No OTel import outside the otel package
- **WHEN** `grep -rE "^(from|import) opentelemetry" src/a2kit/` is run, excluding `src/a2kit/packages/otel/`
- **THEN** the result is empty


### Requirement: Built-in OTel log sink with drain-on-missing-SDK invariant

The framework SHALL ship a built-in `otel_sink` operator sink in `a2kit.packages.log.handlers.OtelHandler` that emits one OTel span per `*Ended` log emission. `*Started` events and emissions whose name does not end in `Ended` SHALL be silently consumed. When the `opentelemetry` SDK is not importable (or no tracer provider is configured), the sink SHALL drain every emission without raising — preserving the operator-fan-out failure-isolation contract.

The sink is registered at App boot when `A2kitConfig.log.otel_sink` is `"on"`, or `"auto"` (default) AND the SDK is importable AND at least one `OTEL_EXPORTER_*` env var is set.

#### Scenario: otel_sink drains when SDK is missing

- **GIVEN** the `opentelemetry` package is not importable
- **WHEN** `otel_sink(emission)` is called for any emission
- **THEN** the call returns normally and no span is emitted

#### Scenario: Span emitted per *Ended event

- **GIVEN** the SDK is configured and a tracer is available
- **WHEN** an emission with `name="CellEnded"` reaches the sink
- **THEN** one span named `CellEnded` is started and ended within the call

#### Scenario: auto heuristic predicates both conditions

- **GIVEN** `A2kitConfig.log.otel_sink == "auto"`
- **WHEN** `should_register_otel_sink("auto")` runs
- **THEN** it returns True iff `opentelemetry` is importable AND at least one `OTEL_EXPORTER_*` env var is set
