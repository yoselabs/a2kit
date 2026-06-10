# Tasks — prune-stale-tombstones

## 1. Convention first (governance — confirm before code)

- [ ] 1.1 Amend `AGENTS.md` §1 ("No backward compatibility shims") with the
      sunset clause (design D2): a migration-hint tombstone is a transition
      aid kept only until the live downstream consumer has migrated past the
      removal, then deleted; a swept name raises the language-default
      `AttributeError` / `TypeError` (loud, no alias, no hint).
- [ ] 1.2 Record the keep-list (in-flight cluster: ADR 0028 positional
      `App(...)` + `App.add_router`, refound-ldd, v0.40 `TestClient`
      tombstones) so a future sweep knows what was deliberately retained.

## 2. Specs (RED — define the post-sweep behavior)

- [ ] 2.1 Apply the spec deltas: REMOVE `app-lifecycle` lifespan req +
      `surface-protocol` Substrate req; MODIFY `core-composition`,
      `runtime-config`, `health-probe` to assert generic kwarg rejection /
      plain `AttributeError`.
- [ ] 2.2 `openspec validate prune-stale-tombstones --strict` passes.

## 3. Update tests to the post-sweep behavior (RED → watch fail)

- [ ] 3.1 Rewrite the raise-assertion tests for the swept tombstones to
      assert the generic outcome (unexpected-kwarg `TypeError` / plain
      `AttributeError` / `ImportError`), not the bespoke hint string:
      `test_lifecycle_migration_errors.py` (`lifespan=`, `health_tool=`,
      `Router.lifespan`, `teardown=`), the `App.debug` hint test in
      `test_di_for_sub_configs.py`, the `Substrate` tombstone test in
      `test_substrate.py`, the cli/context tombstone tests
      (`packages/cli/test_context.py`, `packages/context/test_stderr.py`),
      the `@a2kit.tool` `_REMOVED` test, the `TOONSnapshotExtension` test.
- [ ] 3.2 Run them; confirm they fail against the still-present tombstones
      (the bespoke hints still fire) for the right reason.

## 4. Sweep the tombstones (GREEN)

- [ ] 4.1 `src/a2kit/app.py`: delete the special-cased `lifespan` / `debug` /
      `health_tool` branches in `_reject_removed_kwargs` (keep the generic
      `**_kw` rejection); delete `App.add_router`'s sibling
      `Router.lifespan` classmethod tombstone, the `app.provide(teardown=)`
      hint branch, and the `App.debug` / `app.debug` `__getattr__` +
      `_REMOVED_ATTRS` entries.
- [ ] 4.2 `src/a2kit/__init__.py`: remove the `@a2kit.tool` entry from
      `_REMOVED`.
- [ ] 4.3 `src/a2kit/packages/dispatch/substrate.py`: delete the
      `Substrate` raising `__getattr__`.
- [ ] 4.4 Delete `src/a2kit/packages/cli/context.py` (the tombstone module)
      and its `import_acyclicity` / layer-manifest references.
- [ ] 4.5 `src/a2kit/packages/testing/snapshots.py`: delete the
      `TOONSnapshotExtension` tombstone.
- [ ] 4.6 Keep untouched: positional `App(...)`, `App.add_router`,
      `TestClient.override` + renamed-method tombstones (in-flight horizon).

## 5. Reconcile the drift gates (sweeping changes `hasattr`)

- [ ] 5.1 Swept names no longer resolve, so the README / spec / docs
      symbol-drift gates will newly FLAG any doc/spec that still cites a
      swept name. Grep the living docs + specs for the swept names and fix
      or remove each reference (e.g. an antipattern that *names* the swept
      surface in backticks). Run all three drift gates green.
- [ ] 5.2 Confirm `tests/test_spec_symbol_drift.py` allowlist no longer
      needs the swept tombstone names (remove any that were allowlisted as
      tombstone-migration targets, e.g. `a2kit.tool`).

## 6. Verify

- [ ] 6.1 Full suite green; `make lint` green (ruff / ty / a2kit-lint /
      all three drift gates / openspec-validate / surface snapshots).
- [ ] 6.2 `public-api-tier-snapshot` unaffected (no `_LAZY_ATTRS` live
      name changed); regen snapshots only if a tombstone leaked into one.
