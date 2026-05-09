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

`a2kit.packages.otel.install(server, *, tracer_name="a2kit", meter_name="a2kit", metrics=False)`
SHALL register a FastMCP `Middleware` subclass that wraps every
`on_call_tool` invocation in an OTel span.

#### Scenario: Span attributes from A2KitMeta
- **WHEN** a tool registered with `@a2kit.read(name="get_task", tags={"read"})` is invoked through the MCP server with the OTel middleware installed
- **THEN** the active span has attributes:
  - `a2kit.tool_name = "get_task"`
  - `a2kit.verb = "read"`
  - `a2kit.tags = "read"` (sorted, comma-joined)
  - `a2kit.router = "<router-slug>"` (the registered Router slug)

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
- **THEN** a counter named `a2kit.tool.calls` increments per tool call with
  attribute set `{tool, verb, status}` where `status ∈ {"ok", "error"}`

### Requirement: Core stays OTel-free

`a2kit` core (top-level files in `src/a2kit/`) and every plugin package
under `a2kit.packages.*` other than `otel` SHALL NOT import any
`opentelemetry-*` symbol — direct or transitive.

#### Scenario: No OTel import outside the otel package
- **WHEN** `grep -rE "^(from|import) opentelemetry" src/a2kit/` is run, excluding `src/a2kit/packages/otel/`
- **THEN** the result is empty

