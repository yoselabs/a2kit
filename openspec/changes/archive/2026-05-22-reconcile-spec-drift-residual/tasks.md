## 1. Preconditions

- [ ] 1.1 Confirm `make check` is green on `main` before starting — the spec-drift gate currently passes only because the 38 `# reconcile:` allowlist entries grandfather the residual drift
- [ ] 1.2 Re-run the gate's drift audit (empty the grandfathered allowlist in a scratch copy, or read the `# reconcile:` tags) to confirm the 17-spec / 38-symbol worklist has not shifted since this change was proposed

## 2. Apply the 16 spec-reconciliation deltas

- [ ] 2.1 Apply the MODIFIED/REMOVED deltas for `app-lifecycle`, `app-singletons`, `core-composition` (group A) — these drop `app.serve_all`, `a2kit.di.cleanup`, the `app.singleton`/`has_singleton`/`singletons`/`App.__getattr__` citations, `app.use`, `a2kit.packages.enrichers`, and the `A2K-CORE-PURITY`/`A2K-CORE-CLEAN` lint-code references
- [ ] 2.2 Apply the deltas for `di-conditional-injection`, `di-container-package`, `di-scope-cleanup-stack`, `docs-code-parity` (group B) — repair `a2kit.Lazy`, the `a2kit.packages.connections.container` phantom path, `a2kit.di.cleanup`, and the `docs-code-parity` dead-symbol enumerations
- [ ] 2.3 Apply the deltas for `in-process-test-client`, `lazy-init-resources`, `mcp-context-passthrough`, `module-layout-discipline` (group C) — drop the `on_startup`/`on_shutdown` citations, repair `app.async_resource`/`app.lazy`, `a2kit.ldd.current_ctx`, and the `a2kit.lint`/`a2kit.packages.lint.ALL_RULES` paths
- [ ] 2.4 Apply the deltas for `otel-adapter`, `router-conventions`, `test-container-peek`, `tool-descriptors`, `verb-decorators` (group D) — repair the otel span-attribute citations, `a2kit.Param`, `Router.lifespan`, `Container.resolve_sync`, `App.tool_descriptors`, `a2kit.list_view`

## 3. Delete the superseded `app-builder-runtime` capability

- [ ] 3.1 Delete the `openspec/specs/app-builder-runtime/` directory outright (superseded by ADR 0017; ADR 0018 D7.3). OpenSpec deltas cannot archive a spec to zero requirements, so this is a direct directory removal, not a delta
- [ ] 3.2 Confirm git records the deletion and that no remaining spec or doc cross-references the `app-builder-runtime` capability

## 4. Empty the grandfathered allowlist

- [ ] 4.1 In `tests/test_spec_symbol_drift.py`, remove every `# reconcile:`-tagged entry from `_ALLOWLIST` — the entire grandfathered-drift group
- [ ] 4.2 Tidy the surrounding comment block so the allowlist documents only the two surviving groups (tombstone-migration targets, illustrative placeholders)
- [ ] 4.3 Confirm the two surviving groups are still needed: `a2kit.AppBuilder` / `a2kit.tool` (tombstone targets) and `App.method` / `Router.attribute` / `a2kit.ldd.foo` / `app.method` (illustrative metavariables)

## 5. Validate and wrap up

- [ ] 5.1 Run the spec-drift gate (`uv run pytest tests/test_spec_symbol_drift.py --no-cov -q`) — green with zero grandfathered entries; the audit reports zero unresolved symbols
- [ ] 5.2 Run `make check` (lint + test) — the gate runs inside `make lint`; no code changed, so nothing else should move
- [ ] 5.3 Run `make markdown-lint` — green (no doc files changed, but the spec tree was edited)
- [ ] 5.4 `openspec validate reconcile-spec-drift-residual --strict`
- [ ] 5.5 `openspec archive reconcile-spec-drift-residual`
- [ ] 5.6 Remove the "spec-drift-gate allowlist: second reconcile pass" item from `BACKLOG.md` — it is now done
