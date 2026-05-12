## 1. README updates (Item I)

- [x] 1.1 Rewrite testing section (around lines 470-496): teach `TestClient.override(T, fake)` as the recommended override path; keep `app.provide(T, fake)` as the underlying mechanism with a one-line note.
- [x] 1.2 Add a short example of `app.singleton(T, async_factory)` near the existing `app.singleton(AppState, build_state)` example (line 190).
- [x] 1.3 Document `TestClient.call_wire` next to `TestClient.invoke` in the testing section, with a one-liner on when wire-shape matters vs. shape-after-decoding.
- [x] 1.4 Add a short note in the tool-authoring section about Google-style docstring `Args:` becoming MCP/CLI parameter descriptions automatically (point to `tool-description-contract` spec).
- [x] 1.5 Add a short note referencing `AmbientContextMissing` and the ambient LDD ctx contract (point to `OPERATIONAL_CONTRACTS.md` Q8).
- [x] 1.6 Update the migration-from-v0.x bullet at line 513 ("override providers via `app.provide(T, fake)`") to mention `TestClient.override` as the preferred test path.

## 2. Tool description contract: store `param_descriptions` on `A2KitMeta` (Item J)

- [x] 2.1 Add `param_descriptions: Mapping[str, str]` field to `A2KitMeta` (in `src/a2kit/tool.py` or wherever `A2KitMeta` is defined).
- [x] 2.2 Populate `A2KitMeta.param_descriptions` from the resolved Google-style docstring `Args:` block inside `_augment_annotations_from_docstring` (or its caller) while keeping the existing `fn.__annotations__` mutation in place for FastMCP schema gen.
- [x] 2.3 Add a unit test asserting `meta.param_descriptions["url"] == "..."` for the canonical fixture used by the existing docstring-pull tests.
- [x] 2.4 Update the docstring of `A2KitMeta` to mention the new field and its provenance.

## 3. OPERATIONAL_CONTRACTS.md Q8 rewording (Item K)

- [x] 3.1 Edit `OPERATIONAL_CONTRACTS.md` Q8 prose (around lines 320-340): drop "singleton/provider factory" from the list of contexts that raise; replace with explicit "module-level code, `on_startup`, `on_shutdown`, or any pre-dispatch context".
- [x] 3.2 Add a short paragraph stating that lazy singleton factories instantiated DURING dispatch do see the ambient ctx and may call LDD primitives. Include the `async def make_pool(): await ldd.info(...)` example from the design doc.
- [x] 3.3 Cross-reference the `operational-contracts` spec scenario "lazy singleton factory during dispatch is legal".

## 4. DI container spec: cover `_async_factories` (Item N)

- [x] 4.1 If the sibling `cleanup-round-5-6-code-shape` change has NOT landed yet, no code edits are needed for this item — the spec amendment alone documents the shipped behaviour. Confirm `Container._snapshot`/`_restore` already capture `_async_factories` (round-5 should have shipped this); if not, file a follow-up under the sibling change.
- [x] 4.2 If the sibling change HAS landed and introduced `Container._override`, re-read the sibling's `di-container-package` delta. If it supersedes the snapshot/restore framing, rewrite this change's `specs/di-container-package/spec.md` delta to MODIFY the new `_override` requirement instead, preserving the three-attribute invariant.
- [x] 4.3 Run `openspec validate cleanup-round-5-6-docs-alignment --strict` to confirm no collision with the sibling change.

## 5. Validation and archive prep

- [x] 5.1 Run `openspec validate cleanup-round-5-6-docs-alignment --strict`; resolve any errors.
- [x] 5.2 Run `openspec status --change cleanup-round-5-6-docs-alignment --json` to confirm all artifacts report `ready` or `complete`.
- [x] 5.3 Manually grep `README.md` and `OPERATIONAL_CONTRACTS.md` for any remaining stale references to "app.provide as test override" / "factories raise AmbientContextMissing" / missing call_wire mention.
- [x] 5.4 Confirm the `tests/` directory has a test (existing or new) covering `meta.param_descriptions` so the spec's new scenario isn't aspirational.
