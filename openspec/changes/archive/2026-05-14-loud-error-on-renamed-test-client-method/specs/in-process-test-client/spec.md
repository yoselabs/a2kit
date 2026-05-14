# in-process-test-client — loud-error-on-renamed-test-client-method delta

## ADDED Requirements

### Requirement: TestClient SHALL surface renamed method names with embedded migration hints

The `TestClient` class SHALL intercept attribute access on names that correspond to methods renamed in a prior release and raise `TypeError` (not `AttributeError`) with an error message that includes the new method name and an explicit "no alias is provided" note. Genuinely-unknown attribute names SHALL continue to raise the
standard `AttributeError`.

The framework SHALL NOT host backward-compat aliases for renamed
surfaces. Aliases hide migrations from consumers' read paths.
Renames are effective immediately; the only contract is that the
error message names the new attribute.

#### Scenario: Renamed `.call` raises TypeError with hint

- **GIVEN** a v0.32-style call shape `await client.call("demo.ping", msg="hi")`
- **WHEN** the call is awaited against v0.33+
- **THEN** `TypeError` is raised
- **AND** the message contains `"renamed"` and `"invoke"`

#### Scenario: Genuinely unknown attribute falls through to AttributeError

- **GIVEN** an access `client.completely_unknown_method`
- **WHEN** the attribute resolves
- **THEN** `AttributeError` is raised (not `TypeError`)
- **AND** the message names the missing attribute

#### Scenario: Canonical name still works

- **GIVEN** `await client.invoke("demo.ping", msg="hi")`
- **WHEN** the call is awaited
- **THEN** the tool dispatches and returns its payload (no `TypeError`)
