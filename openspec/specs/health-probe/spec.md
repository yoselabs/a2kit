# health-probe Specification

## Purpose
TBD - created by archiving change a2web-feedback-round-2. Update Purpose after archive.
## Requirements
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

### Requirement: `_meta.health` SHALL install exclusively via `@app.health_check`

The synthetic `_meta.health` tool SHALL install as a side effect of
the first `@app.health_check` registration on an `App`. The install
SHALL be idempotent — subsequent `@app.health_check` calls SHALL
register additional checks without re-installing the synthetic
router. Apps with zero registered checks SHALL NOT have
`_meta.health` exposed; the synthetic router exists only when at
least one check exists.

The previous `App(health_tool=True)` install path SHALL NOT exist.
Constructing `App(...)` with that keyword SHALL raise `TypeError`
with a message naming `@app.health_check` as the replacement.

#### Scenario: First @app.health_check installs the synthetic tool

- **GIVEN** `app = a2kit.App("a")` (no checks yet)
- **WHEN** `@app.health_check` is applied to a function for the first time
- **THEN** `_meta.health` becomes invocable on the app's MCP/CLI surface
- **AND** `app.tools()` includes the synthetic tool descriptor

#### Scenario: Repeated @app.health_check is idempotent

- **GIVEN** an app with two `@app.health_check`-decorated functions registered
- **WHEN** the app is inspected
- **THEN** exactly one `_meta.health` tool descriptor exists
- **AND** both checks fire when `_meta.health` is invoked

#### Scenario: `health_tool=True` raises with migration hint

- **GIVEN** code `a2kit.App("a", health_tool=True)`
- **WHEN** the constructor evaluates
- **THEN** `TypeError` is raised
- **AND** the message contains `"health_check"`

#### Scenario: No checks → no synthetic tool

- **GIVEN** `app = a2kit.App("a")` with no `@app.health_check` registrations
- **WHEN** the app is inspected
- **THEN** `_meta.health` is NOT present in `app.tools()`
- **AND** invoking `_meta.health` over MCP returns the standard "unknown tool" error

### Requirement: Health-check kwargs route through the DI resolver

The system SHALL resolve `@app.health_check`-registered function
kwargs through `Container.resolve_params`, the same DI path used
by tool dispatch. Each resolved kwarg SHALL follow the standard
lifecycle protocol: on first resolution, the framework SHALL enter
the resource via `__aenter__` (when the resource exposes the CM
protocol) and record cleanup on the appropriate scope's stack
(root for SINGLETON, child for SCOPED).

`__aexit__` SHALL fire when the owning scope unwinds:
- SINGLETON resources exit at **app shutdown** (root cleanup stack
  drained via `Container.aclose()`).
- SCOPED resources exit at end of dispatch (child cleanup stack
  drained).

Health checks SHALL NOT trigger re-entry of an already-resolved
SINGLETON. The first resolution anywhere in the app (a tool
dispatch, a prior health check, or any other call site) is the
sole entry point; subsequent health checks reusing the singleton
hit the cache.

Consumers SHALL NOT call internal "ensure ready" methods (e.g.
`await sqlite._ensure()`) on resources passed as health-check
kwargs. By the time the check body runs, the resource has been
entered via the DI resolver's lifecycle protocol — either by this
check (if it's the first reference to the type) or by an earlier
call site.

#### Scenario: first health probe enters a SINGLETON resource

- **GIVEN** `class SpyResource` with `entered`/`exited` counters,
  registered as a singleton via `app.singleton(SpyResource, ...)`,
  with no other call site having referenced it yet
- **AND** `@app.health_check async def probe(spy: SpyResource):
  return a2kit.HealthResult.ok()`
- **WHEN** the health tool / `<app> health` CLI invokes the check
  for the first time in the app's lifetime
- **THEN** `spy.entered == 1` at the moment the check body runs
- **AND** `spy.exited == 0` (singleton stays entered for the
  app's lifetime)

#### Scenario: second health probe reuses the cached SINGLETON

- **GIVEN** the same setup, after one prior health probe has run
- **WHEN** the health tool invokes the check a second time
- **THEN** `spy.entered == 1` (still — no re-entry)
- **AND** the check body receives the same instance as the first
  call

#### Scenario: SINGLETON exits at app shutdown, not per probe

- **GIVEN** a singleton entered by a prior health check
- **WHEN** the app's `lifespan_cm` exits (e.g. CLI subcommand
  completes, MCP transport shuts down)
- **THEN** `spy.exited == 1`

#### Scenario: failure path does not affect singleton lifecycle

- **GIVEN** a singleton `SpyResource` already entered
- **WHEN** a check returns `HealthResult.fail("simulated")` or
  raises
- **THEN** `spy.entered` and `spy.exited` are unchanged by this
  probe; the singleton's lifecycle is independent of any
  individual check's outcome
- **AND** the health-probe surface reports a degraded status
  (existing behaviour, restated for context)

#### Scenario: shared singleton across checks enters once

- **GIVEN** two registered checks `probe_a(spy: SpyResource)` and
  `probe_b(spy: SpyResource)` sharing the same singleton
- **WHEN** the health-probe runs both in a single invocation
- **THEN** `spy.entered == 1` (singleton resolution does not
  re-enter across checks)
- **AND** both checks receive the same instance

