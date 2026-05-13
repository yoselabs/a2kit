# health-probe Specification

## Purpose
TBD - created by archiving change a2web-feedback-round-2. Update Purpose after archive.
## Requirements
### Requirement: Built-in health tool

The system SHALL register a `_meta.health` tool when either (a) `App(..., health_tool=True)` is set explicitly, or (b) at least one `@app.health_check` is registered. The first `@app.health_check` call SHALL auto-install the `_meta.health` synthetic router idempotently — subsequent calls SHALL register additional checks without re-installing. The `health_tool=True` constructor flag SHALL remain accepted (no-op when checks are also registered) for backward compatibility and for apps that want the tool present with zero checks.

#### Scenario: health tool returns ok with version

- **WHEN** a client invokes `_meta.health` on an app constructed with `health_tool=True` and no registered checks
- **THEN** the response is `{"status": "ok", "version": <pyproject version>, "checks": []}`

#### Scenario: health tool not registered when neither flag nor checks present

- **WHEN** an app is constructed without `health_tool=` AND no `@app.health_check` is registered
- **THEN** `_meta.health` is not present in `app.tools()`

#### Scenario: `@app.health_check` auto-enables the health tool

- **GIVEN** an app constructed without the `health_tool=` flag
- **WHEN** `@app.health_check` is applied to a function
- **THEN** the `_meta.health` synthetic router is installed on the app
- **AND** the check is registered into the health registry
- **AND** subsequent `@app.health_check` calls register additional checks without re-installing the router

#### Scenario: `health_tool=True` + `@app.health_check` is idempotent

- **GIVEN** an app constructed with `health_tool=True`
- **WHEN** `@app.health_check` is applied to a function
- **THEN** no second `_meta.health` router is installed
- **AND** the check appears in the health registry

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

The auto-generated `<app> health` CLI subcommand SHALL exit with a non-zero status code when the aggregated health status is anything other than `"ok"`. The subcommand SHALL run without importing any pytest-dependent modules — specifically, the health command SHALL NOT import `a2kit.packages.testing` or any submodule that requires `pytest` at runtime. The probe SHALL execute by calling `a2kit.packages.health.run_checks(app)` directly under the App's `lifespan_cm()`, rendering the result as JSON to stdout.

#### Scenario: ok status exits zero

- **WHEN** all registered checks return `HealthResult.ok()` and the user runs `<app> health`
- **THEN** the command prints the aggregated JSON to stdout
- **AND** exits with code `0`

#### Scenario: degraded status exits non-zero

- **WHEN** any registered check returns `HealthResult.fail(...)` and the user runs `<app> health`
- **THEN** the command prints the aggregated JSON to stdout
- **AND** exits with a non-zero code

#### Scenario: `<app> health` works without pytest installed

- **GIVEN** a fresh virtual environment with the app's runtime dependencies installed and pytest NOT installed
- **WHEN** the user runs `<app> health`
- **THEN** the command runs to completion (no `ModuleNotFoundError: pytest`)
- **AND** prints the aggregated health JSON
- **AND** exits with the appropriate code

#### Scenario: health command does not import testing package

- **WHEN** the `<app> health` command path is exercised
- **THEN** `sys.modules` does not contain `a2kit.packages.testing` (nor any submodule thereof) at the moment `run_checks` is invoked

### Requirement: `_meta.*` namespace reserved

The system SHALL reject user tools whose name starts with `_meta.` at decoration or registration time.

#### Scenario: user tool with reserved name raises

- **WHEN** a user decorates a tool `@a2kit.read(name="_meta.custom")`
- **THEN** a `ValueError` is raised at decoration time, naming the reserved namespace

