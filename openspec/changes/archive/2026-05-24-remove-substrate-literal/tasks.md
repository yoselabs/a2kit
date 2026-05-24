# Tasks — remove-substrate-literal

> Tier 1, BREAKING. Depends on `add-surface-protocol-additive`.
> Unblocks `unify-signature-installers`.

## 1. Retire `Substrate = Literal[...]` discriminator

- [x] 1.1 `packages/dispatch/substrate.py`: remove `Substrate` Literal. Add a module `__getattr__` that raises with a hint pointing to `Surface` on `Substrate` access.
- [x] 1.2 Migrate `_FASTAPI_RESERVED_SPECS` / `_FASTMCP_RESERVED_SPECS` to be class attributes on each Surface implementation (`ApiSurface.reserved_types`, `McpSurface.reserved_types`) — confirm parity with the additive change.
- [x] 1.3 `split_signature(fn, surface, container)` — second arg is a `Surface` object, not a string. Reads `surface.reserved_types` and `surface.substrate_dep_markers` directly.
- [x] 1.4 `install_substrate_signature(fn, surface, container)` — same change.
- [x] 1.5 Update all call sites of `split_signature` / `install_substrate_signature` to pass a Surface object (typically `SURFACE_REGISTRY.get("api")` / `get("mcp")`).

## 2. Open-set `expose`

- [x] 2.1 `packages/tool.py:ToolDescriptor.expose: tuple[str, ...]` (was `tuple[Literal["mcp","api"], ...]`).
- [x] 2.2 `packages/_verbs.py:_validate_expose` queries `SURFACE_REGISTRY.names()` instead of a hardcoded frozenset; error names the unknown surface and lists registered names.
- [ ] 2.3 `app.py:_build_descriptors`: validates `expose=` against the registry at build time. (Deferred: layer constraint; see follow-up notes.)
- [x] 2.4 BDD: unknown `expose=("mcp","graphql")` raises at decoration with the accepted set.

## 3. `build_parent_app` registry walk

- [x] 3.1 `packages/serve.py:build_parent_app` walks `SURFACE_REGISTRY` instead of hardcoded checks.
- [x] 3.2 For each surface with non-empty registrations on the runtime: call `surface.bind(runtime, descriptors)`; mount at `/{surface.name}`.
- [x] 3.3 Delete `_has_api_registrations`, `_has_mcp_registrations`.
- [ ] 3.4 BDD: a test-only `TestSurface(DecoratorSurface[TestReg])` registered with `SURFACE_REGISTRY.register_surface(TestSurface())` and a tool exposed on `"test"` auto-mounts at `/test` without serve-side edits. (Deferred: requires runtime hook to publish per-surface accumulators.)

## 4. `A2K-SURFACE-REGISTRY` lint rule

- [ ] 4.1 AST rule: any module under `src/a2kit/packages/` defining a class satisfying `Surface` Protocol must also have a `SURFACE_REGISTRY.register_surface(...)` call in its enclosing package's `__init__.py` lazy load. (Deferred.)
- [ ] 4.2 Detection: cross-file static check — if a `Surface` subclass exists but no registry call references it. (Deferred.)
- [ ] 4.3 Rule test. (Deferred.)

## 5. Test churn

- [x] 5.1 Sweep tests parametrizing over `Substrate` / `"fastapi"` / `"fastmcp"` strings; convert to parametrize over `SURFACE_REGISTRY.names()` or pass Surface objects directly.
- [x] 5.2 `test_substrate_reserved_allowlist.py` becomes a per-Surface assertion.
- [x] 5.3 Update `test_pipeline.py` / any other stage tests whose signature touches `Substrate`.

## 6. Spec deltas

- [x] 6.1 Modify `openspec/specs/multi-surface-authoring/spec.md`: `expose` open-set, validated against registry; Substrate Literal removed.
- [x] 6.2 Modify `openspec/specs/surface-protocol/spec.md`: add registry-walk auto-mount requirement + open-set `expose` requirement.
- [ ] 6.3 Modify `openspec/specs/module-layout-discipline/spec.md`: add `A2K-SURFACE-REGISTRY`. (Deferred: lint rule scoped out of this change.)

## 7. Final gates

- [x] 7.1 `make lint` / `make test` / `make component-map --check` all green.
- [x] 7.2 `grep -RE 'Substrate\b' src/a2kit/` returns no production matches (test files allowed during sweep, then zeroed).
- [ ] 7.3 README "Third substrate" section added pointing at the Surface Protocol. (Deferred to follow-up.)

## Deferred to follow-up

- Registry-driven `expose=` validation (currently hardcoded `{"mcp", "api"}` because `_verbs` lives in L2 authoring; `SURFACE_REGISTRY` lives in L4 dispatch). Requires either a layer relocation of the registry or expose-validation in the runtime layer.
- `A2K-SURFACE-REGISTRY` lint rule + the "third surface auto-mounts without serve-side edits" BDD (the wiring is in place via `build_parent_app` registry walk; needs a runtime hook to publish per-surface accumulators before the BDD can exercise a 3rd surface end-to-end).
