## ADDED Requirements

### Requirement: Function `install_substrate_signature(fn, substrate, container)` performs a three-way classification

The dispatch package SHALL expose a function `install_substrate_signature(fn, substrate: Literal["fastapi", "fastmcp"], container: Container)` that classifies every parameter of `fn` into exactly one of three buckets:

1. **Substrate-reserved**: the parameter's annotation matches a frozen allowlist for the named substrate. The parameter SHALL pass through to the substrate-facing wrapper signature; the substrate populates it at dispatch.
2. **Container-known**: `container.has_provider(annotation)` returns true. The parameter SHALL be resolved by a2kit's Container via `call_scope` inside the wrapper body and SHALL NOT appear in the substrate-facing wrapper signature.
3. **Wire**: every remaining parameter. It SHALL appear in the substrate-facing wrapper signature and the substrate SHALL route it from request body, query, path, form, or equivalent.

The function SHALL return a substrate-native wrapper whose `__signature__` reflects only the substrate-reserved and wire parameters.

#### Scenario: Three-way split classifies a mixed signature correctly on FastAPI

- **GIVEN** `async def fn(*, request: Request, db: Database, id: str) -> Memory: ...` where `Container` has a provider for `Database`
- **WHEN** `install_substrate_signature(fn, "fastapi", container)` is called
- **THEN** the returned wrapper's `__signature__` exposes `request: Request, id: str`
- **AND** the wrapper body resolves `db: Database` via `Container.call_scope`

#### Scenario: FastMCP variant passes Context through

- **GIVEN** `async def fn(*, ctx: Context, db: Database, id: str) -> str: ...`
- **WHEN** `install_substrate_signature(fn, "fastmcp", container)` is called
- **THEN** the returned wrapper's `__signature__` exposes `ctx: Context, id: str`
- **AND** the body resolves `db` via Container

#### Scenario: Cross-substrate misclassification raises at install time

- **GIVEN** `async def fn(*, ctx: Context, id: str) -> str: ...` (uses FastMCP-only `Context`)
- **WHEN** the author registers it on the FastAPI substrate (e.g. `@app.api.get(...)`)
- **AND** `install_substrate_signature(fn, "fastapi", container)` runs
- **THEN** a `SubstrateSignatureError` is raised at install time naming the parameter `ctx`, its type `Context`, and the wrong substrate `"fastapi"`
- **AND** the error message lists the FastAPI-reserved allowlist and suggests using `@app.mcp.tool` if MCP semantics are intended

### Requirement: Frozen substrate-reserved allowlists

The dispatch package SHALL define two module-level frozen sets:

```
_FASTAPI_RESERVED = frozenset({starlette.requests.Request, starlette.responses.Response, fastapi.BackgroundTasks, starlette.websockets.WebSocket})
_FASTMCP_RESERVED = frozenset({fastmcp.Context})
```

Adding a type to either allowlist SHALL require an ADR 0020 amendment. A test SHALL assert the exact membership of each set against a known baseline so any unrecorded addition fails CI.

#### Scenario: Allowlist set membership is asserted

- **WHEN** the test `test_substrate_reserved_allowlist_stable` runs
- **THEN** it asserts `_FASTAPI_RESERVED == {Request, Response, BackgroundTasks, WebSocket}` and `_FASTMCP_RESERVED == {Context}` exactly
- **AND** if any frozenset has been changed without updating the baseline, the test fails

### Requirement: Container-known classification uses `has_provider`

The classifier SHALL use `Container.has_provider(annotation)` as the single source of truth for "is this a DI dep?". The classifier SHALL NOT use heuristics on the annotation shape (e.g., "is it a pydantic model").

#### Scenario: A pydantic model with no provider is wire

- **GIVEN** a tool with parameter `body: UserCreate` where `UserCreate` is a `BaseModel` and no provider is registered for `UserCreate`
- **WHEN** the splitter classifies the parameter
- **THEN** `body` is classified as wire (FastAPI will route it from the request body)

#### Scenario: A pydantic model with a provider is DI

- **GIVEN** a tool with parameter `settings: AppSettings` where `AppSettings` is a `BaseSettings` subclass and a provider exists for it
- **WHEN** the splitter classifies the parameter
- **THEN** `settings` is classified as Container-known
- **AND** the substrate-facing signature does not include `settings`
