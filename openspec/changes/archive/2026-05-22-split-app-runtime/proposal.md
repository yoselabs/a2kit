## Why

`core` is one undifferentiated lint-manifest unit — 17 top-level modules, the highest fan-in in the codebase (33), and zero intra-unit layer enforcement. The framework's densest, most-churned code has the least structural protection: nothing stops `metadata.py` from importing `app.py` tomorrow.

The single obstacle to splitting `core` is `app.py` (542 LOC). `App` fuses two phases into one class — the compose phase (the `add_*` / `provide` / `health_check` verbs) and the sealed run phase (the validated container, dispatch, the `__aenter__` / `__aexit__` lifecycle) — toggled by a `_sealed` mode flag. It cannot sit in a single layer because it *is* two layers.

ADR 0017 collapsed an earlier `AppBuilder` / `App` split, reasoning the sealed runtime "never crosses the consumer boundary." That reasoning still holds — but ADR 0017 predates ADR 0015's layer manifest. The justification for splitting is no longer boundary-crossing; it is layer enforcement. A new force warrants a new decision: this change supersedes ADR 0017.

## What Changes

- Split `App` into two types: a compose-phase **`App`** (keeps the public name and the Flask / FastAPI / FastMCP "instantiate one object" look and feel) and an internal sealed-runtime **`AppRuntime`**. `AppRuntime` is never exported and never crosses the consumer boundary (verified: all examples and the public `a2kit.*` API stop at compose-phase).
- Finishers (`a2kit.run`, `build_mcp_server`, `a2kit.testing.client`) gain an internal `build()` step that produces an `AppRuntime` from an `App`. Their public signatures are unchanged — the integration surface does not move.
- `build()` snapshots the App's provider registrations and wire-scopes into a **fresh** `Container` rather than sealing the shared one. Consequence: `App` becomes a pure, reusable builder; post-build mutation affects only future builds.
- **BREAKING:** the `_sealed` compose-after-seal guard is removed. The bug it caught (composition leaking into a running app) becomes structurally impossible under the build-snapshot model, so the `TypeError` on a post-seal composition verb no longer fires. Six tests that lock this guard migrate to the build-snapshot model.
- Split the `core` lint-manifest unit into three lint-enforced sub-layers: **kernel** (leaf types and helpers), **authoring** (decoration-time surface), **runtime** (`app` / `AppRuntime`). The split is a verified clean DAG with zero back-edges. The re-export facades (`__init__.py`, `ldd.py`, `testing.py`) become a layer-exempt group.
- `packages/lint/layers.py` gains the three manifest entries; `unit_for_module` / `unit_for_path` learn to map specific top-level modules to specific sub-layers (today they collapse all non-`packages` `a2kit.*` modules to one `core` node).
- ADR 0017 is marked superseded; a new ADR records the App / `AppRuntime` split under the layer-enforcement justification.

Out of scope: the DI `Container` is **not** split (investigated, dropped — `container.py` is ~90% irreducible run-phase code). Capability registration is a separate downstream change.

## Capabilities

### New Capabilities

None. This change reshapes existing behavior; it introduces no new capability.

### Modified Capabilities

- `app-lifecycle`: the `__aenter__` / `__aexit__` lifecycle and container sealing move from `App` to `AppRuntime`; finisher-driven `build()` replaces the in-place `_seal()`; the "sealed container rejects late `provide`" requirement is removed (the build-snapshot model makes the guard unnecessary).
- `core-composition`: the "composition after sealing is rejected" requirement is removed; `App` is redefined as a reusable compose-phase builder; `App.container()` / container-handling requirements are restated against the build-snapshot model.
- `module-layout-discipline`: the layer-manifest requirements change — `core` is no longer a single pseudo-unit; it becomes three ordered units (kernel, authoring, runtime), each lint-enforced, with the facades group exempt.

## Impact

- **Code:** `src/a2kit/app.py` (split into the compose-phase `App` plus a new `runtime` module for `AppRuntime`); the finishers in `packages/cli`, `packages/mcp`, `packages/serve`, `packages/testing`; `packages/lint/layers.py` and the `A2K-LAYER` rule.
- **Tests:** six guard tests migrate — `tests/test_app.py` (`test_composition_after_sealing_raises` and four siblings) and `tests/app/test_provide_unified.py::test_sealed_after_aenter`. New tests cover `build()` snapshot isolation and the three-sub-layer manifest.
- **Public API / consumers:** unchanged. `App`, the verb decorators, and all three finishers keep their signatures. `AppRuntime` is internal-only.
- **Decisions:** ADR 0017 superseded; a new ADR added.
- **Interactions:** ADR 0018 (tombstone lifecycle) — the removed `_sealed` guard's tombstone treatment must be checked. Downstream capability-registration work must archive after this change (shared `App` spec, wave-ordering rule in AGENTS.md).
