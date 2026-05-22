## 1. Snapshot-completeness gate

- [x] 1.1 Enumerate every piece of compose-phase state `build()` must carry into an `AppRuntime`: provider registrations, wire-scope registrations, the dispatch hook, the router registry and built descriptors, the LDD configuration, the health registry. Record each against the accessor that exposes it.
- [x] 1.2 Confirm `Container.providers_view()` plus the wire-scope accessors expose the full provider/scope state; document any gap and the accessor to add.
- [x] 1.3 Fix the `_verbs.py:373` function-local `import a2kit.metadata` to a module-level import (`metadata` is a verified leaf — the local import papers over nothing).

## 2. AppRuntime — failing tests first

- [x] 2.1 Write failing tests for the `AppRuntime` async-CM lifecycle per `app-lifecycle`: entry does not enter resources eagerly, LIFO exit unwind, lifespan-body force-resolve.
- [x] 2.2 Write a failing test for build-snapshot isolation: mutate the `App` after `build()`, assert the already-built `AppRuntime` is unaffected and a second `build()` includes the mutation.
- [x] 2.3 Write a failing test: `build()` runs graph validation and rejects a scope violation at build time (before any `AppRuntime` is produced).
- [x] 2.4 Migrate the six guard tests to the build-snapshot model — `tests/test_app.py::test_composition_after_sealing_raises` (5 parametrized verbs), `::test_finisher_seals_then_composition_raises`, `::test_seal_is_idempotent_app_reusable`, `::test_seal_validates_provider_graph`, `::test_no_post_seal_override_surface_on_container`, `tests/app/test_provide_unified.py::test_sealed_after_aenter`.
- [x] 2.5 Broader test-surface migration (scope discovered during apply — the design's "six guard tests" undercounted): ~30 test files enter the lifecycle via `async with app:` directly on the `App`. Migrate each to `async with build(app) as app:` (the `App` is no longer an async CM); migrate `app._resolver` / `app._seal()` / `async with app` real-wire double-enter sites accordingly.

## 3. AppRuntime implementation

- [x] 3.1 Create `src/a2kit/runtime.py` with `AppRuntime`, lifting the run-phase members out of `app.py`: `__aenter__`/`__aexit__`, the validated runtime container, dispatch wiring, lifecycle unwind.
- [x] 3.2 Implement the internal `build(app) -> AppRuntime`: snapshot registrations + wire-scopes into a fresh `Container`, run graph validation, return the runtime.
- [x] 3.3 Reduce `App` to compose-phase: remove `_sealed`, `_seal()`, `_ensure_not_sealed`, `__aenter__`/`__aexit__`; keep the compose container mutable and reusable.
- [x] 3.4 Route `a2kit.run`, `build_mcp_server`, and `a2kit.testing.client` through `build()`; preserve their public signatures.
- [x] 3.5 Confirm all tests from group 2 pass.

## 4. Core layer split

- [x] 4.1 Write a failing test asserting the layer manifest carries `kernel`/`authoring`/`runtime` sub-units and the facade exemption.
- [x] 4.2 Update `packages/lint/layers.py`: add `kernel`/`authoring`/`runtime` to `LAYER_MANIFEST`; teach `unit_for_module` and `unit_for_path` the top-level-module-to-sub-unit map.
- [x] 4.3 Extend the `A2K-LAYER` rule to enforce intra-core sub-unit edges and to honor the facade exemption.
- [x] 4.4 Run `uv run a2kit lint static src/`; resolve any flagged intra-core upward edge (convert papering function-local imports or correct the sub-unit assignment).
- [x] 4.5 Resolve the core-file-count open question (design.md): `runtime.py` adds one top-level file — either update the `module-layout-discipline` file-count requirement to defer to the layer manifest, or confirm the count stays within budget.

## 5. ADRs and docs

- [x] 5.1 Mark ADR 0017 (`docs/adr/0017-one-public-app.md`) superseded by the new ADR.
- [x] 5.2 Add a new ADR: the `App`/`AppRuntime` split under the layer-enforcement justification and the build-snapshot model; note ADR 0017's boundary-crossing reasoning still holds and the decision changed because a new force was added.
- [x] 5.3 Apply ADR 0018 (tombstone lifecycle) to the removed `_sealed` guard — or record why the whole-mechanism removal needs no tombstone.
- [x] 5.4 Regenerate `docs/adr/INDEX.md` (`make adr-index`).
- [x] 5.5 Update any `App` / lifecycle symbol references in `README.md` and `AGENTS.md` so the symbol-drift gate stays green.

## 6. Verification

- [x] 6.1 Full test suite green (`make test`).
- [x] 6.2 `uv run a2kit lint static src/` clean — no new `# noqa` suppressions.
- [x] 6.3 Cold-start budget intact — `import a2kit` under 100 ms; `AppRuntime` not pulled into `sys.modules` by `import a2kit`.
- [x] 6.4 `openspec validate --changes --strict` passes; the change is archive-ready.
