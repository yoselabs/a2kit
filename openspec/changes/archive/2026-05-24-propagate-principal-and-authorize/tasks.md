## 1. BDD first

- [x] 1.1 `tests/test_principal_propagation.py`: tool body taking `principal: Principal` resolves it on both substrates (HTTP via the FastAPI bridge, MCP via the middleware) given a single authenticated subject `"u1"`.
- [x] 1.2 `tests/packages/dispatch/test_authorize_gate.py`: tool with `authorize=lambda *, principal: "admin" in principal.scopes` denies a non-admin principal on both substrates; HTTP returns 403, MCP returns the documented error envelope; tool body is never invoked on denial.

## 2. SCOPED Principal write

- [x] 2.1 Inside `install_substrate_signature._wrapper` (`packages/dispatch/substrate.py`): after `call_scope` enters, if a `Principal` instance was produced by reserved-param resolution, register it as a SCOPED provider. Idempotent within the call (provider replaces silently if already set).
- [x] 2.2 Document the SCOPED-write idiom inline (one short comment, just the why).

## 3. MCP middleware

- [x] 3.1 New `src/a2kit/packages/mcp/principal_middleware.py`: reads `Context.principal` (verify exact attr at impl time against current `fastmcp`) and writes the SCOPED `Principal` provider into `call_scope`.
- [x] 3.2 Mount the middleware during MCP server build in `packages/mcp/server.py`.

## 4. `AuthorizeGateStage`

- [x] 4.1 New stage `packages/dispatch/stages.py:AuthorizeGateStage`. Self-skips when `descriptor.authorize is None`.
- [x] 4.2 When `authorize` is set: introspect the callable via `signature.resolve_hints`, resolve its params through `call_scope`, invoke. Falsy return raises `AuthorizationDenied(reason: str, callable_name: str)`.
- [x] 4.3 Insert `AuthorizeGateStage` in `DISPATCH_PIPELINE` after `DispatchHookStage`, before tool body.
- [x] 4.4 Add `AuthorizationDenied` exception class to `a2kit.exceptions`.

## 5. Denial mapping

- [x] 5.1 FastAPI: register an exception handler for `AuthorizationDenied` that returns 403 with `{"error": "authorization_denied", "reason": ..., "callable": ...}`.
- [x] 5.2 MCP: `McpErrorRenderStage` recognises `AuthorizationDenied` and emits the documented error envelope.

## 6. Spec sync

- [x] 6.1 New spec `openspec/specs/principal-propagation/spec.md`.
- [x] 6.2 Modify `openspec/specs/request-scoped-di/spec.md`: `Principal` SCOPED-provider clause.
- [x] 6.3 Modify `openspec/specs/dispatch-pipeline/spec.md`: `AuthorizeGateStage` placement.

## 7. Final gates

- [x] 7.1 `openspec validate --strict propagate-principal-and-authorize` passes.
- [x] 7.2 `make lint` green.
- [x] 7.3 `make test` green.
- [x] 7.4 Cold-start budget unaffected.
