## Why

`_build_descriptors` currently runs inside `App.add_router(...)`, before the DI container is finalised. This means descriptors cannot carry container-dependent projections (`wire_param_names`, `lazy_param_names`) — substrate adapters must re-derive them per-call via `wire_input_params(fn, container)`. Every substrate (MCP server, HTTP build, CLI builder) pays this derivation cost on every dispatch, and the "single source of truth for tool shape" promise of `ToolDescriptor` is broken at the substrate boundary.

Deferring materialization to `App.build()` lets descriptors carry the container-aware projection, makes `runtime.descriptor_for(name)` the canonical read path for substrate adapters, and unblocks the container-dependent fields added in [[extend-descriptor-fields]].

## What Changes

- MOVE descriptor materialization: `_build_descriptors(router)` SHALL be invoked from `App.build()` (or the equivalent finishing step that produces `AppRuntime`), not from `App.add_router`. `add_router` stores the router; finalisation walks all routers and materialises descriptors against the now-known container.
- ADD `AppRuntime.descriptor_for(name) -> ToolDescriptor` and `AppRuntime.descriptors() -> tuple[ToolDescriptor, ...]` as the canonical descriptor read surface for substrate adapters.
- POPULATE container-dependent fields: `wire_param_names = frozenset(wire_input_params(fn, container)[0].keys())`, `lazy_param_names = frozenset(name for name, ann in resolve_hints(fn).items() if lazy_inner_type(ann) is not None)`.
- KEEP `App.tools()` working — it SHALL return the descriptors as built at the last `build()` call, raising a clear error if invoked before `build()`. (Pre-build access has no path that needs container-dependent fields.)
- UPDATE substrate adapters (`packages/mcp/server.py`, `packages/http/build.py`, `packages/cli/builder.py`, `packages/codemode/marshal.py`) to consume `runtime.descriptor_for(name).wire_param_names` / `.lazy_param_names` instead of calling `wire_input_params` themselves.

## Impact

- Affected specs: `tool-descriptors` (MODIFIED — materialization lifecycle), `app-runtime` (MODIFIED — new descriptor read surface)
- Affected code: `src/a2kit/app.py`, `src/a2kit/runtime.py`, `src/a2kit/packages/mcp/server.py`, `src/a2kit/packages/http/build.py`, `src/a2kit/packages/cli/builder.py`, `src/a2kit/packages/codemode/marshal.py`
- Breaking: YES (any external code reading `app.tools()` before `app.build()` now raises). Internal-only surface; acceptable per "no backward compat".
- Depends on: [[extend-descriptor-fields]] (descriptor field skeleton must exist first)
- Unblocks: [[bridge-di-to-substrate-native]], [[privatize-tool-metadata]]
