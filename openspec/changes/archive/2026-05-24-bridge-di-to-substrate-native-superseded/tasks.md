# Tasks — bridge-di-to-substrate-native

> Tier 1, depends on `extract-tool-descriptor-projection`. Unblocks `add-surface-protocol`, `unify-signature-installers`, `add-auth`.

## 1. `Principal` type

- [ ] 1.1 Define `Principal` in `src/a2kit/packages/context/principal.py`: frozen dataclass `{subject: str, scopes: frozenset[str], claims: Mapping[str, Any], issued_by: str, raw_token: str | None}`. `raw_token` is opaque — bridge doesn't parse it.
- [ ] 1.2 Re-export `Principal` from `a2kit.packages.context` front door.
- [ ] 1.3 Public re-export at `a2kit.Principal` via lazy `__getattr__`. Cold-start budget verified.
- [ ] 1.4 BDD: `tests/packages/context/test_principal.py` — frozen invariant, no mutation, equality semantics.

## 2. `substrate-dep` 4th signature class

- [ ] 2.1 Extend `SplitSignature` dataclass in `packages/dispatch/substrate.py` with a fourth field `substrate_dep: tuple[inspect.Parameter, ...]`.
- [ ] 2.2 `split_signature` learns to classify params with `Annotated[T, fastapi.params.Depends|Security]` annotations into the new bucket when `surface_dep_markers` is non-empty.
- [ ] 2.3 `surface_dep_markers` initially comes from a closed lookup keyed by current substrate string (will be replaced by `Surface.substrate_dep_markers` once `add-surface-protocol` lands).
- [ ] 2.4 When `substrate-dep` params exist on an MCP-target wrapper, raise `SubstrateSignatureError("FastAPI Depends/Security cannot appear on MCP-exposed tools; remove the marker or scope this tool with expose=('api',)")`.
- [ ] 2.5 BDD: `tests/packages/dispatch/test_substrate_dep_classification.py` — covers FastAPI Depends (passthrough), FastAPI Security (passthrough), Annotated-with-non-marker (still wire), MCP-reject path.

## 3. Container ↔ FastAPI Depends bridge

- [ ] 3.1 Add `Container.expose_as_fastapi_depends(type_: type) -> Callable[..., Any]` returning a FastAPI-compatible `Depends`-callable. Generated callable reads `_a2kit_scope` contextvar and calls `scope.get(type_)`. If no active scope: raise `RuntimeError("a2kit Depends resolver called outside call_scope")`.
- [ ] 3.2 Cache the generated callables per type on the container (`_fastapi_depends_cache: dict[type, Callable]`).
- [ ] 3.3 In `packages/http/build.py:build_http_app`: for every container-known type referenced by any descriptor's `wire_param_names` or `substrate_dep` chains, register an entry in `fastapi_app.dependency_overrides`.
- [ ] 3.4 BDD: `tests/packages/http/test_di_bridge.py` — a FastAPI `Security` guard `def guard(*, principal: Principal, db: Database)` resolves both. Concurrent requests get isolated scopes.

## 4. Principal propagation as SCOPED provider

- [ ] 4.1 Inside `install_substrate_signature._wrapper` (substrate.py:353): after entering `call_scope`, if the substrate produced a `Principal` (via reserved-param resolution or middleware), write it: `scope.provide(Principal, lambda: principal_value, scope=Scope.SCOPED)`. Idempotent within the call.
- [ ] 4.2 `packages/mcp/` middleware reads FastMCP `Context.principal` (or framework-equivalent — pin exact attr in `design.md`) and writes it the same way.
- [ ] 4.3 Document the SCOPED-write idiom inline.
- [ ] 4.4 BDD: `tests/test_principal_propagation.py` — tool body taking `principal: Principal` resolves both on MCP and HTTP.

## 5. `AuthorizeGateStage`

- [ ] 5.1 New stage `packages/dispatch/stages.py:AuthorizeGateStage` — self-skips when descriptor `authorize is None`.
- [ ] 5.2 When `authorize` is set: introspect the callable via `signature.resolve_hints`, resolve its params through `call_scope` (same path as tool-body resolution), invoke. Falsy return raises `AuthorizationDenied(reason: str, callable_name: str)`.
- [ ] 5.3 `AuthorizationDenied` mapped to: HTTP 403 by FastAPI error handler; MCP error-envelope by `McpErrorRenderStage`.
- [ ] 5.4 Insert `AuthorizeGateStage` in `DISPATCH_PIPELINE` after `DispatchHookStage` (DI is resolved), before tool body.
- [ ] 5.5 BDD: `tests/packages/dispatch/test_authorize_gate.py` — tool with `authorize=` taking deps gates correctly on both substrates; denial maps to right status.

## 6. `A2K-SUBSTRATE-DEP` lint rule

- [ ] 6.1 New AST rule: scan tool functions; if `Annotated[T, fastapi.Depends|Security]` annotation appears AND the function's effective `expose` includes `"mcp"`: hard error.
- [ ] 6.2 Allowlist exemption for explicit `expose=("api",)`.
- [ ] 6.3 Rule test in `tests/packages/lint/rules/test_substrate_dep.py`.

## 7. Discharge ADR 0020 `dependency_overrides` gap

- [ ] 7.1 Update ADR 0020: add a supersedence note for the "`dependency_overrides[T]` no-op" clause. Bridge makes it work properly.
- [ ] 7.2 Update `tests/packages/http/test_dependency_override.py` (currently asserts the gap exists) to assert the bridge resolves.
- [ ] 7.3 Update README "Multi-surface authoring" section: remove the warning about FastAPI deps not seeing a2kit types.

## 8. Spec deltas

- [ ] 8.1 New spec `openspec/specs/di-substrate-bridge/spec.md`.
- [ ] 8.2 New spec `openspec/specs/principal-propagation/spec.md`.
- [ ] 8.3 Modify `openspec/specs/di-container-package/spec.md`: add `expose_as_fastapi_depends` + SCOPED-write surface.
- [ ] 8.4 Modify `openspec/specs/request-scoped-di/spec.md`: `Principal` is a SCOPED provider when present.
- [ ] 8.5 Modify `openspec/specs/http-surface/spec.md`: bridge wired in `build_http_app`.
- [ ] 8.6 Modify `openspec/specs/multi-surface-authoring/spec.md`: signature splitter has 4 classes; ADR 0020 `dependency_overrides` clause superseded.

## 9. Final gates

- [ ] 9.1 `make lint` green; `make test` green.
- [ ] 9.2 Cold-start budget unaffected (FastAPI still lazy via `packages/http/__init__.py` PEP 562).
- [ ] 9.3 ADR 0020 amendment committed; cross-link from this change's archive entry.
