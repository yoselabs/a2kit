## 1. Preconditions

- [ ] 1.1 Confirm `add-spec-drift-gate` has landed (or is landing in the same batch); this change depends on its dead-symbol worklist and on its decision for the spec-deletion mechanism
- [ ] 1.2 Re-grep the live code for each dead symbol named in the deltas (`app.singleton`, `App.teardown_failures`, `TestClient.override`, `Container._snapshot`/`_restore`, `A2K-CORE-CLEAN`, `A2K-DI-CHAIN`, `A2K-DI-PROVIDER`, `_APP_CTX`, `packages/cli/app_ctx.py`, `a2kit.Param`, `App.use_factory`, `packages/enrichers/`, `packages/middlewares/`, `--format=toon`, `@a2kit.tool`, `on_startup`/`on_shutdown`) to confirm none has reappeared since the audit

## 2. Spec: app-singletons (STALE — rewrite)

- [ ] 2.1 Apply the `app-singletons` delta to `openspec/specs/app-singletons/spec.md`: rewrite the registration requirement around `provide(...)`, keep the resolution / scope / introspection requirements aligned to the live surface
- [ ] 2.2 Apply the REMOVED blocks: delete the dead `singleton(...)`-raises-with-hint requirement and the `App.teardown_failures` / `lifespan_cm()` requirement
- [ ] 2.3 Fix the genuine live bug: in `src/a2kit/_lifecycle_helpers.py` (~lines 37-45) rename every `app.singleton(...)` in the `TypeError` messages to `app.provide(...)`; the message must name the method that exists
- [ ] 2.4 Verify the `_lifecycle_helpers.py` fix with a targeted test (unannotated-factory `TypeError` message contains `app.provide`, not `app.singleton`)

## 3. Spec: core-purity (STALE — gut to true residue)

- [ ] 3.1 Apply the `core-purity` delta: REMOVE the `A2K-CORE-CLEAN`-dependent requirement, the identity-hook requirement, the `A2KitMeta.extra` requirement, and the verbatim-classname router-slug requirement
- [ ] 3.2 Confirm the residual `core-purity` requirements (introspection-failure WARN logging, `hasattr`-discipline, constructor validation, verb-decorator-no-feature-kwargs) still match the code; the delta leaves them in place
- [ ] 3.3 If the residue is judged to be a different capability, hand `core-purity` to `add-spec-drift-gate` for a directory-level decision (this change leaves a non-empty true residue)

## 4. Spec: di-container-package (STALE — repair)

- [ ] 4.1 Apply the `di-container-package` delta: correct the public-surface requirement to list the live `Container` methods and drop `register` from the current surface
- [ ] 4.2 Apply the REMOVED block for the `_snapshot`/`_restore` test-seam requirement

## 5. Spec: in-process-test-client (STALE — repair + remove dead requirement)

- [ ] 5.1 Apply the `in-process-test-client` delta: repair the test-client lifecycle requirement (App async-CM protocol, no `@app.on_startup`/`@app.on_shutdown`)
- [ ] 5.2 Repair the `_meta.health` requirement to drop `App(health_tool=True)` and require `@app.health_check`
- [ ] 5.3 Apply the REMOVED block for the dead `TestClient.override` requirement

## 6. Spec: module-layout-discipline (STALE — resolve self-contradiction)

- [ ] 6.1 Apply the `module-layout-discipline` delta: REMOVE the blanket "no underscore-prefixed modules" requirement; ADD/MODIFY to the allowlisted-private-sibling rule that matches the mirror lint rule
- [ ] 6.2 Apply the REMOVED block for the `_APP_CTX` / `packages/cli/app_ctx.py` phantom-file requirement
- [ ] 6.3 Repair the "one concept per file" exemplar names so they reference files that exist

## 7. Spec: request-scoped-di (STALE — repair)

- [ ] 7.1 Apply the `request-scoped-di` delta: repair the per-call-caching requirement and the resolution-surface requirement to drop `app.singleton` and the false "`_override`/`_snapshot`/`_restore` seam remains" claim
- [ ] 7.2 Apply the REMOVED blocks for the `A2K-DI-CHAIN` and `A2K-DI-PROVIDER` lint-rule requirements

## 8. Spec: router-conventions (STALE — resolve slug contradiction)

- [ ] 8.1 Apply the `router-conventions` delta: REMOVE the suffix-strip slug requirement; ADD the explicit-`slug`-attribute requirement matching `src/a2kit/routers.py`
- [ ] 8.2 Apply the MODIFIED enricher requirement (no `@enriches`, no `a2kit.packages.enrichers`)
- [ ] 8.3 Cross-check: confirm the `core-purity` delta REMOVEs its conflicting verbatim-classname slug requirement so the two specs and the code now agree

## 9. Spec: thin-core-surface (STALE — gut museum spec)

- [ ] 9.1 Apply the `thin-core-surface` delta: keep the three still-true requirements (FastMCP hard dependency, thin-core/plugin shape, no-compat-shims)
- [ ] 9.2 Apply the REMOVED blocks for the ~18 superseded requirements (`uncalled_for`/`Depends`, `dependency_overrides`, `App.use_factory`, `packages/enrichers/`, `--format=toon`, `runner.py`/`cli.py`, etc.)
- [ ] 9.3 If the residue is judged unworthy of a standalone capability, hand `thin-core-surface` to `add-spec-drift-gate` for a directory-level decision

## 10. Spec: tool-description-contract (STALE — remove unimplemented requirement)

- [ ] 10.1 Apply the `tool-description-contract` delta: REMOVE the `a2kit.Param` per-parameter-description requirement (no `Param` class exists)
- [ ] 10.2 Confirm the docstring-driven and Pydantic-`Field` requirements remain accurate and are left untouched

## 11. Spec: app-lifecycle (DRIFTED — repair)

- [ ] 11.1 Apply the `app-lifecycle` delta: MODIFY the cleanup-failure requirement to drop the stale `ToolError`/`ShutdownError` framing and cross-reference `di-scope-cleanup-stack`

## 12. Spec: core-composition (DRIFTED — coordinate)

- [ ] 12.1 Apply the `core-composition` delta: MODIFY the purity-lint-rule requirement to state that no core-purity-token rule (`A2K-CORE-PURITY` or `A2K-CORE-CLEAN`) exists, consistent with the `core-purity` removal

## 13. Spec: docs-code-parity (DRIFTED — repair stale example symbols)

- [ ] 13.1 Apply the `docs-code-parity` delta: MODIFY the symbol-drift requirement, the README-surface requirement, and the canonical-API-exerciser requirement to replace `app.singleton` / `Router.providers` / `App.singleton(..., teardown=...)` with the live `app.provide` surface

## 14. Spec: health-probe (DRIFTED — repair signature drift)

- [ ] 14.1 Apply the `health-probe` delta: MODIFY the CLI-exit-code requirement so `run_checks` is described as taking a `HealthRegistry` + `Resolver` (not an `App`) and drop the removed `lifespan_cm()`
- [ ] 14.2 MODIFY the health-check-DI requirement to replace `app.singleton` with `app.provide` and "singleton" wording with "app-scope"

## 15. Spec: mcp-context-passthrough (DRIFTED — repair)

- [ ] 15.1 Apply the `mcp-context-passthrough` delta: MODIFY the three drifted requirements to drop `app.singleton` (→ `app.provide`) and `App.on_startup` / `on_startup`-hook references

## 16. Spec: mcp-tool-annotations (DRIFTED — repair)

- [ ] 16.1 Apply the `mcp-tool-annotations` delta: MODIFY the two requirements that name `@a2kit.tool` to enumerate only the live verbs `@a2kit.read` / `@a2kit.write` / `@a2kit.list_`

## 17. Spec: operational-contracts (DRIFTED — repair)

- [ ] 17.1 Apply the `operational-contracts` delta: MODIFY the multi-App-isolation, `_meta.*`-namespace, and LDD-active-dispatch requirements to drop `@on_startup`/`@on_shutdown`, `health_tool=True`, and `app.singleton`

## 18. Spec: type-driven-format-routing (DRIFTED — repair symbol name)

- [ ] 18.1 Apply the `type-driven-format-routing` delta: REMOVE the `_infer_format_hint` requirement; ADD the `infer_format_hint` requirement (public name) with the same routing table and scenarios
- [ ] 18.2 Confirm `_is_dump_scalar` is left as-is — it is correctly underscore-private in the code; only `infer_format_hint` drifted

## 19. Validation and wrap-up

- [ ] 19.1 `openspec validate reconcile-stale-specs --strict` is green
- [ ] 19.2 Run `make check` (lint + test) — the only code change is the `_lifecycle_helpers.py` message fix; nothing else should move
- [ ] 19.3 Run the `add-spec-drift-gate` gate against the reconciled `openspec/specs/` — its dead-symbol worklist should report zero findings
- [ ] 19.4 Record in the change notes the follow-up coverage gaps (no spec for `signature.py`, `metadata.py` / `A2KitMeta`, `schema.py`, `exceptions.py`, per-family lint rules) for a later new-spec-authoring change
- [ ] 19.5 `openspec archive reconcile-stale-specs`
