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
Constructing `App(...)` with that keyword SHALL raise the standard
unexpected-kwarg `TypeError` (naming the offending kwarg + the
CHANGELOG); the bespoke `@app.health_check` hint is swept under the
tombstone sunset rule (`AGENTS.md` §1) and `health_tool` falls through
to `App.__init__`'s generic kwarg rejection.

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

#### Scenario: `health_tool=True` raises the generic unexpected-kwarg TypeError

- **GIVEN** code `a2kit.App("a", health_tool=True)`
- **WHEN** the constructor evaluates
- **THEN** `TypeError` is raised naming `health_tool` as an unexpected kwarg and pointing at the CHANGELOG
- **AND** no bespoke `health_check` hint string is required

#### Scenario: No checks → no synthetic tool

- **GIVEN** `app = a2kit.App("a")` with no `@app.health_check` registrations
- **WHEN** the app is inspected
- **THEN** `_meta.health` is NOT present in `app.tools()`
- **AND** invoking `_meta.health` over MCP returns the standard "unknown tool" error

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

### Requirement: Transport-native liveness route on HTTP serve

The multiplex parent SHALL expose a static liveness route at the root path `GET /health` returning HTTP 200 with body `{"status": "ok"}` whenever a2kit serves over HTTP (`serve --transport=http`), independent of which surfaces are mounted. The route SHALL be present for an MCP-only serve, an api-only serve, and a both-surfaces serve alike.

The liveness route SHALL be **dumb**: it SHALL NOT resolve DI, enter resources,
or aggregate surface health — a wedged DI graph SHALL still answer 200. Degraded
/ readiness aggregation remains the responsibility of the `_meta.health` tool;
the two SHALL stay separate.

The liveness route SHALL be reachable **without credentials** regardless of any
authentication strategy configured on a surface: it is a sibling of the surface
mounts on the parent application, which carries no authentication middleware.

The existing `/api/health` route on the FastAPI sub-app SHALL remain unchanged
(back-compatible for REST deployments).

#### Scenario: MCP-only serve exposes a liveness route

- **GIVEN** a runtime with only MCP registrations, served over HTTP
  (`--select surface=mcp`)
- **WHEN** a client issues `GET /health`
- **THEN** the response status is 200 and the body is `{"status": "ok"}`

#### Scenario: api-only serve exposes the same root liveness route

- **GIVEN** a runtime with only `api`-surface registrations, served over HTTP
- **WHEN** a client issues `GET /health`
- **THEN** the response status is 200 and the body is `{"status": "ok"}`

#### Scenario: both-surfaces serve exposes /health and keeps /api/health

- **GIVEN** a runtime with both MCP and `api` registrations, served over HTTP
- **WHEN** a client issues `GET /health` and `GET /api/health`
- **THEN** both return 200 with body `{"status": "ok"}`

#### Scenario: liveness answers with a wedged DI graph

- **GIVEN** an HTTP serve whose provider resolution would raise on any tool call
- **WHEN** a client issues `GET /health`
- **THEN** the response status is 200 — the route resolved no DI

#### Scenario: liveness is reachable without credentials

- **GIVEN** an HTTP serve with an authentication strategy configured on a
  surface (e.g. `APIKeyAuth` on `api`, or an MCP `auth=` provider)
- **WHEN** a client issues `GET /health` with no credentials
- **THEN** the response status is 200 — the parent-root route is not behind any
  surface's auth middleware

#### Scenario: no parent, no route

- **GIVEN** an App with no registrations on any surface
- **WHEN** `build_parent_app` is invoked
- **THEN** it raises `ValueError` (unchanged) and no `/health` route is served

