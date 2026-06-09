## MODIFIED Requirements

### Requirement: Title is independent of tool name

The system SHALL forward `title=` to MCP `ToolAnnotations.title` while keeping the tool's `name` (the protocol identifier) as the **canonical name** resolved per `tool-descriptors`. The public verb decorators (`@a2kit.read`, `@a2kit.write`, `@a2kit.list_`) SHALL NOT accept a `name=` kwarg; the protocol identifier SHALL be the canonical name, not the bare `fn.__name__`.

On the MCP surface the canonical name SHALL be produced by mounting each router as a native sub-server (`FastMCP.mount(namespace=slug)`, the homomorphism — ADR 0028 decision 3) so a router verb registers under the **flat `slug_leaf`** name (`entity` + `update` → `entity_update`); an app-level verb (no owning router) registers under the bare `leaf` on the root server; and a verb with `canonical_name_override="…"` registers under that string **verbatim**, with the slug never re-applied. MCP is the only flat namespace, so this mount is what dissolves the cross-router collision class (two routers each defining `update` no longer collide). The `title` annotation SHALL remain independent of, and unaffected by, this name resolution.

#### Scenario: Router verb gets the flat slug_leaf name

- **GIVEN** `class Entity(a2kit.Router): slug = "entity"` with a method `async def update(...) -> Memory` decorated `@a2kit.read(title="Update Entity")`
- **WHEN** the MCP server is built
- **THEN** the MCP registration has `name="entity_update"` (flat, via `mount(namespace="entity")`) and `ToolAnnotations(title="Update Entity")`

#### Scenario: App-level verb keeps the bare leaf name

- **GIVEN** an app-level method `async def health(...) -> Health` with no owning router, decorated `@a2kit.read`
- **WHEN** the MCP server is built
- **THEN** the MCP registration has `name="health"` (bare leaf, no app-name prefix) on the root server

#### Scenario: Pinned override is verbatim on MCP

- **GIVEN** `class Jira(a2kit.Router): slug = "jira"` with `@a2kit.read(canonical_name_override="jira_search") async def search(...) -> Results`
- **WHEN** the MCP server is built
- **THEN** the MCP registration has `name="jira_search"` exactly — the slug is not re-applied (never `jira_jira_search`)
- **AND** the name is byte-for-byte identical to the pre-migration explicit-name registration

#### Scenario: Two routers with the same leaf do not collide

- **GIVEN** `Entity(slug="entity")` and `Ontology(slug="ontology")` each defining a `@a2kit.read def update`
- **WHEN** the MCP server is built
- **THEN** both `entity_update` and `ontology_update` are registered as distinct tools
- **AND** no silent flat-`update` collision occurs
