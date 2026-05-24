## Why

Split #1 of the umbrella `add-surface-protocol`. This half is purely
additive: introduce the `Surface` Protocol, `DecoratorSurface[R]`
template, and `SurfaceRegistry`; migrate `McpSurface` and `ApiSurface`
to extend the template; have each substrate package self-register.
The `Substrate = Literal["fastapi", "fastmcp"]` discriminator stays
intact, so this change ships independently with no breaking surface.

The breaking removal of the Literal lives in the sibling change
`remove-substrate-literal`, which depends on this one.

Splitting lets the additive half merge fast and exercises the Protocol
against the real implementations before we rip out the string
discriminator. If the Protocol shape proves wrong, we fix it before
~30 test sites churn on the Literal removal.

## What Changes

- **New `Surface` Protocol** in `packages/dispatch/surface.py` (new
  module, L4). Required attrs/methods: `name: ClassVar[str]`,
  `reserved_types: ClassVar[frozenset[type]]`,
  `substrate_dep_markers: ClassVar[frozenset[type]]`,
  `def bind(runtime, descriptors) -> Any`,
  `def install_di_bridge(runtime, substrate_app) -> None`.
- **Generic `DecoratorSurface[R]` Template** (R = registration
  dataclass type) absorbing the shared shape of `McpSurface` and
  `ApiSurface`: `registrations: tuple[R, ...]` accumulator,
  `_decorator`/`_wrap` skeletons.
- **`SurfaceRegistry`** — ordered registry keyed by surface name with
  `register_surface(s)`, `names()`, `get(name)`; one module-level
  `SURFACE_REGISTRY` instance.
- `McpSurface` extends `DecoratorSurface[McpRegistration]` and
  satisfies `Surface`. `name = "mcp"`,
  `reserved_types = frozenset({Context})`,
  `substrate_dep_markers = frozenset()`.
- `ApiSurface` extends `DecoratorSurface[ApiRoute]` and satisfies
  `Surface`. `name = "api"`,
  `reserved_types = frozenset({Request, Response, BackgroundTasks, WebSocket})`,
  `substrate_dep_markers = frozenset({fastapi.params.Depends, fastapi.params.Security})`.
- Each substrate package's lazy front door registers its surface with
  `SURFACE_REGISTRY` on first access.
- `build_mcp_server`/`build_http_app` remain the public callers; they
  call `McpSurface().bind(...)` / `ApiSurface().bind(...)` under the
  hood. (Pure refactor — same observable behaviour.)
- `Substrate` Literal **unchanged**. String discrimination at
  `install_substrate_signature` and `expose: Literal["mcp","api"]`
  unchanged. Those move in `remove-substrate-literal`.

## Capabilities

### New Capabilities

- `surface-protocol`: the `Surface` Protocol + `SurfaceRegistry` +
  `DecoratorSurface[R]` template. Defines what it means to be a
  substrate adapter and provides the only extension point.

### Modified Capabilities

- `http-surface`: `ApiSurface` extends `DecoratorSurface[ApiRoute]`
  and satisfies the Protocol; `build_http_app` body folded into
  `ApiSurface.bind`.
- `mcp-context-passthrough`: `McpSurface` extends
  `DecoratorSurface[McpRegistration]` and satisfies the Protocol;
  `build_mcp_server` body folded into `McpSurface.bind`.

## Impact

- New module `packages/dispatch/surface.py` (~200 LOC).
- `packages/http/api.py`, `packages/mcp/surface.py`: shrink as
  shared shape moves to the template.
- `packages/mcp/server.py`, `packages/http/build.py`: builders become
  thin shims over `surface.bind(...)`.
- `packages/dispatch/substrate.py`: no change. String discriminator
  remains.
- `packages/serve.py`: no change. `_has_api_registrations` /
  `_has_mcp_registrations` remain.
- Cold-start unaffected: surface modules stay lazy under the
  `packages/http/__init__.py` / `packages/mcp/__init__.py` PEP 562
  facades.
- Tests added: `tests/packages/dispatch/test_surface_protocol.py`
  (Protocol satisfaction, registry add/lookup, name conflict raises).
- Mirror tests for existing surface modules continue to pass without
  changes (no public behaviour change).
- Unblocks `remove-substrate-literal`.
