## ADDED Requirements

### Requirement: Helpers are independently importable and FastMCP-native

Each a2kit helper SHALL be an independently-importable module that depends only
on `fastmcp`, `pydantic`, and the Python standard library. A helper SHALL NOT
require an `a2kit.App`, a shared a2kit composition root, DI container, or config
object to function, and SHALL be usable by sprinkling it onto a plain FastMCP
server.

#### Scenario: A helper works on a plain FastMCP server

- **GIVEN** a server authored with a plain `fastmcp.FastMCP()` instance (no `a2kit.App`)
- **WHEN** a single a2kit helper (e.g. the typed-TSV result serializer) is applied to one tool
- **THEN** the server builds and that tool's behavior reflects the helper, with no other a2kit construct imported

#### Scenario: A helper imports no a2kit core

- **GIVEN** any helper module under `a2kit.*`
- **WHEN** its import set is inspected
- **THEN** every import resolves to `fastmcp`, `pydantic`, the standard library, or the helper's own package — and none to a shared a2kit core, `App`, DI container, or config

### Requirement: The extractability invariant holds for every helper

Every a2kit helper SHALL be extractable into FastMCP as a copy-one-file +
open-one-issue operation: it SHALL NOT import another a2kit helper's internals,
and the architecture SHALL NOT reintroduce an `App`-like composition spine that
helpers depend on. This invariant SHALL be enforceable as an architectural lint
rule (`AK###`), not only by review.

#### Scenario: Cross-helper coupling is rejected

- **GIVEN** the extractability lint rule is active
- **WHEN** a helper module imports another a2kit helper's internal (non-public) symbol, or imports a reintroduced shared composition core
- **THEN** the lint rule fails with the offending import named

#### Scenario: A helper is liftable in isolation

- **GIVEN** any single helper module and its own tests
- **WHEN** the module and its tests are copied out of a2kit into a standalone location with only `fastmcp` + `pydantic` available
- **THEN** the module imports and its tests pass without pulling any other a2kit module

### Requirement: Consumer dependency points at FastMCP directly

A consumer server SHALL depend on FastMCP directly as its composition root, and
SHALL treat a2kit as an optional add-on dependency for specific helpers. a2kit
SHALL NOT be the required composition root for a consumer server.

#### Scenario: Consumer composes on FastMCP, adds helpers à la carte

- **GIVEN** a consumer MCP server
- **WHEN** it is composed
- **THEN** its composition root is a FastMCP server, and any a2kit helpers it uses are imported individually and are removable without losing the server's ability to build
