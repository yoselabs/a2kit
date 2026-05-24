## ADDED Requirements

### Requirement: Exactly one signature installer

The a2kit codebase SHALL contain exactly one signature installer: `install_substrate_signature` in `src/a2kit/packages/dispatch/substrate.py`. The previous `install_mcp_signature` SHALL be removed; the public symbol SHALL remain only as a migration-hint raise pointing to `install_substrate_signature(fn, surface=..., container=...)`. Both projection tools (`@app.read/list/write`) and substrate-native tools (`@app.mcp.tool`, `@app.api.<method>`) SHALL produce wrappers via the single installer.

#### Scenario: install_mcp_signature is a migration raise

- **WHEN** code calls `from a2kit.packages.mcp._wrappers import install_mcp_signature; install_mcp_signature(fn)`
- **THEN** `TypeError` is raised with hint pointing to `install_substrate_signature`

#### Scenario: ADR 0020 Option-B byte-snapshot guarantee superseded

- **WHEN** the test suite runs
- **THEN** no test asserts `str(__signature__)` byte-equality across the installer migration
- **AND** behavioral assertions cover Context detection, schema generation, parameter classification

### Requirement: Surface drives signature classification

`install_substrate_signature` SHALL take a `Surface` parameter and consume `surface.reserved_types` + `surface.substrate_dep_markers` directly. No code path SHALL discriminate on substrate name strings. Context detection on MCP SHALL flow from `McpSurface.reserved_types = frozenset({Context})`, not from a hardcoded `"fastmcp"` check.

#### Scenario: Single installer produces MCP and API wrappers

- **GIVEN** the same author function `async def fetch(*, ctx: Context, db: Database, id: str) -> Memory: ...` registered on both surfaces
- **WHEN** wrappers are built via `install_substrate_signature(fn, surface=mcp_surface, ...)` and again for `api_surface`
- **THEN** the MCP wrapper exposes `id` (wire), passes `ctx` (reserved), resolves `db` (container)
- **AND** the API wrapper exposes `id` (wire), resolves `db` (container), has no `ctx` param
