# Design — prune-stale-tombstones

## Context

`AGENTS.md` §1 mandates that a removed surface "crashes loudly with an embedded
migration hint." The implementation is a tombstone: the name resolves to a
method / `__getattr__` branch / `**_kw` check that raises a hinted
`AttributeError` / `TypeError`. The old behavior never runs — this is genuinely
no-backward-compat, just with a helpful error.

`AGENTS.md` §1 says "no transitional period" (about *behavior* — there is never
a working old path) but is silent on the *lifetime of the hint*. In practice the
hints are permanent: ~14 tombstones span v0.23 → ADR 0028. The oldest are
five-plus minors past any live caller. Several are even pinned by dedicated
capability-spec scenarios, which makes them read as permanent surface.

The full inventory, classified against the **migration horizon** (the set of
removals the live downstream consumer, a2web, has not yet migrated past):

| Tombstone | Removed | Spec scenario? | Verdict |
|---|---|---|---|
| `@a2kit.tool` (`__init__._REMOVED`) | v0.33 | yes (`verb-decorators`, `core-purity`, `mcp-tool-annotations` — "does not exist", no hint asserted) | **sweep** |
| `App(lifespan=)` | v0.35 | yes — `app-lifecycle` asserts the hint | **sweep** |
| `App(health_tool=)` | v0.35 | yes — `health-probe`, `core-purity`, `operational-contracts` | **sweep** |
| `Router.lifespan` classmethod | v0.35 | no | **sweep** |
| `app.provide(teardown=)` | v0.36 | no | **sweep** |
| `App.debug` / `app.debug` | di-for-sub-configs (~v0.38) | yes — `core-composition`, `runtime-config` assert the hint | **sweep** |
| `App(debug=)` | ADR 0022 (~v0.38) | no | **sweep** |
| `Substrate` Literal | remove-substrate-literal (~v0.38) | yes — `surface-protocol` has a dedicated hint requirement | **sweep** |
| `a2kit.packages.cli.context` module | decouple-import-cycles (~v0.38) | no | **sweep** |
| `TOONSnapshotExtension` | v0.23 | no (specs only say `toon` helpers "no longer exist") | **sweep** |
| positional `a2kit.App(...)` | ADR 0028 | (migration-window) | **keep** |
| `App.add_router` | ADR 0028 W2 | (migration-window) | **keep** |
| `TestClient.override` + renamed methods | v0.40 | no | **keep** |

## Goals / Non-Goals

**Goals:**
- Establish a written sunset rule so tombstones stop being permanent.
- Delete the settled tombstones and their raise-assertion tests.
- Reconcile the capability specs that assert a swept tombstone's hint.

**Non-Goals:**
- Touching the in-flight cluster (ADR 0028 / refound-ldd / v0.40) a2web will hit.
- Changing the `_LAZY_ATTRS` live surface or any tier snapshot's *live* names.
- Introducing aliases or silent compat anywhere — swept names raise the
  language-default error, which is still loud, just unhinted.

## Decisions

### D1. Sunset criterion = migration horizon, not a magic version number

The cut is **"has the live downstream consumer migrated past this removal?"**,
not a fixed version. `pre-v0.37` (the original framing) was a proxy; the real
line is the in-flight surface refactor (ADR 0028 + refound-ldd + the v0.40
testing changes). Everything older is swept; that cluster is kept. This keeps
exactly the hints a2web will actually encounter and discards the archaeology.
The rule is recorded in `AGENTS.md` so future removals inherit it.

### D2. `AGENTS.md` §1 gains a sunset clause (governance edit)

Append to §1, in spirit:

> A migration-hint tombstone is a **transition aid, not a permanent surface.**
> Keep it only until the live downstream consumer has migrated past the
> removal; then delete it. A swept name raises the language-default
> `AttributeError` / `TypeError` (still loud, no alias, no hint). Do not let
> tombstones accumulate across the migration horizon.

This is a Constitution-Phase-A edit (convention change) and is the crux of the
change — it is what makes the deletions policy-compliant rather than a
violation of §1's "embedded migration hint."

### D3. Spec deltas relax hint-assertions to existence-assertions

For each swept tombstone with a spec scenario asserting its *hint*, MODIFY the
requirement so it asserts only that the surface **no longer exists** (raises the
language-default error). Concretely:
- `app-lifecycle`: `App(lifespan=)` falls into the generic unknown-kwarg
  `TypeError` path; drop the "names the version of removal and the two
  replacement paths" clause.
- `core-composition` + `runtime-config`: `app.debug` is a plain missing
  attribute (`AttributeError`); drop the migration-hint scenarios.
- `health-probe` + `core-purity` + `operational-contracts`: `health_tool=`
  is rejected by the standard unexpected-kwarg `TypeError`, not a special hint.
- `surface-protocol`: delete the dedicated "`Substrate` Literal import SHALL
  raise with migration hint" requirement; `Substrate` is simply absent.
- `verb-decorators` / `core-purity` / `mcp-tool-annotations` (for `@a2kit.tool`)
  and the `toon` specs already say only "does not exist" — no change needed.

### D4. `_reject_removed_kwargs` shrinks, it doesn't vanish

`App.__init__`'s `**_kw` still rejects unknown kwargs with the standard
"unexpected kwarg" `TypeError` (that is core hygiene, not a tombstone). Only the
*special-cased* hinted branches for `lifespan` / `debug` / `health_tool` are
removed — those kwargs then fall through to the generic rejection. So the
behavior stays "loud `TypeError`," just without the bespoke hint string.

### D5. Test pruning

Each swept tombstone has a raise-assertion test (e.g.
`test_lifecycle_migration_errors.py` for `lifespan=` / `health_tool=` /
`Router.lifespan` / `teardown=`; the debug-hint test in
`test_di_for_sub_configs.py`; the `Substrate` tombstone test in
`test_substrate.py`; the cli/context tombstone tests). Delete the assertions
that the *hint* fires; keep (or convert to) an assertion that the surface is
absent only where that still adds value. Net: the migration-error test files
shrink substantially or disappear.

## Risks / Trade-offs

- **Worse error for a late straggler.** A consumer still on the old surface now
  gets `AttributeError: 'App' object has no attribute 'debug'` instead of a
  hint naming `app.config.debug`. Accepted: these removals are 3–18 versions
  old; the hint's audience has migrated. The git history + CHANGELOG retain the
  migration guidance.
- **Governance edit.** Amending `AGENTS.md` §1 is a convention change requiring
  human confirmation (Phase A). If the convention is *not* amended, the sweep
  would violate §1 — so the `AGENTS.md` edit and the deletions must land
  together, or not at all.
- **Drawing the horizon line.** Mis-sweeping an in-flight tombstone would give
  a2web a bare error during its pending migration. Mitigated by the explicit
  keep-list (D1 table) and by keeping anything touched by ADR 0028 / refound-ldd
  / v0.40.
- **Re-rot.** Without enforcement, tombstones re-accumulate. Out of scope here;
  a future lint rule (`tombstone older than the horizon`) could enforce D2, but
  the horizon is not machine-knowable today — left as a manual review item.
