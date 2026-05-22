---
id: "0018"
status: accepted
date: 2026-05-22
last_reviewed: 2026-05-22
supersedes: []
superseded_by: null
tags: [architecture, surface, governance, testing]
deciders: [Denis Tomilin]
---

# ADR 0018: Tombstone lifecycle — birth, shape, and death of removed-surface markers

## Status

Accepted, 2026-05-22.

## Context

AGENTS.md mandates that a removed public API leaves a *tombstone*: a
loud-crash-with-hint that names the removed surface, its replacement,
and the version. That doctrine specifies a tombstone's **birth** but
nothing else — not its shape, not its death. Three gaps followed.

First, tombstones have no defined end. A v0.33 tombstone is still in
the tree at v0.40. Nothing says when one may be deleted, so none ever
are; they accumulate.

Second, tombstone behaviour leaked into *living* capability specs.
Specs such as `test-container-peek` and `app-builder-runtime` carry
Requirements like "the removed `TestClient.override` raises a migration
hint". A living capability spec describes the *current* surface; a
tombstone is by definition not current surface. Encoding it as a
standing Requirement is drift by construction — when the delivery
mechanism is itself removed, the spec still claims it.

Third, when a whole capability is superseded (ADR 0016 → 0017
collapsed `AppBuilder`), it was unclear whether its
`openspec/specs/<cap>/spec.md` should be deleted or kept as an emptied
husk of `REMOVED` requirements.

This ADR closes all three. It is the doctrine companion to the
`spec-drift-gate` capability (the mechanical SPEC↔code check landed in
the same change).

## Decision

### 1. Tombstones are permanent, but cheap by being data-driven

A removed public name keeps its loud-crash-with-hint **indefinitely**.
A consumer pinned to an old version may upgrade years later; it must
hit the named hint, not an opaque `AttributeError`. There is no
"death" for the *guarantee*.

"Permanent" is affordable only when the *mechanism* is data-driven:
one registry mapping removed-name → (replacement, version) plus one
module-level `__getattr__` that raises from it. A removed name becomes
a row in a dict, not a hand-written raise-stub per method. The
existing `_REMOVED_IN_V033` dict in `a2kit/__init__.py` and the
`_REMOVED_NAMES` map in the testing client are the correct shape;
per-method stub functions are not.

The cheap exception: a tombstone for an import path that **never
shipped** in a tagged release guards nothing and is deleted outright
(this is what removed the orphaned `codemode.run_code` `__getattr__`
branch — the `codemode` package post-dates the path's last home).

### 2. Removed-surface behaviour is not a living-spec Requirement

A tombstone's "raises with a hint" behaviour, if specced at all, is a
short-lived `ADDED` requirement **in the change that removes the
surface**, then `REMOVED` from that capability a couple of minors
later once no consumer is plausibly still mid-migration. It never
lives as a standing Requirement in a living capability spec.

The `test-container-peek` and `app-builder-runtime` specs that today
carry tombstone-as-Requirement text are the anti-pattern this rule
names. The `reconcile-stale-specs` change removes them.

### 3. A superseded capability spec is deleted, not emptied

When a whole capability is superseded, its
`openspec/specs/<cap>/spec.md` file is **deleted** from the spec tree.
The deletion is recorded in the superseding change's spec delta as
`## REMOVED Requirements` with **Reason** and **Migration** lines. It
is not left as a husk of `REMOVED` requirements.

`openspec/specs/` is the catalogue of *what a2kit does today*. A husk
file is permanent drift bait — the spec-drift gate would have to
allowlist every dead symbol in it forever — and misleads any reader or
tool that enumerates the directory. The OpenSpec archive
(`openspec/changes/archive/`) already preserves the full history of
the superseded capability, so deletion loses nothing: the record
lives in the archive, the catalogue stays honest.

## Consequences

### Positive

- Tombstone "permanence" is decoupled from maintenance cost — a
  registry row, not a function.
- Living specs describe only current surface; the spec-drift gate can
  trust that a backtick symbol in a living spec is a *claim*, not a
  documented absence.
- The spec tree is a clean catalogue: one file per live capability,
  no husks.

### Negative

- `reconcile-stale-specs` inherits real work: stripping
  tombstone-as-Requirement text from `test-container-peek` /
  `app-builder-runtime`, and deleting any fully-superseded capability
  spec file.
- A removed name's hint text is now also a registry-data concern —
  changing a hint means editing a dict value, which is fine, but the
  hint is no longer co-located with a function the reader might grep.

## References

- AGENTS.md — the "no backward-compat shims; removed surface
  tombstones" doctrine this ADR completes.
- The `spec-drift-gate` capability and `tests/test_spec_symbol_drift.py`
  — the mechanical SPEC↔code gate landed alongside this ADR.
- ADR 0016 / 0017 — the `AppBuilder` supersession that raised the
  "delete or empty the spec?" question (decision 3).
- `a2kit/__init__.py` `_REMOVED_IN_V033`, the testing client's
  `_REMOVED_NAMES` — the data-driven tombstone shape (decision 1).
- The `add-spec-drift-gate` and `reconcile-stale-specs` OpenSpec
  changes.
