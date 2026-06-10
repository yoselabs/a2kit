# purge-compat-debt

## Why

a2kit's stated policy (`AGENTS.md` §1) is "no backward compatibility shims," but
the codebase still carries a layer of *transitional machinery*: fail-loud
tombstones that raise an embedded migration hint, silent compat aliases that
still work, and the plumbing that supports them. They accumulated under the
"keep the hint until the live consumer migrates" sunset rule.

The maintainer's decision: **drop the in-code migration-hint courtesy
entirely.** Consumers read the CHANGELOG; that is enough. A removed surface is
simply *gone* — the old name raises the language-default Python error, with no
embedded recipe, no alias, no interception. This amends `AGENTS.md` §1 itself
(the "embedded migration hint" mandate) and then purges every existing instance.

This is the §1 tombstone-sunset rule taken to its limit: the migration horizon
is **now**, for everything, because the only consumer contract is the CHANGELOG.

## What Changes

### Convention (`AGENTS.md` §1) — the governing edit

Rewrite §1: a removed/renamed surface is deleted, full stop. The old name raises
the **language-default** `AttributeError` / `TypeError` / `ImportError` — no
embedded migration hint, no `**_kw` catch-with-recipe, no `__getattr__`
interception, no alias, no `DeprecationWarning`, no tombstone. The migration
recipe lives **only** in the CHANGELOG (`Unreleased` → versioned), which every
breaking change must carry. The lone carve-out: a deletion that would cause
**silent misbehavior** (a load-bearing invariant, not compat) keeps a plain
guard with a terse, non-archaeological message (e.g. "App is abstract; subclass
it") — never a versioned migration story. The just-added "tombstone sunset"
clause is removed (superseded: there are no tombstones).

### Purge — tombstones (delete the hint machinery → plain errors)

- `App.add_router(...)` (`app.py`) → deleted; `app.add_router` is a plain `AttributeError`.
- `a2kit.App(...)` base construction (`app.py`) → keep the abstract-class guard, strip the ADR-0028 migration message to a terse "App is abstract; subclass it / use `app_of`".
- `Container._retired()` + its 7 DI tombstones (`register` / `register_singleton` / `resolve` / `aresolve` / `has` / `has_async_singleton` / `has_any_async_singletons`) (`packages/di/container.py`) → deleted; old names are plain `AttributeError`.
- `TestClient._MIGRATED_NAMES` (`call`→`invoke`) + `_REMOVED_NAMES` (`override`) + the `__getattr__` interception (`packages/testing/client.py`) → deleted; old names are plain `AttributeError`.
- `_lazy_module` `removed=` parameter + `RemovedHints` type + the `_REMOVED` resolution branch (`_lazy_module.py`) → deleted (dead since the tombstone sweep emptied `_REMOVED_IN_V033`).

### Purge — silent aliases (delete the working compat → old name breaks)

- `LEGACY_CODE_ALIASES` + `normalize_code` (`packages/lint/static.py`) and `_REGO_LEGACY_ALIASES` (`packages/lint/_bundle/extract_facts.py`) → deleted. First migrate the **3** internal `# noqa: A2K-LAYER` / `A2K-PKG-FRONT-DOOR` / `A2K-PKG-INIT-PURITY` comments to their `AK###` spellings, then drop the tables and inline the raw code at `normalize_code`'s two call sites.
- `AmbientContextMissing` (`exceptions.py`, the "deprecation-shim retained for one release") → deleted; the dispatch layer raises only `request_scope.RequestScopeMissing`.
- The deprecated module-level `SURFACE_REGISTRY` proxy (`__init__.py` / `packages`) → deleted; readers use the composed `runtime.surfaces` registry directly.

### CHANGELOG

Every purged surface gets a migration row in a new `## Unreleased` section — this is now the *sole* migration channel, so it must be complete.

## Capabilities

The capabilities whose scenarios assert a migration-hint **message** are modified
to assert the **plain** language-default error instead (or drop the
hint-specific scenario). Affected set (to confirm per-capability during apply):
`core-composition` (add_router), `request-scoped-di` / `thin-core-surface` (Container retired methods), `in-process-test-client` (TestClient call/override), `mcp-context-passthrough` / `dispatch-pipeline` (AmbientContextMissing → RequestScopeMissing), `surface-protocol` / `serve-topology` (SURFACE_REGISTRY proxy), plus the lint-code-format capability (LEGACY_CODE_ALIASES). Capabilities that only mention these names in historical prose need no delta.

## Impact

- **Convention:** `AGENTS.md` §1 rewritten (Constitution Phase A — human-confirmed; the maintainer has confirmed).
- **Code:** `app.py`, `packages/di/container.py`, `packages/testing/client.py`, `_lazy_module.py`, `packages/lint/static.py`, `packages/lint/_bundle/extract_facts.py`, `exceptions.py`, `__init__.py` (+ internal `SURFACE_REGISTRY` readers).
- **Tests:** every `*_raises_with_migration_hint` / hint-message-asserting test for a purged surface is rewritten to assert the plain error, or deleted; the `_lazy_module` `removed=` test is deleted.
- **Consumers (a2web):** old surfaces now raise bare Python errors instead of hinted ones. Accepted — the CHANGELOG is the migration contract. (Trade-off noted: a2web is migrated by an AI agent, for which inline hints were arguably more useful than for a human; the bet is that the agent reads the CHANGELOG.)
- **Out of scope:** architectural duplications (the two signature installers `install_mcp_signature` vs `install_substrate_signature`, the `di/container.py` god-object, `Resolver` vs `Container`) — these are dual *implementations* needing redesign, not compat cruft, and are tracked separately. The derived `extras.expose` field is left as-is (a convenience read, not compat).
