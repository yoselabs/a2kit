## ADDED Requirements

### Requirement: `ToolDescriptor` carries `verb`, `expose`, and `authorize` fields

`ToolDescriptor` SHALL carry three additional fields:

- `verb: Literal["read", "list", "write"]` — the verb used at decoration time. Required.
- `expose: tuple[Literal["mcp", "api"], ...]` — the substrates this tool is registered on. Defaulted from the decorator's `expose=` kwarg; default `("mcp", "api")`.
- `authorize: Callable[..., bool | Awaitable[bool]] | None` — the authorization callable from the decorator's `authorize=` kwarg, or `None`.

These fields SHALL be materialized at `App.add_router(...)` (or equivalent registration path) and frozen on the descriptor.

The existing `format_hint` field is unchanged.

#### Scenario: Descriptor carries verb and expose

- **GIVEN** `@app.read async def fetch(*, id: str) -> Memory: ...`
- **WHEN** `app.tools()` is called
- **THEN** the descriptor has `verb == "read"`
- **AND** `expose == ("mcp", "api")` (the default)
- **AND** `authorize is None`

#### Scenario: expose= kwarg propagates to descriptor

- **GIVEN** `@app.read(expose=("mcp",)) async def llm_only(...): ...`
- **WHEN** `app.tools()` is called
- **THEN** the descriptor's `expose == ("mcp",)`

#### Scenario: authorize= kwarg propagates to descriptor

- **GIVEN** `@app.write(authorize=fn) async def upsert(...): ...` where `fn` is any callable
- **WHEN** `app.tools()` is called
- **THEN** the descriptor's `authorize is fn`
