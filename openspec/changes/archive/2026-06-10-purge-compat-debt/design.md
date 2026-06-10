# Design — purge-compat-debt

## The inventory (live in `src/`, 2026-06-11 audit)

| # | Item | File | Kind | Purge |
|---|---|---|---|---|
| 1 | `App.add_router` | `app.py` | tombstone | delete → `AttributeError` |
| 2 | `a2kit.App(...)` base construction | `app.py` | **invariant + hint** | keep guard, strip message |
| 3 | `Container._retired()` ×7 DI methods | `packages/di/container.py` | tombstone | delete → `AttributeError` |
| 4 | `TestClient._MIGRATED_NAMES` / `_REMOVED_NAMES` + `__getattr__` | `packages/testing/client.py` | tombstone | delete → `AttributeError` |
| 5 | `_lazy_module` `removed=` / `RemovedHints` / `_REMOVED` branch | `_lazy_module.py` | dead plumbing | delete |
| 6 | `LEGACY_CODE_ALIASES` + `normalize_code` | `packages/lint/static.py` | silent alias | delete (migrate 3 noqa first) |
| 7 | `_REGO_LEGACY_ALIASES` | `packages/lint/_bundle/extract_facts.py` | silent alias | delete |
| 8 | `AmbientContextMissing` | `exceptions.py` | one-release shim | delete → `RequestScopeMissing` only |
| 9 | `SURFACE_REGISTRY` module proxy | `__init__.py` + readers | deprecated proxy | delete |

Not in scope: zero live `DeprecationWarning` exist already (the one `warnings.warn`
in `_list_helpers.py` is a legitimate missing-type-param `RuntimeWarning`).
Architectural duplications (two signature installers, container god-object) are
redesigns, not purges — tracked separately.

## D1. The deletion-safety rule

Deleting a tombstone is safe only when the old call then **errors**. Before
deleting each, confirm the result is a loud Python error, never silent
misbehavior:

- Attribute tombstones (`add_router`, `Container.*`, `TestClient.*`) → the name
  vanishes → `AttributeError`. Safe.
- **Item 2 is the exception.** `if type(self) is App: raise` is a load-bearing
  invariant (App is abstract). Delete the *message archaeology*, keep the guard:
  `raise TypeError("a2kit.App is abstract — author by subclassing (class Kay(a2kit.App): ...) or use a2kit.testing.app_of(...) in tests.")`. No version, no ADR number — a plain abstract-class error. (If the guard were deleted, `a2kit.App("x")` would build a routerless base App and silently do nothing.)
- `normalize_code` is *called* (parse_noqa, run_static_rules); deleting the alias
  table alone leaves it an identity function. Delete the function too and pass the
  raw code at both call sites.

## D2. The new `AGENTS.md` §1 (verbatim replacement)

Replace the whole of §1 (heading through the "Tombstone sunset" clause) with:

> ### 1. No backward compatibility, no migration hints
>
> When a surface is renamed, removed, or restructured, it is **deleted**.
> The old name raises the **language-default** error (`AttributeError` /
> `TypeError` / `ImportError`) — nothing more. No alias, no
> `DeprecationWarning`, no transitional period, no tombstone, and **no
> embedded migration hint**. Do not catch removed kwargs via `**_kw` to
> re-raise a recipe; do not intercept old attribute names in `__getattr__`;
> do not keep a "removed" hint table.
>
> The migration recipe lives in **one** place: the `CHANGELOG.md`
> `Unreleased` section (promoted to the version on release). Every breaking
> change adds a migration-table row there. That is the entire consumer
> contract — a2kit does not spend code on guiding consumers through a
> removal.
>
> **The only carve-out** is a deletion that would otherwise *silently
> misbehave* — a load-bearing invariant, not a compat shim. There, keep a
> plain guard with a terse, present-tense message stating the rule (e.g.
> "`a2kit.App` is abstract; subclass it"). Never a versioned migration
> story; never an ADR citation in a runtime error.
>
> **Reason**: transitional machinery (hints, aliases, tombstones) is
> standing code that documents the past. It hides drift, invites
> re-accumulation, and duplicates what the CHANGELOG already records. The
> consumer is assumed to read release notes; the codebase stays in the
> present tense.

This drops: the renames/removed-kwargs/renamed-methods hint bullets, the
"force migration into commit history" rationale, and the entire "Tombstone
sunset" clause. It keeps the no-alias / no-DeprecationWarning / no-transition
spine. AGENTS.md §4 ("Errors carry migration hints") is also struck or
narrowed — it now contradicts §1 (its `health_tool=` example is exactly the
hint we forbid). Resolve §4 in the same edit: reduce it to "errors are clear
and action-oriented" without the name-the-version/name-the-replacement
prescription.

## D3. Spec deltas — hint-assertion → plain-error

~18 capability specs match the audit grep; only those whose **scenarios assert a
hint message** need a delta. Pattern per delta: MODIFY the requirement so the
scenario asserts the language-default error and drops "AND the message names
X / gives the rewrite". Confirm each at apply time (some matches are historical
prose, no delta). Known deltas: `core-composition`, `in-process-test-client`,
`request-scoped-di` / `thin-core-surface`, `mcp-context-passthrough` /
`dispatch-pipeline`, `surface-protocol` / `serve-topology`, the lint-code-format
capability. Where a spec's requirement *is* "raises with migration hint," it
becomes "raises the language-default error."

## Risks / Trade-offs

- **Worse DX for stragglers, by design.** Old calls get bare `AttributeError`
  instead of "use X". Accepted; CHANGELOG is the contract. Sharpest edge: a2web
  is migrated by an *agent*, for which inline hints were arguably higher-value
  than for a human — this bets the agent reads release notes. The maintainer has
  taken that bet explicitly.
- **CHANGELOG becomes load-bearing.** It is now the *only* migration channel, so
  the purge must add a complete migration table for every removed surface in the
  same change. A missing row = a silent loss of guidance.
- **Governance.** §1 (and §4) rewrite is a Constitution Phase-A edit; it must
  land with the deletions, not before (else the deletions would violate the old
  §1's "embedded hint" mandate) and not after (else the tombstones would violate
  the new §1). One atomic change.
- **Re-accumulation.** With hints gone, the temptation to "just add a quick
  tombstone" returns. Mitigation is cultural (the §1 rewrite) plus the existing
  drift gates; a lint rule forbidding migration-hint strings in raises is a
  possible follow-up but is out of scope here.
- **Scope discipline.** Architectural duplications are explicitly excluded — they
  are redesigns, and folding them in would balloon a 1-day purge into a
  multi-week refactor.
