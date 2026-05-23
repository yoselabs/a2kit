## Why

Today the signature splitter in `packages/dispatch/substrate.py` has three classes: substrate-reserved, container-resolved, and wire. A parameter typed `Annotated[T, fastapi.Depends(...)]` falls through to `wire`, which breaks FastAPI's introspection: the marker is silently ignored and the param is generated into the wrapper's wire signature, then FastAPI fails to bind the route.

This change introduces the missing 4th class so FastAPI `Depends` / `Security` markers pass through to FastAPI's `__signature__` (where FastAPI's own dependency graph can walk them) while the rest of a2kit's classification stays untouched. The lint rule lands in the same cycle so the MCP-target reject path is statically enforceable, not just a runtime `SubstrateSignatureError`.

Carved out of the [[bridge-di-to-substrate-native]] umbrella as a single-cycle change. It does not yet wire FastAPI's `dependency_overrides` (that's [[bridge-container-fastapi-depends]]); it only teaches the splitter to recognise and route the markers.

## What Changes

- EXTEND `SplitSignature` (`packages/dispatch/substrate.py`) with a fourth field `substrate_dep: tuple[inspect.Parameter, ...]`.
- TEACH `split_signature` to classify any parameter whose `Annotated[...]` metadata contains a `fastapi.params.Depends` or `fastapi.params.Security` instance into the new bucket. Detection MUST be lazy: only import `fastapi.params` when a candidate annotation is observed; never at module load.
- WHEN a substrate-dep param appears on an MCP-target wrapper, RAISE `SubstrateSignatureError("FastAPI Depends/Security cannot appear on MCP-exposed tools; remove the marker or scope this tool with expose=('api',)")` from `install_substrate_signature` with `substrate="fastmcp"`.
- WIRE the substrate-dep params into FastAPI's `__signature__` passthrough (their `Annotated` metadata is preserved unchanged so FastAPI sees its own marker).
- ADD lint rule `A2K-SUBSTRATE-DEP`: AST-scan tool functions; if `Annotated[T, fastapi.params.Depends|Security]` appears on any parameter AND the function's effective `expose` includes `"mcp"`, hard-fail with the documented hint. Tools explicitly scoped `expose=("api",)` are exempt.

## Impact

- Affected specs: NEW `substrate-dep-class` capability; MODIFIED `module-layout-discipline` (new lint rule).
- Affected code: `packages/dispatch/substrate.py` (splitter + install_substrate_signature); `packages/lint/rules/substrate_dep.py` (new); `packages/lint/static.py` (registry).
- Breaking: silently-broken `Depends`-on-tool path now raises with a clear hint. Any author who was getting away with it because they happened to be api-only by coincidence still works; mcp-exposed cases now fail loudly.
- Depends on: none (independent of [[add-principal-type]]).
- Unblocks: [[bridge-container-fastapi-depends]], [[propagate-principal-and-authorize]].
