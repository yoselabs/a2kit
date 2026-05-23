## ADDED Requirements

### Requirement: Verb decorators accept `expose=` kwarg

`@a2kit.read`, `@a2kit.list_`, and `@a2kit.write` SHALL accept an `expose: tuple[Literal["mcp", "api"], ...] = ("mcp", "api")` kwarg. The kwarg declares which substrates receive the registration when the multiplex serves both. Default is both. Passing an empty tuple SHALL raise `ValueError` at decoration time naming the verb (a tool exposed nowhere is meaningless).

`expose=` SHALL NOT be accepted on `@app.api.<method>` or `@app.mcp.<feature>` decorators — those are single-surface by definition; passing `expose=` to them raises `TypeError`.

#### Scenario: expose=("mcp",) registers MCP only

- **GIVEN** `@app.read(expose=("mcp",)) async def llm_only(*, prompt: str) -> str: ...`
- **WHEN** the multiplex is built with both substrates having other registrations
- **THEN** the FastMCP `tools/list` includes `llm_only`
- **AND** no FastAPI route `POST /api/llm_only` is registered

#### Scenario: expose=("api",) registers FastAPI only

- **GIVEN** `@app.list(expose=("api",)) async def audit(*, since: datetime, db: Database) -> list[AuditRow]: ...`
- **WHEN** the multiplex is built
- **THEN** the FastAPI route `POST /api/audit` exists
- **AND** `audit` is absent from MCP `tools/list`

#### Scenario: Empty expose raises

- **WHEN** a tool is decorated `@app.read(expose=())`
- **THEN** `ValueError` is raised at decoration time naming `expose=` and the verb

### Requirement: Verb decorators accept `authorize=` kwarg

`@a2kit.read`, `@a2kit.list_`, and `@a2kit.write` SHALL accept an `authorize: Callable[..., bool | Awaitable[bool]] | None = None` kwarg. The callable's signature is intentionally permissive (`Callable[...]`) because the concrete `Principal` and per-tool argument types are introduced by a future change (`add-auth`). The kwarg stores the callable on the descriptor for future enforcement.

`@app.api.<method>` and `@app.mcp.<feature>` decorators SHALL also accept `authorize=` for uniformity. Enforcement semantics are out of scope of this change; the kwarg surface and descriptor field are reserved here so authors do not refactor signatures when the auth change lands.

#### Scenario: authorize= accepted on all three families

- **WHEN** an author writes `@app.read(authorize=fn)`, `@app.api.get("/x", authorize=fn)`, or `@app.mcp.tool(authorize=fn)` where `fn` is any callable
- **THEN** the decorator accepts the kwarg without raising
- **AND** the descriptor (or equivalent per-family registration record) records `authorize=fn`

#### Scenario: authorize= callable is not invoked by this change

- **GIVEN** any tool with `authorize=fn` where `fn` would raise if invoked
- **WHEN** the tool is dispatched under serve before `add-auth` lands
- **THEN** `fn` is NOT invoked
- **AND** the tool body runs normally (the kwarg is reserved surface; enforcement awaits `add-auth`)
