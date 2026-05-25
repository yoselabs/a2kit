# principal-propagation Specification

## Purpose

A substrate-neutral path for moving an authenticated `Principal` from
whichever substrate authenticated the request (FastAPI `Security` guard,
MCP `PrincipalMiddleware`) into the per-call DI scope, plus a dispatch
stage that gates the tool body on the descriptor's `authorize=` callable
resolved through the same DI path. Together these turn `Principal` into a
type-resolved injectable and make `authorize=` a load-bearing constraint
on dispatch rather than an unused field.

## Requirements
### Requirement: Principal is written into `call_scope` as SCOPED

The substrate adapter SHALL write the resolved `Principal` into the active call scope as a SCOPED provider before the tool body runs whenever a substrate produces a `Principal` for the request (via reserved-param resolution on FastAPI `Security` or via the MCP `PrincipalMiddleware`). Tool bodies and `authorize=` callables SHALL resolve `principal: Principal` by type annotation alone, without any explicit container registration by the author.

#### Scenario: Tool body resolves Principal via DI on both substrates

- **GIVEN** `@a2kit.read async def me(*, principal: Principal) -> dict: return {"subject": principal.subject}`
- **WHEN** invoked via HTTP and via MCP with the same authenticated subject `"u1"`
- **THEN** both invocations return `{"subject": "u1"}`
- **AND** no explicit container registration of `Principal` was performed by the author

### Requirement: `AuthorizeGateStage` resolves the gate via DI and short-circuits on falsy return

`packages/dispatch/stages.py:AuthorizeGateStage` SHALL be inserted in the
dispatch pipeline after `DispatchHookStage` and before the tool body.
When the descriptor's `authorize is None`, the stage SHALL self-skip.
Otherwise the stage SHALL resolve the `authorize` callable's parameters
through `call_scope` (same path as tool-body resolution) and invoke it.
A falsy return SHALL raise
`AuthorizationDenied(reason: str, callable_name: str)`. The error SHALL
map to HTTP 403 on FastAPI and to the documented MCP error envelope via
`McpErrorRenderStage`.

#### Scenario: authorize gate denies on both substrates

- **GIVEN** `@a2kit.read(authorize=lambda *, principal: "admin" in principal.scopes) async def admin_op(...): ...`
- **WHEN** invoked on either substrate by a principal without the `admin` scope
- **THEN** HTTP returns 403 with `{"error": "authorization_denied", ...}` / MCP returns the documented error envelope
- **AND** the tool body is never invoked

#### Scenario: authorize gate passes through

- **GIVEN** `@a2kit.read(authorize=lambda *, principal: "admin" in principal.scopes) async def admin_op(*, principal: Principal) -> dict: return {"subject": principal.subject}`
- **WHEN** invoked by a principal whose scopes include `"admin"`
- **THEN** the tool body runs and returns `{"subject": <principal.subject>}`

### Requirement: DI is the single source of truth for Principal

`Principal` SHALL be resolvable exclusively via the per-call DI scope. No dispatch-pipeline stage MAY read `Principal` from a contextvar (or any other ambient mechanism) as a fallback. Substrate adapters MUST write `Principal` into the per-call DI scope; how the substrate obtains it from the wire (header, OAuth token, OIDC claim) is the adapter's private concern.

#### Scenario: Tool body resolves Principal via DI override

- **GIVEN** an App with a DI provider registered for `Principal` returning a `fake_principal`
- **WHEN** a tool decorated `async def me(*, principal: Principal) -> Principal: return principal` is dispatched
- **THEN** the tool body receives `fake_principal`
- **AND** no contextvar was set or read during dispatch

#### Scenario: No provider, no substrate write — clear error

- **GIVEN** an App with no Principal provider and a synthetic dispatch path that does not write Principal into the scope
- **WHEN** a tool body declaring `principal: Principal` is dispatched
- **THEN** the dispatcher raises a clear "no provider for Principal" error
- **AND** the error does not silently fall back to a contextvar


