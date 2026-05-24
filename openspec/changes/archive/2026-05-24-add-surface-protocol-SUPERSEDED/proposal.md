## Why

`McpSurface` (`packages/mcp/surface.py:48`) and `ApiSurface` (`packages/http/api.py:48`) are 95% the same shape — a registration dataclass + a `_decorator` factory + a per-verb `_wrap`. Substrate-discrimination is hardcoded as `Substrate = Literal["fastapi", "fastmcp"]` at 10+ sites (`packages/dispatch/substrate.py:55`, allowlist frozensets at lines 121-127, validator at line 84, `expose: Literal["mcp", "api"]` at `tool.py:48`, etc.).

Two structural consequences:

1. **Adding a third substrate** (A2A, gRPC, AsyncAPI, GraphQL, or a thinner replacement when FastMCP absorbs more of our MCP surface) requires editing those ~10 hardcoded sites. The framework is not open to extension — it's open to forking the if-chain.
2. **The DI bridge** (`bridge-di-to-substrate-native`) needs a per-substrate place to hang the FastAPI `Depends` exposure / FastMCP principal extraction. Today that logic would land inside each substrate adapter as ad-hoc imports, with no protocol to enforce that future substrates wire it up.

Replace the two coexisting bespoke classes with one Protocol + a small registry. This is the framework's primary hedge against FastMCP encroachment: when FastMCP ships its own cross-transport story, we either drop our `fastmcp` Surface (it becomes a thin shim over theirs) or absorb a sibling — without touching cross-cutting code.

## What Changes

- **New `Surface` Protocol** in `packages/dispatch/surface.py` (new module, L4). Required methods:
  - `name: ClassVar[str]` (e.g. `"mcp"`, `"api"`, future `"a2a"`).
  - `reserved_types: ClassVar[frozenset[type]]` (e.g. `{Request, Response, BackgroundTasks, WebSocket}` for fastapi).
  - `substrate_dep_markers: ClassVar[frozenset[type]]` (e.g. `{fastapi.params.Depends, fastapi.params.Security}` for fastapi; empty frozenset for fastmcp).
  - `def bind(self, runtime: AppRuntime, descriptors: tuple[ToolDescriptor, ...]) -> SubstrateApp` — builds the substrate-native app (FastAPI instance / FastMCP server).
  - `def install_di_bridge(self, runtime: AppRuntime, substrate_app: Any) -> None` — wires the `bridge-di-to-substrate-native` mechanism for this substrate. Called by `bind` post-construction.
- **Generic `DecoratorSurface[R]` Template** in the same module (R = the registration dataclass type). Subsumes `McpSurface` and `ApiSurface`:
  - Owns the `registrations: tuple[R, ...]` accumulator.
  - Provides `_decorator(kind, **kwargs)` and `_wrap(fn, registration)` templates.
  - Subclasses specify only the registration dataclass + per-verb method names.
- **`SurfaceRegistry`** in `packages/dispatch/surface.py`: small ordered registry keyed by surface name. `register_surface(s: Surface)` is the extension point. Bundled surfaces (mcp, api) self-register on package import via the runtime extension hook.
- **BREAKING**: `Substrate = Literal["fastapi", "fastmcp"]` removed from `packages/dispatch/substrate.py`. Replaced by runtime `SurfaceName = str` validated against `SurfaceRegistry`. `expose: tuple[str, ...]` on descriptors; no `Literal` constraint. Unknown surface name raises at decoration time with hint pointing to `SurfaceRegistry.names()`.
- **BREAKING**: `McpSurface` and `ApiSurface` retired as standalone classes. Replaced by `McpSurface(DecoratorSurface[McpRegistration], Surface)` and `ApiSurface(DecoratorSurface[ApiRoute], Surface)` — both satisfying the Protocol. No third type alongside.
- **BREAKING**: substrate-name string discriminator `substrate == "fastapi"` checks in `install_substrate_signature` replaced with `surface.reserved_types` / `surface.substrate_dep_markers` lookups against the active Surface. No more hardcoded if-chain.
- **`build_parent_app` mounts every registered Surface that has registrations.** Auto-mount logic moves from hardcoded `_has_api_registrations` / `_has_mcp_registrations` to `for surface in registry: if runtime.has_registrations_for(surface.name): mount(surface.bind(runtime, descriptors))`.
- **Lint rule `A2K-SURFACE-REGISTRY`** (new): a new substrate module must register via `SurfaceRegistry`. A direct import-and-mount pattern bypassing the registry is a hard error.

## Capabilities

### New Capabilities

- `surface-protocol`: the `Surface` Protocol + `SurfaceRegistry` + `DecoratorSurface[R]` template. Defines what it means to be a substrate adapter and provides the only extension point.

### Modified Capabilities

- `multi-surface-authoring`: substrate adapters now satisfy `Surface` Protocol; `expose: tuple[str, ...]` is open-set validated against the registry, not a `Literal`.
- `http-surface`: `ApiSurface` extends `DecoratorSurface[ApiRoute]` + satisfies `Surface`; `build_http_app` becomes `ApiSurface.bind`.
- `mcp-context-passthrough` / `mcp-tool-annotations`: `McpSurface` extends `DecoratorSurface[McpRegistration]` + satisfies `Surface`; `build_mcp_server` becomes `McpSurface.bind`.
- `module-layout-discipline`: adds `A2K-SURFACE-REGISTRY` lint rule.

## Impact

- New module `packages/dispatch/surface.py` (~200 LOC: Protocol + Template + Registry).
- `packages/http/api.py` and `packages/mcp/surface.py`: each shrinks substantially (Template absorbs the shared shape).
- `packages/dispatch/substrate.py`: `_FASTAPI_RESERVED_SPECS` / `_FASTMCP_RESERVED_SPECS` migrate to be class attributes on each Surface implementation. Substrate-string discrimination eliminated.
- `packages/serve.py`: `_has_api_registrations` / `_has_mcp_registrations` replaced by registry walk.
- `app.py:_build_descriptors`: validates `expose=` against `SurfaceRegistry.names()` instead of a hardcoded allowlist.
- Depends on `extract-tool-descriptor-projection` (Surface.bind takes `tuple[ToolDescriptor, ...]`) and `bridge-di-to-substrate-native` (the `install_di_bridge` method exists because the bridge mechanism exists).
- Unblocks `unify-signature-installers` (signature splitter consumes surface-attributes uniformly, no per-substrate branches).
- Cold-start unaffected: surface modules remain lazy under `packages/http/__init__.py` and `packages/mcp/__init__.py` PEP 562 facades. Registry sits at L4 (dispatch); registration happens at the L5 substrate module import, triggered by `App.api` / `App.mcp` access (the existing ADR-0020 back doors).
- Test churn: per-substrate signature-classifier tests rewrite to parametrize over `SurfaceRegistry.names()`. `test_substrate_reserved_allowlist.py` becomes a per-Surface assertion. Estimated ~30 test sites.
