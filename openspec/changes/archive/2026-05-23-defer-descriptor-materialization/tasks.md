## 1. Build-time re-materialization

- [x] 1.1 In `runtime.build(app)`, after `runtime_container = app.container().snapshot(); runtime_container.seal()`, re-materialise descriptors against `runtime_container`. Replace the existing `app.tools()` line with `_build_descriptors_with_container(routers, runtime_container)`.
- [x] 1.2 Refactor `app._build_descriptors(router)` into `_build_descriptors(router, container=None)`. When `container` is `None`, leave `wire_param_names` / `lazy_param_names` as `None` (current behaviour). When supplied, populate them.
- [x] 1.3 `App.add_router` continues to call `_build_descriptors(router)` with no container (matches pre-existing semantics; pre-build access still works).

## 2. Runtime read surface

- [x] 2.1 `AppRuntime.descriptor_for(name: str) -> ToolDescriptor` — O(1) lookup by tool name; raises `KeyError(name)` on miss. Build the lookup dict once at `AppRuntime.__init__`.
- [x] 2.2 `AppRuntime.descriptors() -> tuple[ToolDescriptor, ...]` — frozen tuple in stable registration order.

## 3. Container-dependent field population

- [x] 3.1 In `_build_descriptors(router, container)`, compute `wire_param_names = frozenset(wire_input_params(fn, container)[0].keys())` per tool.
- [x] 3.2 Compute `lazy_param_names` via `resolve_hints(fn)` walk + `lazy_inner_type(ann) is not None`.
- [x] 3.3 Pass these into the `ToolDescriptor(...)` constructor.

## 4. BDD test

- [x] 4.1 `tests/test_descriptor_materialization_lifecycle.py`: GIVEN an App with a provider `Database` and a router whose tool takes `db: Database` and `id: str`, WHEN `build(app)` runs, THEN `runtime.descriptor_for("fetch").wire_param_names == frozenset({"id"})`.
- [x] 4.2 GIVEN the same App, WHEN `app.tools()[0]` is read BEFORE `build()`, THEN `descriptor.wire_param_names is None` (pre-build behaviour unchanged).
- [x] 4.3 GIVEN a tool with `cache: Lazy[Cache]`, THEN post-build `lazy_param_names == frozenset({"cache"})`.
- [x] 4.4 `runtime.descriptor_for("does_not_exist")` raises `KeyError`.

## 5. Spec sync

- [x] 5.1 Sync `openspec/changes/defer-descriptor-materialization/specs/tool-descriptors/spec.md` deltas into `openspec/specs/tool-descriptors/spec.md` at archive time.
- [x] 5.2 Sync `openspec/changes/defer-descriptor-materialization/specs/app-lifecycle/spec.md` deltas into `openspec/specs/app-lifecycle/spec.md` at archive time.

## 6. Verification

- [x] 6.1 `openspec validate --strict defer-descriptor-materialization` passes.
- [x] 6.2 `make test` green — full suite.
- [x] 6.3 `make lint` green.
