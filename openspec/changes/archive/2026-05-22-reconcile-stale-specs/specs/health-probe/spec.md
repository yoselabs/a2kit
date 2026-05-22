## MODIFIED Requirements

### Requirement: CLI exit code reflects health

The auto-generated `<app> health` CLI subcommand SHALL exit with a non-zero status code when the aggregated health status is anything other than `"ok"`. The subcommand SHALL run without importing any pytest-dependent modules — specifically, the health command SHALL NOT import `a2kit.packages.testing` or any submodule that requires `pytest` at runtime. The probe SHALL execute by calling `a2kit.packages.health.run_checks(registry, resolver, ...)` — `run_checks` takes a `HealthRegistry` and a `Resolver`, not an `App`; it is invoked within the App's entered lifecycle so DI resolution and resource entry work — rendering the result as JSON to stdout.

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

#### Scenario: run_checks takes a Resolver, not an App

- **WHEN** the signature of `a2kit.packages.health.run_checks` is inspected
- **THEN** it accepts a `HealthRegistry` and a `Resolver` parameter — it does not accept an `App`, keeping `packages/health` free of any dependency on `a2kit.app`

### Requirement: Health-check kwargs route through the DI resolver

The system SHALL resolve `@app.health_check`-registered function kwargs through the DI resolver's `resolve_params`, the same DI path used by tool dispatch. Each resolved kwarg SHALL follow the standard lifecycle protocol: on first resolution, the framework SHALL enter the resource via `__aenter__` (when the resource exposes the CM protocol) and record cleanup on the appropriate scope's stack (root for app-scope, child for per-call scope).

`__aexit__` SHALL fire when the owning scope unwinds:
- App-scope resources exit at **app shutdown** (root cleanup stack drained).
- Per-call resources exit at end of dispatch (child cleanup stack drained).

Health checks SHALL NOT trigger re-entry of an already-resolved app-scope resource. The first resolution anywhere in the app (a tool dispatch, a prior health check, or any other call site) is the sole entry point; subsequent health checks reusing the resource hit the cache.

Consumers SHALL NOT call internal "ensure ready" methods on resources passed as health-check kwargs. By the time the check body runs, the resource has been entered via the DI resolver's lifecycle protocol.

#### Scenario: first health probe enters an app-scope resource

- **GIVEN** `class SpyResource` with `entered`/`exited` counters, registered via `app.provide(SpyResource, ...)` (default app scope), with no other call site having referenced it yet
- **AND** `@app.health_check async def probe(spy: SpyResource): return a2kit.HealthResult.ok()`
- **WHEN** the health tool / `<app> health` CLI invokes the check for the first time in the app's lifetime
- **THEN** `spy.entered == 1` at the moment the check body runs
- **AND** `spy.exited == 0` (an app-scope resource stays entered for the app's lifetime)

#### Scenario: second health probe reuses the cached app-scope resource

- **GIVEN** the same setup, after one prior health probe has run
- **WHEN** the health tool invokes the check a second time
- **THEN** `spy.entered == 1` (still — no re-entry)
- **AND** the check body receives the same instance as the first call

#### Scenario: app-scope resource exits at app shutdown, not per probe

- **GIVEN** an app-scope resource entered by a prior health check
- **WHEN** the App's lifecycle exits (CLI subcommand completes, MCP transport shuts down)
- **THEN** `spy.exited == 1`

#### Scenario: shared app-scope resource across checks enters once

- **GIVEN** two registered checks `probe_a(spy: SpyResource)` and `probe_b(spy: SpyResource)` sharing the same app-scope resource
- **WHEN** the health-probe runs both in a single invocation
- **THEN** `spy.entered == 1` (app-scope resolution does not re-enter across checks)
- **AND** both checks receive the same instance
