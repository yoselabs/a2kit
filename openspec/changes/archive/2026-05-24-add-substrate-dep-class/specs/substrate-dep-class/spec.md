## ADDED Requirements

### Requirement: Substrate-dep is the fourth signature class

`split_signature` (`packages/dispatch/substrate.py`) SHALL classify parameters into four buckets: substrate-reserved, container-resolved (lazy), substrate-dep, and wire. `substrate-dep` is any parameter whose `Annotated[...]` metadata contains a `fastapi.params.Depends` or `fastapi.params.Security` instance. Detection SHALL be lazy: `fastapi.params` is only imported when a candidate annotation is observed.

For `substrate="fastapi"`, substrate-dep params SHALL pass through to the generated `__signature__` with their original `Annotated` metadata preserved so FastAPI's own dependency graph can walk them.

For `substrate="fastmcp"`, the presence of any substrate-dep param SHALL cause `install_substrate_signature` to raise `SubstrateSignatureError("FastAPI Depends/Security cannot appear on MCP-exposed tools; remove the marker or scope this tool with expose=('api',)")`.

#### Scenario: FastAPI Depends passes through

- **GIVEN** a tool `async def fetch(*, db: Annotated[Database, Depends(get_db)], id: str) -> Memory: ...`
- **WHEN** `split_signature(fetch, substrate="fastapi")` runs
- **THEN** `db` appears in `result.substrate_dep`
- **AND** `id` appears in `result.wire`

#### Scenario: FastAPI Security passes through

- **GIVEN** a tool `async def admin(*, principal: Annotated[Principal, Security(guard)], id: str) -> None: ...`
- **WHEN** `split_signature(admin, substrate="fastapi")` runs
- **THEN** `principal` appears in `result.substrate_dep`

#### Scenario: Non-marker Annotated still wire

- **GIVEN** a tool `async def fetch(*, label: Annotated[str, "wire help text"]) -> None: ...`
- **WHEN** `split_signature(fetch, substrate="fastapi")` runs
- **THEN** `label` appears in `result.wire`
- **AND** `result.substrate_dep` is empty

#### Scenario: substrate-dep on MCP rejected at build time

- **GIVEN** a tool `async def fetch(*, db: Annotated[Database, Depends(get_db)], id: str) -> Memory: ...` with default `expose=("mcp","api")`
- **WHEN** `install_substrate_signature(fn, ..., substrate="fastmcp")` runs as part of MCP build
- **THEN** `SubstrateSignatureError` is raised with the documented hint
