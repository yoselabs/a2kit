# Tasks — add-surface-protocol

> Tier 1, depends on `extract-tool-descriptor-projection` and `bridge-di-to-substrate-native`. Unblocks `unify-signature-installers`.

## 1. `Surface` Protocol + Template + Registry

- [ ] 1.1 New module `src/a2kit/packages/dispatch/surface.py`. Layer: L4 (dispatch).
- [ ] 1.2 Define `Surface` Protocol (runtime_checkable) with: `name: ClassVar[str]`, `reserved_types: ClassVar[frozenset[type]]`, `substrate_dep_markers: ClassVar[frozenset[type]]`, `def bind(runtime, descriptors) -> Any`, `def install_di_bridge(runtime, substrate_app) -> None`.
- [ ] 1.3 Define generic `DecoratorSurface[R]` Template (R = registration dataclass). Owns `registrations: tuple[R, ...]`, `_decorator`/`_wrap` skeletons. Subclasses specify the registration type + per-verb method names.
- [ ] 1.4 Define `SurfaceRegistry` — ordered dict keyed by surface name. Public methods: `register_surface(s)`, `names()`, `get(name)`. Single module-level instance `SURFACE_REGISTRY`.
- [ ] 1.5 BDD: `tests/packages/dispatch/test_surface_protocol.py` — Protocol satisfaction tests, registry add/lookup, name conflict raises.

## 2. Migrate `McpSurface` to satisfy Protocol

- [ ] 2.1 `packages/mcp/surface.py:McpSurface` → `class McpSurface(DecoratorSurface[McpRegistration]): name = "mcp"; reserved_types = frozenset({Context}); substrate_dep_markers = frozenset()`.
- [ ] 2.2 Implement `bind(runtime, descriptors)` — moves the body of `build_mcp_server` (today in `packages/mcp/server.py`) into `McpSurface.bind`.
- [ ] 2.3 Implement `install_di_bridge(runtime, server)` — wires FastMCP `Context.principal` extraction middleware to write `Principal` into `call_scope`.
- [ ] 2.4 At `packages/mcp/__init__.py` lazy load, register: `SURFACE_REGISTRY.register_surface(McpSurface())`.
- [ ] 2.5 Old `build_mcp_server` becomes a thin shim calling `McpSurface().bind(...)`. (Or removed if no external callers — check; if removed, breaking change in spec deltas.)

## 3. Migrate `ApiSurface` to satisfy Protocol

- [ ] 3.1 `packages/http/api.py:ApiSurface` → `class ApiSurface(DecoratorSurface[ApiRoute]): name = "api"; reserved_types = frozenset({Request, Response, BackgroundTasks, WebSocket}); substrate_dep_markers = frozenset({fastapi.params.Depends, fastapi.params.Security})`.
- [ ] 3.2 Implement `bind(runtime, descriptors)` — absorbs `build_http_app` body.
- [ ] 3.3 Implement `install_di_bridge(runtime, fastapi_app)` — wires `Container.expose_as_fastapi_depends()` into `fastapi_app.dependency_overrides`.
- [ ] 3.4 At `packages/http/__init__.py` lazy load, register `SURFACE_REGISTRY.register_surface(ApiSurface())`.
- [ ] 3.5 `build_http_app` becomes a thin shim or is removed (decide; if removed, breaking change with migration hint).

## 4. Remove `Substrate = Literal[...]` discriminator

- [ ] 4.1 `packages/dispatch/substrate.py`: `Substrate` retired. Replace with runtime `SurfaceName = str` validated against `SURFACE_REGISTRY.names()`.
- [ ] 4.2 `split_signature` and `install_substrate_signature` take a `Surface` object instead of a `Substrate` string; consume `surface.reserved_types` and `surface.substrate_dep_markers` directly. No string discrimination.
- [ ] 4.3 `tool.py:ToolDescriptor.expose: tuple[str, ...]` (was `tuple[Literal["mcp", "api"], ...]`). Validated against registry at `_build_descriptors` time.
- [ ] 4.4 `_verbs.py:_validate_expose` queries `SURFACE_REGISTRY.names()` instead of hardcoded frozenset.
- [ ] 4.5 Migration hints: any code import of `Substrate` from `packages/dispatch/substrate.py` raises with hint pointing to `Surface`.

## 5. `build_parent_app` auto-mount via registry

- [ ] 5.1 `packages/serve.py:build_parent_app` walks `SURFACE_REGISTRY` instead of hardcoded `_has_api_registrations`/`_has_mcp_registrations`.
- [ ] 5.2 For each surface with non-empty registrations for this runtime: call `surface.bind(runtime, descriptors)`; mount at `/{surface.name}`.
- [ ] 5.3 Delete `_has_api_registrations`, `_has_mcp_registrations`.
- [ ] 5.4 BDD: `tests/packages/test_serve.py` — adding a third surface (test-only `TestSurface`) is mounted at `/test` without serve-side edits.

## 6. `A2K-SURFACE-REGISTRY` lint rule

- [ ] 6.1 AST rule: any new module under `packages/` that defines a class subclassing `Surface` Protocol must also have a `SURFACE_REGISTRY.register_surface(...)` call in its enclosing package's `__init__.py` lazy load.
- [ ] 6.2 Detection: cross-file static check — if a `Surface` subclass exists but no registry call references it.
- [ ] 6.3 Rule test.

## 7. Spec deltas

- [ ] 7.1 New spec `openspec/specs/surface-protocol/spec.md`.
- [ ] 7.2 Modify `openspec/specs/multi-surface-authoring/spec.md`: substrate string discriminator replaced by Surface Protocol; `expose` is open-set.
- [ ] 7.3 Modify `openspec/specs/http-surface/spec.md`: `ApiSurface` satisfies Surface; `build_http_app` is a thin shim.
- [ ] 7.4 Modify `openspec/specs/mcp-context-passthrough/spec.md` + `mcp-tool-annotations/spec.md`: same for MCP.
- [ ] 7.5 Modify `openspec/specs/module-layout-discipline/spec.md`: add `A2K-SURFACE-REGISTRY`.

## 8. Final gates

- [ ] 8.1 `make lint` / `make test` / `make component-map --check` all green.
- [ ] 8.2 Cold-start budget verified — Surface registration runs only when `App.api`/`App.mcp` accessed (existing back-doors per ADR 0020).
- [ ] 8.3 README updated: add a "Third substrate" section pointing at the Surface Protocol.
