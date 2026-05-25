## ADDED Requirements

### Requirement: expose= validates against the live surface registry

Verb decorators (`@a2kit.read`, `@a2kit.write`, `@a2kit.list_`) SHALL validate the `expose=` kwarg against the set of currently-registered surface names. The set MUST be obtained at decoration time from a kernel-layer name registry that is kept in sync with `SURFACE_REGISTRY` by a side-effect of `register_surface()`. The literal `frozenset({"mcp", "api"})` MUST NOT appear in the verb-decorator validation path.

#### Scenario: A registered surface name is accepted

- **GIVEN** the MCP and HTTP packages are imported (their surfaces self-register)
- **WHEN** a tool is decorated `@a2kit.read(expose=("mcp",))`
- **THEN** the decorator does not raise

#### Scenario: An unregistered surface name is rejected with an enumerated message

- **GIVEN** the MCP and HTTP packages are imported
- **WHEN** a tool is decorated `@a2kit.read(expose=("foo",))`
- **THEN** the decorator raises `TypeError`
- **AND** the error message enumerates the currently-registered surface names (e.g. "Registered surfaces: ('mcp', 'api')")
- **AND** the error message does not embed a hardcoded surface name list

#### Scenario: A newly-registered surface name is accepted without code changes to verbs

- **GIVEN** a test fixture registers a synthetic `StubSurface(name="test")`
- **WHEN** a tool is decorated `@a2kit.read(expose=("test",))`
- **THEN** the decorator does not raise
- **AND** no edits to `src/a2kit/_verbs.py` were required

#### Scenario: Empty registry raises an actionable message

- **GIVEN** no Surface implementations have been imported
- **WHEN** a tool is decorated `@a2kit.read(expose=("mcp",))`
- **THEN** the decorator raises `TypeError`
- **AND** the message instructs the author to import a surface-mounting package (e.g. `a2kit.packages.mcp`)
