## Context

`a2kit.App` is a single class that fuses a compose phase (the `add_router` / `add_cli` / `add_mcp_middleware` / `provide` / `health_check` verbs) and a sealed run phase (the validated DI container, the dispatch pipeline, the `__aenter__` / `__aexit__` lifecycle). The two phases are toggled by a private `_sealed` flag set by the first finisher.

The layer manifest (ADR 0015, `packages/lint/layers.py`) tiers every importable unit. It treats all top-level `a2kit.*` modules as one `core` pseudo-unit — the only unit with no intra-unit enforcement. `app.py` straddles what would be two distinct layers, which is why `core` cannot be subdivided while `App` is one class.

ADR 0017 collapsed an earlier `AppBuilder` / `App` split, judging it unjustified because the sealed runtime never crosses the consumer boundary. That judgement was correct under the forces of the time. ADR 0015's layer manifest is a later force ADR 0017 never weighed.

A read-only investigation during the explore session confirmed: (1) the sealed runtime is touched only by framework-internal code under `packages/{cli,mcp,dispatch,serve,testing}` — no example or public API depends on it; (2) the proposed kernel / authoring / runtime cut of `core` is a clean DAG with zero back-edges.

## Goals / Non-Goals

**Goals:**

- `App` is a compose-phase-only type; the sealed runtime is a separate internal `AppRuntime`.
- The `core` unit becomes three lint-enforced sub-layers, so the densest code gains the same import-graph protection every package already has.
- Zero change to the consumer-facing surface: `App`, the verb decorators, and the three finishers keep their exact signatures.
- `App` becomes a pure, reusable builder — a finisher may be handed an `App` more than once.

**Non-Goals:**

- Splitting the DI `Container`. Investigated and dropped: `container.py` is ~90% irreducible run-phase code; extracting its three compose methods buys little.
- Capability registration (relocating per-capability code out of `app.py`). Separate downstream change.
- The `otel` / observability reshape. Separate change.
- Moving top-level modules into physical subdirectories. The sub-layers are a manifest concept; files stay flat in `src/a2kit/`.

## Decisions

**1. The internal type is named `AppRuntime`.**
Alternatives: `AppInstance` (rejected — `App` is already an instance; generic), `AppBackend` (rejected — "backend" implies a swappable implementation, which it is not). `AppRuntime` aligns the class name, its module (`runtime.py`), and its layer-manifest unit (`runtime`).

**2. `build()` snapshots into a fresh `Container`; it does not seal the shared one.**
The finisher's internal `build(app) -> AppRuntime` reads the App's accumulated registrations (`Container.providers_view()` plus the registered wire-scopes) and constructs a **new** `Container`, validates its provider graph, and hands it to `AppRuntime`. The compose-phase `App` keeps its own mutable container untouched.
Alternative considered: seal the shared container in place (the ADR 0016 / 0017 model). Rejected because it keeps `App` stateful — post-build, the shared container is sealed, so `App.provide()` would still have to raise. Snapshotting makes `App` a true pure builder: post-build mutation affects only future builds, never a running `AppRuntime`.

**3. Finishers own `build()`; there is no public `build()`.**
`a2kit.run`, `build_mcp_server`, and `a2kit.testing.client` call `build()` internally, exactly as they call `_seal()` today (ADR 0017's "finishers seal internally" pattern). Consumers never see `AppRuntime`. This preserves the smallest honest framework-consumer contract: one public type plus the entry functions.

**4. The `_sealed` compose-after-seal guard is removed outright.**
The guard exists to catch composition leaking into a running app. Under decision 2 that leak is structurally impossible — a running `AppRuntime` holds its own snapshot. With the bug gone, the guard is dead defense and is deleted, not preserved. This dissolves `App`'s dual-mode personality entirely: `App` has no `_sealed` flag and no mode.

**5. `core` splits into three flat manifest units.**
`unit_for_module` / `unit_for_path` in `layers.py` gain a module-to-sub-layer map. Assignment (verified clean DAG):
- **kernel** — `exceptions`, `_context_protocol`, `metadata`, `_list_helpers`, `_lifecycle_helpers`, `_field_introspect`.
- **authoring** — `_verbs`, `tool`, `signature`, `schema`, `routers`, `_verb_validators`.
- **runtime** — `app`, `runtime` (new — `AppRuntime`), `__main__`.
- **facades** (layer-exempt, re-export only) — `__init__.py`, `ldd.py`, `testing.py`.
Files stay flat; no new subpackages, so the `module-layout-discipline` "no additional core subpackages" requirement is untouched.

**6. ADR 0017 is superseded by a new ADR.**
The new ADR records the split under the layer-enforcement justification and the build-snapshot model, explicitly noting that ADR 0017's boundary-crossing reasoning still holds — the decision changed because a new force (the layer manifest) was added, not because the old reasoning was wrong.

## Risks / Trade-offs

- **`providers_view()` + wire-scopes may be an incomplete snapshot** → a planning task must enumerate every piece of compose-phase state `build()` must carry: provider registrations, wire-scope registrations, the dispatch hook, the router registry and descriptors, the LDD configuration, the health registry. If any is missed, a finisher produces a runtime that silently diverges from the composed App. Mitigation: an explicit "snapshot completeness" task plus a test that mutates the `App` after `build()` and asserts the `AppRuntime` is unaffected.
- **ADR 0018 (tombstone lifecycle) interaction** → the removed `_sealed` guard must follow the tombstone rules — or be exempt because the *entire mechanism* is gone (no surface to tombstone). Mitigation: a task to apply ADR 0018 to the removal.
- **Third mechanical migration of the finishers** → ADR 0016 then 0017 already migrated every composition site twice. This is a third. Accepted: it is the cost of having deferred the layer manifest until after ADR 0017.
- **Core file count** → adding `runtime.py` raises the top-level file count by one. `module-layout-discipline` carries a "≤ 12 core files" requirement that the current tree already strains. This change should not silently worsen it; see Open Questions.

## Migration Plan

1. Introduce `AppRuntime` in a new `src/a2kit/runtime.py`, lifting the run-phase members (`__aenter__` / `__aexit__`, the validated container, dispatch wiring, lifecycle unwind) out of `App`.
2. Add the internal `build(app) -> AppRuntime` and route all three finishers through it; delete `_seal()` and the `_sealed` flag.
3. Reduce `App` to compose-phase: registries, the verb methods, the mutable compose container.
4. Migrate the six guard tests — `tests/test_app.py::test_composition_after_sealing_raises` (parametrized over five verbs), `::test_finisher_seals_then_composition_raises`, `::test_seal_is_idempotent_app_reusable`, `::test_seal_validates_provider_graph`, `::test_no_post_seal_override_surface_on_container`, and `tests/app/test_provide_unified.py::test_sealed_after_aenter` — to assert the build-snapshot behavior (post-build mutation is harmless; graph validation still rejects scope violations at `build()` time).
5. Update `layers.py` (`LAYER_MANIFEST`, `unit_for_module`, `unit_for_path`) for the three sub-units; extend `A2K-LAYER` coverage; add a manifest test.
6. Mark ADR 0017 superseded; add the new ADR; regenerate `docs/adr/INDEX.md`.

Rollback: the change is internal; reverting the commit restores the single-class `App` with no consumer impact.

## Open Questions

- Does the `module-layout-discipline` "≤ 12 core files" requirement need a delta? Adding `runtime.py` makes the strain worse. Option A: leave it (pre-existing drift, not this change's job). Option B: the three-sub-layer manifest becomes the organizing principle and the flat file-count cap is relaxed in this change's delta. Recommendation: Option B — the file-count cap predates the layer manifest and the manifest is the better structural control.
- Should `App.container()` stay a public-ish accessor, or is the compose-phase container now fully private? Investigation showed it is touched only framework-internally; leaning toward keeping it as an internal accessor unchanged.
