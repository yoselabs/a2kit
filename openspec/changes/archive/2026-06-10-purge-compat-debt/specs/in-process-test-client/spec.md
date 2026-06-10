# in-process-test-client

## REMOVED Requirements

### Requirement: TestClient SHALL surface renamed method names with embedded migration hints

**Reason**: The `TestClient.__getattr__` interception, the `_MIGRATED_NAMES` /
`_REMOVED_NAMES` tables, and their embedded migration hints are removed (no
backward compatibility, no migration hints). Renamed / removed method names
(`call`, `override`) no longer get a bespoke hinted `TypeError`; they raise the
language-default `AttributeError` like any unknown attribute. Replaced by
"TestClient removed method names raise `AttributeError`".

## ADDED Requirements

### Requirement: TestClient removed method names raise `AttributeError`

The `TestClient` class SHALL NOT intercept attribute access for renamed or
removed method names. Accessing a removed name (e.g. the pre-v0.33 `call`, the
removed `override`) raises the standard `AttributeError` with no embedded
migration hint and no alias. The canonical names (`invoke`, `call_wire`)
remain the only callable surface. The migration recipe lives only in the
CHANGELOG.

#### Scenario: removed `.call` raises AttributeError

- **GIVEN** a `TestClient` instance
- **WHEN** test code accesses `client.call`
- **THEN** `AttributeError` is raised (not `TypeError`, no migration hint)

#### Scenario: removed `.override` raises AttributeError

- **GIVEN** a `TestClient` instance
- **WHEN** test code accesses `client.override`
- **THEN** `AttributeError` is raised

#### Scenario: Canonical name still works

- **GIVEN** `await client.invoke("demo.ping", msg="hi")`
- **WHEN** the call is awaited
- **THEN** the tool dispatches and returns its payload (no `TypeError`)

## MODIFIED Requirements

### Requirement: Ambient-LDD pytest fixture

The system SHALL provide `a2kit.testing.ambient_for_tests` — a
`pytest.fixture` that wraps test execution in an active LDD ambient
state, allowing tests to call orchestrator or phase functions
directly (bypassing `TestClient.invoke`) without raising
`RequestScopeMissing`.

The fixture SHALL be opt-in (not `autouse=True` at the framework
level). Consumers requiring project-wide ambient state SHALL
re-export it with `autouse=True` in their own `conftest.py`. This
preserves the loud-by-default contract of `RequestScopeMissing`
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
- **WHEN** the test body calls `await a2kit.log.info("evt", k=1)`
- **THEN** the call completes without raising
  `RequestScopeMissing`

#### Scenario: tests not using the fixture still fail loud

- **GIVEN** a pytest test function that does NOT depend on
  `ambient_for_tests` and is not under an autouse re-export
- **WHEN** the test body calls `await a2kit.log.info("evt", k=1)`
- **THEN** the call raises `RequestScopeMissing`

#### Scenario: default flags suppress event/report emission

- **GIVEN** a test using `ambient_for_tests`
- **WHEN** the test body calls `await a2kit.log.info("evt")` and
  `await a2kit.log.info(SomeReport(...))`
- **THEN** neither emission produces a wire-side effect (no sinks
  fire), consistent with `events_enabled=False` and
  `reports_enabled=False`

#### Scenario: fixture is importable from the public surface

- **WHEN** a consumer writes `from a2kit.testing import ambient_for_tests`
- **THEN** the import resolves and the imported object is a
  pytest fixture (carries the `_pytestfixturefunction` marker
  attribute)

### Requirement: Pre-decorated autouse ambient-LDD fixture

The system SHALL provide `a2kit.testing.ambient_for_tests_autouse` —
a peer of `ambient_for_tests` that is pre-decorated with
`pytest.fixture(autouse=True)` at the framework level. Consumers
that want project-wide ambient binding SHALL re-export this single
name in their `conftest.py` without touching pytest internals.

The autouse variant SHALL share the same default flag values as
`ambient_for_tests` (`ctx = null_context()`, `events_enabled = False`,
`reports_enabled = False`) and SHALL produce equivalent runtime
behavior; the only difference is the `autouse=True` decoration.

The existing `ambient_for_tests` fixture SHALL remain unchanged.
Consumers that adopted the documented `__wrapped__` re-export
pattern SHALL continue to work without migration. The framework
SHALL NOT deprecate either flavor.

The `OPERATIONAL_CONTRACTS.md` Q-AmbientForTests entry SHALL
document both flavors with a one-line decision rule:
project-wide-binding consumers import `_autouse`; per-test opt-in
consumers import the bare `ambient_for_tests`.

#### Scenario: autouse variant binds ambient without consumer re-decoration

- **GIVEN** a consumer's `conftest.py` containing only
  `from a2kit.testing import ambient_for_tests_autouse`
- **WHEN** a pytest test in that project calls
  `await a2kit.log.info("evt", k=1)` without declaring any fixture
  in its signature
- **THEN** the call completes without raising `RequestScopeMissing`

#### Scenario: autouse variant exposes pytest fixture metadata

- **WHEN** a test imports
  `from a2kit.testing import ambient_for_tests_autouse`
- **THEN** the imported object carries the
  `_pytestfixturefunction` marker attribute
- **AND** its `autouse` attribute resolves to `True`

#### Scenario: bare ambient_for_tests fixture is unchanged

- **GIVEN** a project that imports only the bare
  `ambient_for_tests` fixture (no autouse re-export)
- **WHEN** a pytest test that does NOT declare `ambient_for_tests`
  in its signature calls `await a2kit.log.info("evt", k=1)`
- **THEN** the call raises `RequestScopeMissing`, exactly as before this change
