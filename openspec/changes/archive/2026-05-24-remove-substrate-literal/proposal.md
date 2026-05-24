## Why

Split #2 of the umbrella `add-surface-protocol`. The additive half
(`add-surface-protocol-additive`) introduced the `Surface` Protocol,
template, and registry without touching the string discriminator.
This change rips it out: `Substrate = Literal["fastapi", "fastmcp"]`
goes away, `expose` becomes an open set validated against the
registry, signature splitting consumes Surface attributes directly,
and `build_parent_app` walks the registry instead of hardcoded
`_has_api_registrations` / `_has_mcp_registrations`.

This is the BREAKING half. It deliberately ships after the additive
half so the Protocol shape has already been validated against real
implementations, and so the ~30 test sites that parametrize over the
Literal churn in a single change with a clear blast radius.

## What Changes

- **BREAKING**: `Substrate = Literal["fastapi", "fastmcp"]` removed from `packages/dispatch/substrate.py`. Replaced by runtime `SurfaceName = str` validated against `SURFACE_REGISTRY.names()`. Direct import raises with a hint pointing to `Surface`.
- **BREAKING**: `ToolDescriptor.expose: tuple[str, ...]` (was `tuple[Literal["mcp", "api"], ...]`). Validated against the registry at descriptor-build time; unknown names raise with the list of registered surfaces.
- **BREAKING**: `split_signature` and `install_substrate_signature` take a `Surface` object instead of a `Substrate` string; consume `surface.reserved_types` and `surface.substrate_dep_markers` directly. The hardcoded `_FASTAPI_RESERVED_SPECS` / `_FASTMCP_RESERVED_SPECS` frozensets migrate to be class attributes on each Surface implementation.
- **BREAKING**: `_verbs.py:_validate_expose` queries `SURFACE_REGISTRY.names()` instead of a hardcoded frozenset.
- `packages/serve.py:build_parent_app` walks `SURFACE_REGISTRY` instead of hardcoded `_has_api_registrations`/`_has_mcp_registrations`. For each surface with non-empty registrations: call `surface.bind(runtime, descriptors)`; mount at `/{surface.name}`. The `_has_*` helpers are deleted.
- New lint rule `A2K-SURFACE-REGISTRY`: any module under `src/a2kit/packages/` that defines a class satisfying the `Surface` Protocol SHALL also register it via `SURFACE_REGISTRY.register_surface(...)` in its enclosing package's `__init__.py` lazy load. Cross-file AST check.

## Capabilities

### Modified Capabilities

- `multi-surface-authoring`: `expose` is open-set, validated against the registry; Substrate Literal is gone.
- `surface-protocol`: adds the registry-walk auto-mount requirement and the open-set `expose` requirement.
- `module-layout-discipline`: adds the `A2K-SURFACE-REGISTRY` lint rule.

## Impact

- **Depends on** `add-surface-protocol-additive` (Surface/Template/Registry must exist; both surfaces must already satisfy the Protocol).
- `packages/dispatch/substrate.py`: `Substrate`, `_FASTAPI_RESERVED_SPECS`, `_FASTMCP_RESERVED_SPECS` removed/relocated. `split_signature` / `install_substrate_signature` signature changes.
- `packages/serve.py`: `_has_api_registrations` / `_has_mcp_registrations` deleted; replaced by registry walk.
- `packages/tool.py`: `expose` type annotation widens to `tuple[str, ...]`.
- `app.py:_build_descriptors`: validates `expose=` against `SURFACE_REGISTRY.names()`.
- ~30 test sites: parametrize over `SURFACE_REGISTRY.names()` instead of the hardcoded literal; per-substrate signature-classifier tests rewrite as per-Surface assertions; `test_substrate_reserved_allowlist.py` becomes per-Surface.
- Migration hint: any code import of `Substrate` raises with hint pointing to `Surface`.
- Test added: `tests/packages/test_serve.py` — a test-only `TestSurface` registered via `SURFACE_REGISTRY.register_surface(...)` auto-mounts at `/test` without serve-side edits.
- Test added for `A2K-SURFACE-REGISTRY` rule.
- Unblocks `unify-signature-installers` (signature splitter consumes surface attributes uniformly).
