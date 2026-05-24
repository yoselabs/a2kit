# Tasks — remove-substrate-literal

> Tier 1, BREAKING. Depends on `add-surface-protocol-additive`.
> Unblocks `unify-signature-installers`.

## 1. Retire `Substrate = Literal[...]` discriminator

- [ ] 1.1 `packages/dispatch/substrate.py`: remove `Substrate` Literal. Add a module `__getattr__` that raises with a hint pointing to `Surface` on `Substrate` access.
- [ ] 1.2 Migrate `_FASTAPI_RESERVED_SPECS` / `_FASTMCP_RESERVED_SPECS` to be class attributes on each Surface implementation (`ApiSurface.reserved_types`, `McpSurface.reserved_types`) — confirm parity with the additive change.
- [ ] 1.3 `split_signature(fn, surface, container)` — second arg is a `Surface` object, not a string. Reads `surface.reserved_types` and `surface.substrate_dep_markers` directly.
- [ ] 1.4 `install_substrate_signature(fn, surface, container)` — same change.
- [ ] 1.5 Update all call sites of `split_signature` / `install_substrate_signature` to pass a Surface object (typically `SURFACE_REGISTRY.get("api")` / `get("mcp")`).

## 2. Open-set `expose`

- [ ] 2.1 `packages/tool.py:ToolDescriptor.expose: tuple[str, ...]` (was `tuple[Literal["mcp","api"], ...]`).
- [ ] 2.2 `packages/_verbs.py:_validate_expose` queries `SURFACE_REGISTRY.names()` instead of a hardcoded frozenset; error names the unknown surface and lists registered names.
- [ ] 2.3 `app.py:_build_descriptors`: validates `expose=` against the registry at build time.
- [ ] 2.4 BDD: unknown `expose=("mcp","graphql")` raises at build with the list of registered surfaces.

## 3. `build_parent_app` registry walk

- [ ] 3.1 `packages/serve.py:build_parent_app` walks `SURFACE_REGISTRY` instead of hardcoded checks.
- [ ] 3.2 For each surface with non-empty registrations on the runtime: call `surface.bind(runtime, descriptors)`; mount at `/{surface.name}`.
- [ ] 3.3 Delete `_has_api_registrations`, `_has_mcp_registrations`.
- [ ] 3.4 BDD: a test-only `TestSurface(DecoratorSurface[TestReg])` registered with `SURFACE_REGISTRY.register_surface(TestSurface())` and a tool exposed on `"test"` auto-mounts at `/test` without serve-side edits.

## 4. `A2K-SURFACE-REGISTRY` lint rule

- [ ] 4.1 AST rule: any module under `src/a2kit/packages/` defining a class satisfying `Surface` Protocol must also have a `SURFACE_REGISTRY.register_surface(...)` call in its enclosing package's `__init__.py` lazy load.
- [ ] 4.2 Detection: cross-file static check — if a `Surface` subclass exists but no registry call references it.
- [ ] 4.3 Rule test.

## 5. Test churn

- [ ] 5.1 Sweep tests parametrizing over `Substrate` / `"fastapi"` / `"fastmcp"` strings; convert to parametrize over `SURFACE_REGISTRY.names()` or pass Surface objects directly.
- [ ] 5.2 `test_substrate_reserved_allowlist.py` becomes a per-Surface assertion.
- [ ] 5.3 Update `test_pipeline.py` / any other stage tests whose signature touches `Substrate`.

## 6. Spec deltas

- [ ] 6.1 Modify `openspec/specs/multi-surface-authoring/spec.md`: `expose` open-set, validated against registry; Substrate Literal removed.
- [ ] 6.2 Modify `openspec/specs/surface-protocol/spec.md`: add registry-walk auto-mount requirement + open-set `expose` requirement.
- [ ] 6.3 Modify `openspec/specs/module-layout-discipline/spec.md`: add `A2K-SURFACE-REGISTRY`.

## 7. Final gates

- [ ] 7.1 `make lint` / `make test` / `make component-map --check` all green.
- [ ] 7.2 `grep -RE 'Substrate\b' src/a2kit/` returns no production matches (test files allowed during sweep, then zeroed).
- [ ] 7.3 README "Third substrate" section added pointing at the Surface Protocol.
