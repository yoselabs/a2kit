# Tasks — add-surface-protocol-additive

> Tier 1, additive. Depends on `extract-tool-descriptor-projection`
> and `bridge-di-to-substrate-native`. Unblocks
> `remove-substrate-literal`.

## 1. `Surface` Protocol + Template + Registry

- [x] 1.1 New module `src/a2kit/packages/dispatch/surface.py`. Layer: L4 (dispatch).
- [x] 1.2 Define `Surface` Protocol (runtime_checkable) with: `name: ClassVar[str]`, `reserved_types: ClassVar[frozenset[type]]`, `substrate_dep_markers: ClassVar[frozenset[type]]`, `def bind(runtime, descriptors) -> Any`, `def install_di_bridge(runtime, substrate_app) -> None`.
- [x] 1.3 Define generic `DecoratorSurface[R]` Template (R = registration dataclass). Owns `registrations: tuple[R, ...]`, `_decorator`/`_wrap` skeletons.
- [x] 1.4 Define `SurfaceRegistry` — ordered dict keyed by surface name. Public methods: `register_surface(s)`, `names()`, `get(name)`. Single module-level instance `SURFACE_REGISTRY`. Name conflict raises.
- [x] 1.5 Re-export `Surface`, `DecoratorSurface`, `SurfaceRegistry`, `SURFACE_REGISTRY` from `packages/dispatch/__init__.py`.
- [x] 1.6 BDD: `tests/packages/dispatch/test_surface_protocol.py` — Protocol satisfaction, registry add/lookup/names/get, name conflict raises.

## 2. Migrate `McpSurface` to extend Template + satisfy Protocol

- [x] 2.1 `packages/mcp/surface.py:McpSurface` → `class McpSurface(DecoratorSurface[McpRegistration]): name = "mcp"; reserved_types = frozenset({Context}); substrate_dep_markers = frozenset()`.
- [x] 2.2 Implement `bind(runtime, descriptors)` — move body of `build_mcp_server` (`packages/mcp/server.py`) here.
- [x] 2.3 Implement `install_di_bridge(runtime, server)` — wires `PrincipalMiddleware`.
- [x] 2.4 `build_mcp_server` becomes thin shim calling `McpSurface().bind(...)`. No behaviour change for callers.
- [x] 2.5 At `packages/mcp/__init__.py` lazy load, register `SURFACE_REGISTRY.register_surface(McpSurface())`.

## 3. Migrate `ApiSurface` to extend Template + satisfy Protocol

- [x] 3.1 `packages/http/api.py:ApiSurface` → `class ApiSurface(DecoratorSurface[ApiRoute]): name = "api"; reserved_types = frozenset({Request, Response, BackgroundTasks, WebSocket}); substrate_dep_markers = frozenset({fastapi.params.Depends, fastapi.params.Security})`.
- [x] 3.2 Implement `bind(runtime, descriptors)` — move body of `build_http_app` (`packages/http/build.py`) here.
- [x] 3.3 Implement `install_di_bridge(runtime, fastapi_app)` — wires `Container.expose_as_fastapi_depends()` into `dependency_overrides`.
- [x] 3.4 `build_http_app` becomes thin shim calling `ApiSurface().bind(...)`.
- [x] 3.5 At `packages/http/__init__.py` lazy load, register `SURFACE_REGISTRY.register_surface(ApiSurface())`.

## 4. Spec deltas

- [x] 4.1 New spec `openspec/specs/surface-protocol/spec.md`.
- [x] 4.2 Modify `openspec/specs/http-surface/spec.md`: `ApiSurface` satisfies Surface; `build_http_app` is a thin shim.
- [x] 4.3 Modify `openspec/specs/mcp-context-passthrough/spec.md`: same for MCP.

## 5. Final gates

- [x] 5.1 `make lint` / `make test` / `make component-map --check` all green.
- [x] 5.2 Cold-start budget verified — Surface registration runs only when `App.api`/`App.mcp` accessed (existing back-doors per ADR 0020).
- [x] 5.3 Substrate Literal **untouched**; no `Substrate` removal in this change.
