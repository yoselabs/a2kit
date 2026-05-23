## 1. Rename

- [ ] 1.1 `src/a2kit/metadata.py`: rename `get_meta` → `_get_meta`, `set_meta` → `_set_meta`. Add `META_ATTR` private constant stays.
- [ ] 1.2 Add migration-hint shims at module level: `def get_meta(*a, **kw): raise AttributeError(<hint pointing to ToolDescriptor>)`. Same for `set_meta`. Remove from `__all__` if present.

## 2. Helper relocation

- [ ] 2.1 Move `_stamp(fn, meta)` from `_verbs.py` to `metadata.py` as a module-private helper.
- [ ] 2.2 Move `_compute_report_schema(...)` from `_verbs.py` to `metadata.py` as module-private.
- [ ] 2.3 Move `_build_annotation_kwargs(...)` and `_kwargs_for(...)` from `_verbs.py` to `_verb_validators.py`.
- [ ] 2.4 Update `_verbs.py` imports to consume the relocated helpers; verify no public re-export.
- [ ] 2.5 `_verbs.py` SHALL now contain only: decorator factories (`read`, `write`, `list_`, `_read_internal`) and any public verb-level validators.

## 3. Internal cutover (src/)

- [ ] 3.1 `packages/cli/builder.py` (lines 159, 166, 325, 334, 354, 371): replace `get_meta(fn)` with `runtime.descriptor_for(name).metadata_view`. Where `metadata_view` is insufficient, plumb the missing field onto `ToolDescriptor`.
- [ ] 3.2 `packages/mcp/server.py:83`: same.
- [ ] 3.3 `packages/http/build.py`: same.
- [ ] 3.4 `packages/codemode/marshal.py`, `codemode/stubs.py`: same.
- [ ] 3.5 `packages/testing/client.py:316-318`: same.
- [ ] 3.6 `routers.py:105`, `schema.py:95`: these run pre-build during composition. Switch to `_get_meta` (underscored) — keep within allowlist.
- [ ] 3.7 `app.py:412, 416, 424, 434`: same — composition path, allowed to use `_get_meta`.

## 4. Lint rule

- [ ] 4.1 Add `packages/lint/rules/metadata_private.py`: AST scan all files under `src/a2kit/packages/` for `from a2kit.metadata import _get_meta` or `_set_meta`. Reject if module is not in allowlist.
- [ ] 4.2 Allowlist constant: `_METADATA_PRIVATE_ALLOWLIST = frozenset({"a2kit._verbs", "a2kit.metadata", "a2kit.runtime", "a2kit.tool", "a2kit.app", "a2kit.routers", "a2kit.schema"})`.
- [ ] 4.3 Test in `tests/packages/lint/rules/test_metadata_private.py` covering allow + reject cases.

## 5. Test sweep

- [ ] 5.1 Audit `tests/` for `get_meta` / `set_meta` calls (~35 sites). For each:
  - If the test builds an App: switch to `app.build().descriptor_for(name)`.
  - If the test inspects pre-build stamping behaviour: switch to `from a2kit.metadata import _get_meta` (test package gets temporary allowlist exemption documented in the lint rule).
- [ ] 5.2 Add `tests/conftest.py` helper `descriptor_for(app, name)` that calls `app.build()` once per fixture scope and caches the runtime.
- [ ] 5.3 Update `tests/test_spec_symbol_drift.py` allowlist if needed.

## 6. Spec sync

- [ ] 6.1 Modify `openspec/specs/tool-descriptors/spec.md`: declare `ToolDescriptor` (via `AppRuntime`) as the sole external read surface for tool meta.
- [ ] 6.2 Modify `openspec/specs/verb-decorators/spec.md`: remove `get_meta`/`set_meta` from the public read API.
- [ ] 6.3 Modify `openspec/specs/module-layout-discipline/spec.md`: add `A2K-METADATA-PRIVATE` requirement.

## 7. Verification

- [ ] 7.1 `openspec validate --strict privatize-tool-metadata` passes.
- [ ] 7.2 `make lint` green — including new `A2K-METADATA-PRIVATE` rule.
- [ ] 7.3 `make test` green — full suite.
- [ ] 7.4 Verify `docs/COMPONENT_MAP.md` regenerates with `metadata.py` no longer imported from L5 packages.
