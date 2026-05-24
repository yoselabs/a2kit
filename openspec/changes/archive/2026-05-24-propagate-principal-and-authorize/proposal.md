## Why

With [[add-principal-type]] giving us a substrate-neutral `Principal`, [[add-substrate-dep-class]] giving us the 4th signature class, and [[bridge-container-fastapi-depends]] letting FastAPI consume a2kit DI, the last gap is making `Principal` itself flow into the same DI machinery and gating tool dispatch on the `authorize=` callable. Today:

- Substrate-resolved `Principal` (from FastAPI `Security(...)` output or from FastMCP `Context.principal`) never reaches `call_scope`, so a tool body or `authorize` callable that takes `principal: Principal` can't resolve it.
- The dispatch pipeline has no authorize-gate stage; `descriptor.authorize` is carried on the descriptor but never invoked.

This change makes both work: the substrate adapter writes the resolved `Principal` into the active scope as a SCOPED provider, an MCP middleware does the equivalent extraction from FastMCP `Context`, and a new `AuthorizeGateStage` resolves the gate via the same DI path used for tool bodies and short-circuits on a falsy return.

## What Changes

- WRITE `Principal` into the active scope as a SCOPED provider from inside `install_substrate_signature._wrapper` (`packages/dispatch/substrate.py`) after `call_scope` enters. When the substrate's reserved-param resolution or middleware produced a `Principal`, do `scope.provide(Principal, lambda: principal_value, scope=Scope.SCOPED)`. Idempotent within the call.
- ADD `packages/mcp/principal_middleware.py`: small middleware that reads FastMCP `Context.principal` (or the framework-equivalent attribute — pin in design notes during implementation) and writes the same SCOPED provider into `call_scope`. Mounted on the MCP server during build.
- ADD `packages/dispatch/stages.py:AuthorizeGateStage`. Self-skips when `descriptor.authorize is None`. Otherwise resolves the callable's params through `call_scope` (re-uses `signature.resolve_hints` + the container resolution path used by tool bodies), invokes, and raises `AuthorizationDenied(reason: str, callable_name: str)` on falsy return.
- INSERT `AuthorizeGateStage` in `DISPATCH_PIPELINE` after `DispatchHookStage` (so DI is resolved) and before the tool body.
- MAP `AuthorizationDenied` -> HTTP 403 on FastAPI; `McpErrorRenderStage` formats the MCP error envelope.

## Impact

- Affected specs: NEW `principal-propagation` capability (owns the SCOPED-write + authorize-gate requirements); MODIFIED `request-scoped-di` (mentions `Principal` as scoped when present); MODIFIED `dispatch-pipeline` (new stage).
- Affected code: `packages/dispatch/substrate.py` (SCOPED write inside wrapper); `packages/dispatch/stages.py` (new stage); `packages/dispatch/__init__.py` (pipeline insertion); `packages/mcp/principal_middleware.py` (new); `packages/mcp/server.py` (mount middleware); `packages/http/build.py` (403 mapping for `AuthorizationDenied`).
- Breaking: an `authorize=` callable previously carried but un-enforced now actually gates. Authors who set `authorize=` expecting it to do something now get the behaviour; authors who set it as a no-op marker get gated unexpectedly. Document in changelog.
- Depends on: [[add-principal-type]], [[bridge-container-fastapi-depends]].
- Unblocks: [[add-auth]] (defines the wrappers that produce `Principal` instances).
