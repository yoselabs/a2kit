## 1. Lifecycle move

- [ ] 1.1 Remove `_build_descriptors(router)` call from `App.add_router`.
- [ ] 1.2 Add `_materialize_all_descriptors(self)` to `App` (or equivalent) called from `App.build()` after the container is finalised. Walks `self._routers`, calls `_build_descriptors(router)` per router with container in scope, stores result on the resulting `AppRuntime`.
- [ ] 1.3 `App.tools()` SHALL raise `RuntimeError("App.tools() requires App.build()")` if invoked pre-build. Update any internal callers that relied on pre-build access.

## 2. Runtime read surface

- [ ] 2.1 `AppRuntime.descriptor_for(name: str) -> ToolDescriptor` — O(1) lookup by tool name; raises `KeyError(name)` on miss.
- [ ] 2.2 `AppRuntime.descriptors() -> tuple[ToolDescriptor, ...]` — frozen tuple in stable registration order.
- [ ] 2.3 Both methods are the canonical descriptor read surface for substrate adapters.

## 3. Container-dependent field population

- [ ] 3.1 In `_build_descriptors(router, container)`, compute `wire_param_names = frozenset(wire_input_params(fn, container)[0].keys())` per tool.
- [ ] 3.2 Compute `lazy_param_names = frozenset(name for name, ann in resolve_hints(fn).items() if lazy_inner_type(ann) is not None)`.
- [ ] 3.3 Pass these into the `ToolDescriptor(...)` constructor instead of leaving them `None`.

## 4. Substrate adapter cutover

- [ ] 4.1 `packages/mcp/server.py:83` — replace direct `wire_input_params(fn, container)` call with `runtime.descriptor_for(name).wire_param_names`.
- [ ] 4.2 `packages/http/build.py:73` — same pattern; `_force_body_binding_for_wire_params` reads from descriptor.
- [ ] 4.3 `packages/cli/builder.py` — same pattern at all sites that currently re-derive wire shape.
- [ ] 4.4 `packages/codemode/marshal.py` and `codemode/stubs.py` — same.

## 5. BDD test

- [ ] 5.1 `tests/test_descriptor_materialization_lifecycle.py`: GIVEN an App with a router whose tool takes `db: Database` (container-known) and `id: str` (wire), WHEN `App.build()` runs, THEN `runtime.descriptor_for("fetch").wire_param_names == frozenset({"id"})`.
- [ ] 5.2 GIVEN the same App, WHEN `app.tools()` is called BEFORE `build()`, THEN `RuntimeError` is raised.
- [ ] 5.3 GIVEN a tool with `cache: Lazy[Cache]`, THEN `wire_param_names` excludes `cache` and `lazy_param_names == frozenset({"cache"})`.

## 6. Spec sync

- [ ] 6.1 Modify `openspec/specs/tool-descriptors/spec.md`: add Requirement for build-time materialization, container-aware `wire_param_names`/`lazy_param_names`, finalize the field defaults from [[extend-descriptor-fields]].
- [ ] 6.2 Modify `openspec/specs/app-runtime/spec.md` (or create if absent): add Requirement for `AppRuntime.descriptor_for` / `descriptors`.

## 7. Verification

- [ ] 7.1 `openspec validate --strict defer-descriptor-materialization` passes.
- [ ] 7.2 `make test` green — full suite, no skips. Substrate tests that re-derived wire shape still pass via descriptor read.
- [ ] 7.3 `make lint` green.
