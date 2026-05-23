## ADDED Requirements

### Requirement: `Principal` is owned by the framework, not the auth wrapper

`Principal` SHALL be defined as a frozen dataclass in `a2kit.packages.context.principal`: `{subject: str, scopes: frozenset[str], claims: Mapping[str, Any], issued_by: str, raw_token: str | None}`. It SHALL be re-exported from `a2kit.packages.context` and lazily from top-level `a2kit.Principal`. Auth wrappers (in the separate `add-auth` change) SHALL produce `Principal` instances; they SHALL NOT define their own `Principal` type.

#### Scenario: Principal frozen

- **GIVEN** `p = Principal(subject="u1", scopes=frozenset(), claims={}, issued_by="test", raw_token=None)`
- **WHEN** code attempts `p.subject = "u2"`
- **THEN** `FrozenInstanceError` is raised

### Requirement: Principal is written into `call_scope` as SCOPED

When a substrate produces a `Principal` for a request (via reserved-param resolution or middleware), the substrate adapter SHALL write it into the active call scope as a SCOPED provider before the tool body runs. Tool bodies and `authorize=` callables SHALL be able to resolve `principal: Principal` by type annotation alone.

#### Scenario: Tool body resolves Principal via DI on both substrates

- **GIVEN** `@app.read async def me(*, principal: Principal) -> dict: return {"subject": principal.subject}`
- **WHEN** invoked via HTTP and via MCP with the same authenticated subject `"u1"`
- **THEN** both invocations return `{"subject": "u1"}`
- **AND** no explicit container registration of `Principal` was performed by the author

### Requirement: `AuthorizeGateStage` resolves the gate via DI and short-circuits on falsy return

`packages/dispatch/stages.py:AuthorizeGateStage` SHALL be inserted in the dispatch pipeline after `DispatchHookStage` and before the tool body. When the descriptor's `authorize is None`, the stage SHALL self-skip. Otherwise the stage SHALL resolve the `authorize` callable's parameters through the active `call_scope` (same path as tool-body resolution) and invoke it. A falsy return SHALL raise `AuthorizationDenied(reason: str, callable_name: str)`. The error SHALL map to HTTP 403 on FastAPI and to the MCP error envelope via `McpErrorRenderStage`.

#### Scenario: authorize gate denies on both substrates

- **GIVEN** `@app.read(authorize=lambda *, principal: "admin" in principal.scopes) async def admin_op(...): ...`
- **WHEN** invoked on either substrate by a principal without the `admin` scope
- **THEN** HTTP returns 403 / MCP returns the documented error envelope
- **AND** the tool body is never invoked
