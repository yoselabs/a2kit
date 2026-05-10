# health-probe Specification

## Purpose
TBD - created by archiving change a2web-feedback-round-2. Update Purpose after archive.
## Requirements
### Requirement: Built-in health tool

The system SHALL register a `_meta.health` tool when `App(..., health_tool=True)` is set.

#### Scenario: health tool returns ok with version

- **WHEN** a client invokes `_meta.health` on an app constructed with `health_tool=True` and no registered checks
- **THEN** the response is `{"status": "ok", "version": <pyproject version>, "checks": []}`

#### Scenario: health tool not registered by default

- **WHEN** an app is constructed without the `health_tool=` flag
- **THEN** `_meta.health` is not present in `app.tool_descriptors()`

### Requirement: User-registered readiness checks

The system SHALL allow registering health checks via `@app.health_check` that run when the health tool is invoked and aggregate into the response.

#### Scenario: passing check contributes ok entry

- **WHEN** `@app.health_check` is registered for a function returning `HealthResult.ok()` and the health tool runs
- **THEN** the response `checks` list contains an entry with that function's `__name__` and `status="ok"`

#### Scenario: failing check flips overall status to degraded

- **WHEN** any registered check returns `HealthResult.fail("sqlite missing")`
- **THEN** the response `status` is `"degraded"` and the corresponding `checks` entry has `reason="sqlite missing"`

### Requirement: Hidden from tool listings by default

The system SHALL exclude `_meta.health` from agent-facing `list_tools` output by default.

#### Scenario: list_tools omits the health tool

- **WHEN** an MCP client calls `list_tools` without an opt-in flag
- **THEN** the returned list does not include `_meta.health`

#### Scenario: include_meta surfaces the health tool

- **WHEN** an MCP client calls `list_tools` with the meta opt-in flag
- **THEN** the returned list includes `_meta.health` with its descriptor

### Requirement: CLI exit code reflects health

The system SHALL provide `<app> health` as a CLI subcommand whose exit code reflects the aggregated status.

#### Scenario: ok exits zero

- **WHEN** the user runs `<app> health` and all checks pass
- **THEN** the process exits with status `0`

#### Scenario: degraded exits non-zero

- **WHEN** the user runs `<app> health` and any check fails
- **THEN** the process exits with non-zero status and the failure reason appears on stderr

### Requirement: `_meta.*` namespace reserved

The system SHALL reject user tools whose name starts with `_meta.` at decoration or registration time.

#### Scenario: user tool with reserved name raises

- **WHEN** a user decorates a tool `@a2kit.read(name="_meta.custom")`
- **THEN** a `ValueError` is raised at decoration time, naming the reserved namespace

