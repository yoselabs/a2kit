# error-contract-tests Specification

## Purpose
TBD - created by archiving change a2effect-foundation. Update Purpose after archive.
## Requirements
### Requirement: `contract_tests(app)` generates per-tool envelope tests

The `a2effect.testing.contract_tests(app)` function SHALL be a pytest plugin helper that, when called at module scope in a test file, generates parametrized tests covering every tool registered on the app. Generated tests SHALL be discovered by pytest's collection machinery without further author wiring.

Generated tests SHALL cover at minimum these three checks per tool:

1. **Envelope round-trip**: every type in the tool's `Raises(...)` set produces a valid `ErrorEnvelope` when raised through the dispatch pipeline, with `type` matching the class name, `kind` matching the class's declared `kind`, and `retryable` matching the class's declared `retryable`.

2. **Dead-enricher detection**: every registered enricher (router-level + app-level) whose output type is `AppError` or a subclass SHALL be reachable — i.e., the output type appears in at least one tool's `Raises(...)` set. Enrichers whose output never appears in any tool's contract SHALL fail this check (likely a sign of accidental dead code or a missing declaration).

3. **Surface parity**: for each tool's declared `Raises(...)` member, the envelope produced by the MCP renderer, the HTTP renderer, and the CLI renderer SHALL contain identical `error.type`, `error.kind`, `error.retryable`, and `error.hint` values (rendering of the surrounding container differs by surface, but the inner envelope is identical).

#### Scenario: contract_tests detects mis-typed envelope

- **GIVEN** an app with a tool declaring `Raises(NotFound)`
- **AND** an enricher that returns `InvalidId` for the body's raised exception (mismatch — translated type isn't in the declared set for this tool)
- **WHEN** pytest runs the generated contract tests
- **THEN** at least one parametrized test for that tool fails with a clear message naming the mismatch

#### Scenario: contract_tests detects dead enricher

- **GIVEN** an app where a router enricher returns `SomeUnusedError` (not in any tool's `Raises(...)`)
- **WHEN** pytest runs the generated tests
- **THEN** the dead-enricher test fails naming `SomeUnusedError` and the router that registered it

#### Scenario: contract_tests detects surface drift

- **GIVEN** a tool whose error rendering differs between MCP and HTTP (e.g., HTTP renderer doesn't honor a class's `http_status` override)
- **WHEN** pytest runs the surface-parity test
- **THEN** the test fails naming the surface that drifted

### Requirement: Generated tests are introspectable and customizable

The `contract_tests(app)` helper SHALL accept optional keyword arguments to disable specific check categories (`envelope_round_trip=False`, `dead_enricher=False`, `surface_parity=False`) for projects with bespoke needs. By default all three categories run.

Generated test IDs SHALL include the tool name and the error type being tested so failures are immediately attributable (e.g., `test_envelope_round_trip[memory.fetch-NotFound]`).

#### Scenario: Disabling a category

- **GIVEN** `contract_tests(app, dead_enricher=False)` in a conftest
- **WHEN** pytest collects the tests
- **THEN** envelope-round-trip and surface-parity tests are generated
- **AND** dead-enricher tests are NOT generated

