# health-probe Specification Delta

> **Confirmed 2A** via reading-only spike on 2026-05-15. Trace:
> `run_checks` → `_run_one_check` → `app._container.resolve_params(check.fn)`
> → `Container.get(T)` → `_construct` → `_enter_lifecycle` (calls
> `__aenter__`). See `health/__init__.py:74-114` and
> `packages/di/container.py:302-537`. The
> `_run_one_check` docstring already documents this behaviour;
> this delta promotes it from internal comment to capability
> contract.

## ADDED Requirements

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
