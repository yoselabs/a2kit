# docs-code-parity — canonical-api-drift-gate delta

## ADDED Requirements

### Requirement: Canonical-type method drift gate SHALL extend the README symbol-drift check

The CI lint stage SHALL fail when a method name accessed on a
documented canonical type in `README.md` does not exist on the
live class. The canonical types under coverage SHALL include at
minimum `TestClient`, `App`, `Router`, the `ToolContext` re-export,
and the verb decorators `read` / `write` / `list_`. The gate
SHALL parse fenced ```python``` code blocks, AST-walk for
`ast.Attribute` nodes whose `obj_name` resolves to a canonical type
(directly or via variable-name registration within the same block),
and assert `hasattr(canonical_type, attr_name)`.

#### Scenario: Renamed canonical method fails the gate

- **GIVEN** README contains `await client.call(tool, msg="hi")` and `TestClient.call` does not exist on the live class
- **WHEN** `make lint` runs
- **THEN** the drift-gate test fails with a message naming `client.call` and the README location where the call is documented

#### Scenario: Aliased canonical method passes the gate

- **GIVEN** README contains `await client.invoke(tool, msg="hi")` and `TestClient.invoke` exists on the live class
- **WHEN** the gate runs
- **THEN** the access resolves and the gate passes for that block

#### Scenario: Variable name in code block registers as a canonical type

- **GIVEN** a README code block contains `client = a2kit.testing.client(app)` followed by `await client.invoke(...)`
- **WHEN** the gate parses the block
- **THEN** the assignment registers `client` as `TestClient` for the remainder of the block, and `client.invoke` resolves against `TestClient.invoke`

### Requirement: Canonical-API call-shape exerciser SHALL run as a sister test

`tests/test_canonical_apis.py` SHALL exist and SHALL exercise the
documented call shapes end-to-end with a small fixture app. The
test SHALL run as part of `make lint` (alongside the README
drift gate) so silent renames-without-test-updates fail at CI
time. Coverage SHALL include at minimum:

- `TestClient.invoke(...)` and `TestClient.call_wire(...)`
- `App.singleton(T, factory)` and `App.singleton(T, factory, teardown=...)`
- `@a2kit.read()`, `@a2kit.write(...)`, `@a2kit.list_()`
- `Router` subclass with `slug = "x"` and `tools = (...)`

The test SHALL use bind-against-live-types rather than
text-matching, so a rename that preserves observable behavior
under a new name (but breaks the documented call shape) fails.

#### Scenario: Each canonical call shape runs successfully

- **GIVEN** the fixture app from `test_canonical_apis.py`
- **WHEN** the test exercises each documented call shape
- **THEN** every call succeeds (no AttributeError, no TypeError, no signature mismatch)

#### Scenario: Removed surface fails the test loudly

- **GIVEN** a previously-documented call shape that no longer exists on the canonical type
- **WHEN** the test runs after the removal
- **THEN** the test fails with a message naming the removed method
