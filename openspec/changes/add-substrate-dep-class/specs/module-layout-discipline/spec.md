## ADDED Requirements

### Requirement: `A2K-SUBSTRATE-DEP` lint rule forbids FastAPI markers on MCP-exposed tools

A lint rule `A2K-SUBSTRATE-DEP` SHALL scan tool functions; if `Annotated[T, fastapi.params.Depends|Security]` appears on any parameter AND the function's effective `expose` includes `"mcp"`, the rule SHALL hard-fail with hint `"FastAPI Depends/Security cannot appear on MCP-exposed tools; remove the marker or scope this tool with expose=('api',)"`. Tools explicitly scoped `expose=("api",)` SHALL be exempt. Test files under `tests/` are exempt via the standard `is_fixture_path` filter.

#### Scenario: Marker on default-expose tool rejected

- **GIVEN** `@app.read async def fetch(*, who: Annotated[Principal, Depends(guard)], id: str) -> Memory: ...`
- **WHEN** `make lint` runs
- **THEN** `A2K-SUBSTRATE-DEP` fires with the documented hint

#### Scenario: Marker on api-only tool passes

- **GIVEN** `@app.read(expose=("api",)) async def fetch(*, who: Annotated[Principal, Depends(guard)], id: str) -> Memory: ...`
- **WHEN** `make lint` runs
- **THEN** `A2K-SUBSTRATE-DEP` does not fire
