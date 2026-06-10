# Tasks — purge-compat-debt

## 1. Convention first (governance — atomic with the deletions)

- [ ] 1.1 Rewrite `AGENTS.md` §1 to the D2 text (delete → language-default error,
      CHANGELOG is the sole migration channel, no hint/alias/tombstone, the
      silent-misbehavior carve-out). Remove the "Tombstone sunset" clause.
- [ ] 1.2 Resolve `AGENTS.md` §4 ("Errors carry migration hints") — it now
      contradicts §1; reduce to "errors are clear + action-oriented", drop the
      name-version/name-replacement prescription and the `health_tool=` example.
- [ ] 1.3 Scan `AGENTS.md` patterns section (the `__getattr__` migration-hint
      and "loud-crash on unsupported kwargs" examples) — strip the hint-recipe
      framing so the doc no longer prescribes what §1 now forbids.

## 2. Tests RED (assert the plain post-purge errors first)

- [ ] 2.1 For each purged tombstone, rewrite its hint-assertion test to assert
      the language-default error WITHOUT the hint substring: `app.add_router`
      → `AttributeError`; base `App(...)` → `TypeError` "abstract" (no ADR/
      version); `Container.register/resolve/has/...` → `AttributeError`;
      `TestClient.call` / `.override` → `AttributeError`. Delete the
      `_lazy_module` `removed=` test.
- [ ] 2.2 For the aliases: assert old lint codes no longer normalize (a bare
      `A2K-LAYER` noqa does not suppress `AK200`); `AmbientContextMissing` is
      gone (import raises); `SURFACE_REGISTRY` module attr is gone.
- [ ] 2.3 Run; confirm they fail against the still-present hints/aliases.

## 3. Purge tombstones (GREEN)

- [ ] 3.1 `app.py`: delete `add_router`; strip the base-`App` guard message to a
      terse abstract-class error (keep the guard — D1).
- [ ] 3.2 `packages/di/container.py`: delete `_retired` + `_RETIRED_V038` + the
      7 retired method stubs.
- [ ] 3.3 `packages/testing/client.py`: delete `_MIGRATED_NAMES`, `_REMOVED_NAMES`,
      and the `__getattr__` interception branch (keep a plain `__getattr__`
      `AttributeError` only if one is otherwise needed).
- [ ] 3.4 `_lazy_module.py`: delete the `removed=` param, `RemovedHints` type,
      the `_REMOVED` resolution branch, and the `__all__`/docstring references.

## 4. Purge silent aliases (GREEN)

- [ ] 4.1 Migrate the 3 internal legacy noqa comments (`A2K-LAYER`,
      `A2K-PKG-FRONT-DOOR`, `A2K-PKG-INIT-PURITY`) to their `AK###` spellings.
- [ ] 4.2 `packages/lint/static.py`: delete `LEGACY_CODE_ALIASES` + `normalize_code`;
      inline the raw code at the two call sites (`parse_noqa`, `run_static_rules`).
      `packages/lint/_bundle/extract_facts.py`: delete `_REGO_LEGACY_ALIASES` +
      its lookup.
- [ ] 4.3 `exceptions.py`: delete `AmbientContextMissing`; repoint every
      raiser/catcher to `request_scope.RequestScopeMissing`.
- [ ] 4.4 `__init__.py` + readers: delete the module-level `SURFACE_REGISTRY`
      proxy; route readers to the composed `runtime.surfaces` registry.

## 5. Specs (hint-assertion → plain-error)

- [ ] 5.1 Author a MODIFIED delta for each capability whose scenario asserts a
      removed hint message (D3 set), asserting the language-default error and
      dropping the "message names X / gives the rewrite" clauses. Confirm which
      of the ~18 grep matches are real (scenario) vs historical prose (skip).
- [ ] 5.2 `openspec validate purge-compat-debt --strict` passes.

## 6. CHANGELOG (the sole migration channel now)

- [ ] 6.1 New `## Unreleased` entry with a complete migration table: every
      purged surface → its replacement (add_router→routers=, Container.* →
      provide/get/has_provider, TestClient.call→invoke / override→rebuild,
      old lint codes→AK###, AmbientContextMissing→RequestScopeMissing,
      SURFACE_REGISTRY→runtime.surfaces). This is now the ONLY place the
      recipe lives — it must be complete.

## 7. Verify + release

- [ ] 7.1 Full suite green; `make lint` green (ty src / a2kit-lint static incl.
      the migrated noqa / ruff / all three drift gates / openspec-validate /
      markdown / surface snapshots). Grep `src/` for any remaining "was removed"
      / "was retired" / "migration hint" raise strings — should be zero outside
      the silent-misbehavior carve-out.
- [ ] 7.2 Archive the change (applies the spec deltas to canonical).
- [ ] 7.3 Cut `v0.43.0` (breaking; bump pyproject + uv.lock, tag, push main +
      tag). a2web targets v0.43.0.
