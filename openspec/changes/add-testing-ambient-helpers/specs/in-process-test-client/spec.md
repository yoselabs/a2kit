# in-process-test-client Specification Delta

## ADDED Requirements

### Requirement: Lazy-thunk testing constructor

The system SHALL provide `a2kit.testing.lazy(value)` — a synchronous
factory that returns a zero-argument async callable conforming to the
`Lazy[T] = Callable[[], Awaitable[T]]` shape used at the tool seam.

The returned thunk SHALL return the original `value` unchanged on
each invocation. The framework SHALL NOT deep-copy, cache, or
otherwise transform the value; callers needing per-call freshness
SHALL construct their own thunk.

`a2kit.testing.lazy` SHALL be importable as
`from a2kit.testing import lazy` and SHALL appear in
`a2kit.testing.__all__`. `Lazy` SHALL remain a `TypeAlias` — no
runtime `Lazy.of` class-method is added.

#### Scenario: lazy(value) returns a zero-arg async callable

- **GIVEN** an arbitrary value `v = object()`
- **WHEN** a test calls `thunk = a2kit.testing.lazy(v)`
- **THEN** `thunk` is callable with zero arguments
- **AND** `await thunk()` returns `v`
- **AND** `await thunk() is v` (identity preserved, no copy)

#### Scenario: lazy thunk satisfies the Lazy[T] tool kwarg

- **GIVEN** a tool declaring `browser: Lazy[BrowserPool]`
- **WHEN** a test injects a fake via `lazy(fake_browser)` through
  the DI override surface
- **THEN** the tool body's `await browser()` returns `fake_browser`
  and no `TypeError` is raised by the dispatcher's Lazy unwrapping
  path

### Requirement: Ambient-LDD pytest fixture

The system SHALL provide `a2kit.testing.ambient_for_tests` — a
`pytest.fixture` that wraps test execution in an active LDD ambient
state, allowing tests to call orchestrator or phase functions
directly (bypassing `TestClient.invoke`) without raising
`AmbientContextMissing`.

The fixture SHALL be opt-in (not `autouse=True` at the framework
level). Consumers requiring project-wide ambient state SHALL
re-export it with `autouse=True` in their own `conftest.py`. This
preserves the loud-by-default contract of `AmbientContextMissing`
outside test contexts that explicitly request the ambient.

The fixture SHALL default to:
- `ctx = null_context()`
- `events_enabled = False`
- `reports_enabled = False`

Consumers requiring different flag combinations SHALL construct
their own fixture using `ldd_state_for_call` directly. The
framework SHALL NOT expose parametric variants of
`ambient_for_tests`.

#### Scenario: tests using the fixture can emit LDD events without error

- **GIVEN** a pytest test function declaring `ambient_for_tests`
  in its signature
- **WHEN** the test body calls `await a2kit.ldd.event("evt", k=1)`
- **THEN** the call completes without raising
  `AmbientContextMissing`

#### Scenario: tests not using the fixture still fail loud

- **GIVEN** a pytest test function that does NOT depend on
  `ambient_for_tests` and is not under an autouse re-export
- **WHEN** the test body calls `await a2kit.ldd.event("evt", k=1)`
- **THEN** the call raises `AmbientContextMissing` with the v0.33
  hint message

#### Scenario: default flags suppress event/report emission

- **GIVEN** a test using `ambient_for_tests`
- **WHEN** the test body calls `await a2kit.ldd.event("evt")` and
  `await a2kit.ldd.report(SomeReport(...))`
- **THEN** neither emission produces a wire-side effect (no sinks
  fire), consistent with `events_enabled=False` and
  `reports_enabled=False`

#### Scenario: fixture is importable from the public surface

- **WHEN** a consumer writes `from a2kit.testing import ambient_for_tests`
- **THEN** the import resolves and the imported object is a
  pytest fixture (carries the `_pytestfixturefunction` marker
  attribute)
