# prune-stale-tombstones

## Why

a2kit removes surfaces by leaving a **fail-loud tombstone**: the old name still
resolves but raises with a migration hint (`AGENTS.md` §1 — "crashes loudly
with an embedded migration hint. No aliases, no `DeprecationWarning`, no
transitional period"). This is the no-backward-compat policy, not a violation
of it: the old path never runs.

But `AGENTS.md` §1 is silent on *when a tombstone may itself be deleted*, so
they accumulate **permanently**. There are ~14 today, the oldest from v0.23
(`TOONSnapshotExtension`) and v0.33 (`@a2kit.tool`) — five-plus minor versions
past any consumer that would hit them. Several even carry dedicated
capability-spec scenarios asserting their hint, so they read as load-bearing
behavior rather than expiring transition aids. That is the redundancy: a
permanent monument to every rename a2kit has ever made.

This change sets a **sunset rule** for tombstones and sweeps the settled ones,
keeping only the in-flight cluster the live downstream consumer (a2web) will
hit when it migrates.

## What Changes

- **Convention (`AGENTS.md` §1):** add a sunset clause — a migration-hint
  tombstone is kept only until the live downstream consumer has migrated past
  the removal (the "migration horizon"); after that it is deleted and the name
  raises the language-default `AttributeError` / `TypeError` with no hint. The
  hint is a *transition aid*, not a permanent surface.
- **Sweep settled tombstones** (removal predates the current migration horizon;
  a2web already moved past them): `@a2kit.tool` (v0.33), `App(lifespan=)`,
  `App(health_tool=)`, `Router.lifespan` (v0.35), `app.provide(teardown=)`
  (v0.36), `App.debug` / `app.debug` (di-for-sub-configs), `App(debug=)`
  (ADR 0022), `Substrate` Literal (remove-substrate-literal), the
  `a2kit.packages.cli.context` tombstone module, `TOONSnapshotExtension`
  (v0.23). Delete each tombstone + its raise-assertion tests.
- **Keep the in-flight tombstones** a2web will hit on its pending migration:
  positional `a2kit.App(...)` and `App.add_router` (ADR 0028),
  `TestClient.override` + renamed `TestClient` methods (v0.40). These stay
  until a2web lands the ADR-0028 / refound-ldd surface.
- **Specs:** modify the capabilities whose scenarios assert a swept
  tombstone's hint so they require only that the surface no longer exists
  (language-default error), not a specific hinted message.

## Capabilities

### Modified Capabilities

- `app-lifecycle`: REMOVE the dedicated "reject `lifespan=` with a migration hint" requirement; `lifespan` falls through to `App.__init__`'s generic unexpected-kwarg `TypeError`.
- `surface-protocol`: REMOVE the dedicated "`Substrate` Literal import SHALL raise with migration hint" requirement; `Substrate` is simply absent.
- `core-composition`: relax the `App(debug=)` and `app.debug` clauses + scenarios — generic unexpected-kwarg `TypeError` and a plain `AttributeError`, no bespoke hint.
- `runtime-config`: `app.debug` raises the language-default `AttributeError`; drop the migration-hint clause + scenario.
- `health-probe`: `App(health_tool=True)` raises the generic unexpected-kwarg `TypeError`, not a `health_check`-named hint.

(No delta needed for `core-purity` or `operational-contracts`: both already describe the **generic** `**_kw` rejection — "Unexpected kwargs: {...}. See CHANGELOG.md" — which is exactly the post-sweep behavior. The kwarg tombstones already have that loud, CHANGELOG-pointing fallback; this change only removes their *bespoke* per-kwarg hints.)

## Impact

- **Convention:** `AGENTS.md` §1 gains a sunset clause (a governance edit — Constitution Phase A, human-confirmed).
- **Code:** `src/a2kit/__init__.py` (`_REMOVED`), `src/a2kit/app.py` (tombstone methods + `_reject_removed_kwargs`), `src/a2kit/packages/dispatch/substrate.py`, `src/a2kit/packages/cli/context.py` (delete the module), `src/a2kit/packages/testing/snapshots.py`.
- **Tests:** delete the raise-assertion tests for each swept tombstone (`test_lifecycle_migration_errors.py`, `test_di_for_sub_configs.py` debug-hint test, `test_substrate.py` tombstone test, cli/context tombstone tests, etc.).
- **Gate side-effect:** the symbol-drift gate is `hasattr`-based, so a tombstone method currently reads as "resolves." After the sweep, those names genuinely vanish — which is more honest for the gate, not less.
- **Out of scope:** the kept in-flight tombstones; the `_LAZY_ATTRS` live surface (unchanged); any new removals.
