## Why

The `add-spec-drift-gate` + `reconcile-stale-specs` wave installed a SPEC↔code drift gate and cut structural rot (39 requirements removed), but the gate's grandfathered allowlist still carries 38 `# reconcile:`-tagged entries — symbols cited in 17 capability specs that do not resolve on the live `a2kit` surface. An allowlist that does not shrink to zero leaves the spec tree describing a framework that no longer exists, and every stale entry is a place the gate is deliberately blind. This change is the second and final reconcile pass: it clears every `# reconcile:` entry so the gate runs with only tombstone-target and illustrative exemptions.

## What Changes

- **Rewrite dead-name citations in 16 capability specs.** Reconciled spec bodies still cite removed symbols (`app.singleton`, `app.on_startup`, `Container.resolve_sync`, `a2kit.Param`, `A2K-CORE-PURITY`, …) — partly to *document* migrations, which is the ADR 0018 D7.2 anti-pattern (a living spec describes current surface, not removed surface). Each such sentence or scenario is rewritten to describe only the live surface, or removed where it only documented an absence.
- **BREAKING (spec tree): delete the `app-builder-runtime` capability spec.** Its capability — the `AppBuilder` / sealed-`App` two-type split — was superseded by the one-`App` collapse (ADR 0017). Per ADR 0018 D7.3 a superseded capability spec is deleted, not kept as a husk. OpenSpec deltas cannot archive a spec to zero requirements (the validator rejects an empty spec), so the `openspec/specs/app-builder-runtime/` directory is removed directly as an implementation task; the capability's history is preserved in git and in the archived `split-app-builder-runtime` change.
- **Reconcile the 7 specs `reconcile-stale-specs` never scoped.** `otel-adapter`, `di-conditional-injection`, `lazy-init-resources`, `verb-decorators`, `test-container-peek`, `di-scope-cleanup-stack`, and `app-builder-runtime` were outside that change's 17-delta scope; their drift is addressed here.
- **Empty the grandfathered allowlist.** Every `# reconcile:` entry in `tests/test_spec_symbol_drift.py` is removed. After this change the allowlist holds only tombstone-migration targets and illustrative placeholders; the gate is green with no grandfathered drift.

## Capabilities

### New Capabilities

<!-- none — this change only reconciles and removes spec surface -->

### Modified Capabilities

- `app-singletons`: scenarios/sentences citing `app.singleton` / `app.has_singleton` / `app.singletons` / `App.__getattr__` rewritten to describe only the live `provide` surface.
- `app-lifecycle`: drop the `app.serve_all` and `a2kit.di.cleanup` citations; name the live cleanup surface.
- `core-composition`: drop the dead `A2K-CORE-PURITY` / `A2K-CORE-CLEAN` lint-code and `app.use` / `a2kit.packages.enrichers` citations.
- `di-conditional-injection`: repair the `a2kit.Lazy` citation to the live `Lazy[T]` surface.
- `di-container-package`: drop the `a2kit.packages.connections.container` phantom-path citation.
- `di-scope-cleanup-stack`: repair the `a2kit.di.cleanup` citation.
- `docs-code-parity`: rewrite the symbol-enumeration scenarios so they describe the removed-symbol class without citing each dead name in code font.
- `in-process-test-client`: drop residual `app.on_startup` / `app.on_shutdown` citations.
- `lazy-init-resources`: repair `app.async_resource` / `app.lazy` to the live resource-DI surface.
- `mcp-context-passthrough`: drop residual `App.on_startup` / `a2kit.ldd.current_ctx` citations.
- `module-layout-discipline`: repair `a2kit.lint` / `a2kit.packages.lint.ALL_RULES` to live module paths.
- `otel-adapter`: repair the `a2kit.tags` / `a2kit.verb` / `a2kit.router` / `a2kit.tool_name` / `a2kit.tool.calls` citations to the live `A2KitMeta` surface.
- `router-conventions`: drop the `a2kit.Param` and `Router.lifespan` / `a2kit.packages.enrichers` citations.
- `test-container-peek`: repair `Container.resolve_sync` / `app.singleton` to the live container surface.
- `tool-descriptors`: drop the `App.tool_descriptors` / `app.tool_descriptors` citations (the method was removed in `remove-dead-surface`).
- `verb-decorators`: repair the `a2kit.list_view` citation to the live verb surface.

The `app-builder-runtime` capability is **deleted** outright (superseded by ADR 0017) — see "What Changes" above. It is a direct directory removal, not a delta-backed modification, so it is not listed as a modified capability.

## Impact

- **Specs**: 16 capability specs reconciled, 1 (`app-builder-runtime`) deleted. No new capability.
- **Tests**: `tests/test_spec_symbol_drift.py` — all 38 `# reconcile:` allowlist entries removed; the gate stays green because the cited specs no longer carry the dead names.
- **Code**: none. This is a spec-tree + gate-allowlist change; `src/a2kit/` is untouched.
- **Docs**: none beyond the spec tree.
