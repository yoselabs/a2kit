## ADDED Requirements

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
  `await a2kit.ldd.event("evt", k=1)` without declaring any fixture
  in its signature
- **THEN** the call completes without raising `AmbientContextMissing`

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
  in its signature calls `await a2kit.ldd.event("evt", k=1)`
- **THEN** the call raises `AmbientContextMissing` with the v0.33
  hint message, exactly as before this change

#### Scenario: both flavors share default flag values

- **GIVEN** a test running under `ambient_for_tests_autouse`
- **WHEN** the test body calls `await a2kit.ldd.event("evt")` and
  `await a2kit.ldd.report(SomeReport(...))`
- **THEN** neither emission produces a wire-side effect (no sinks
  fire), matching the bare fixture's
  `events_enabled=False` / `reports_enabled=False` defaults
