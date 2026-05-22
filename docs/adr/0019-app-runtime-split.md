---
id: "0019"
status: accepted
date: 2026-05-22
last_reviewed: 2026-05-22
supersedes: ["0017"]
superseded_by: null
tags: [architecture, di, surface, lifecycle]
deciders: [Denis Tomilin]
---

# ADR 0019: App / AppRuntime split — the sealed runtime is an internal type

## Status

Accepted, 2026-05-22. Supersedes ADR 0017.

## Summary

In the context of ADR 0015's layer manifest — which tiers every
importable unit and lint-enforces the import DAG — facing the fact that
`core` is one undifferentiated 17-module unit with the highest fan-in in
the codebase and zero intra-unit enforcement, and that the single
obstacle to subdividing it is `app.py`, a two-phase class that straddles
a compose layer and a run layer toggled by a private `_sealed` flag, we
decided to split `App` into a compose-phase `App` (keeping the public
name) and an internal sealed-runtime `AppRuntime`, have the finishers
build an `AppRuntime` from an `App` via an internal `build()` that
snapshots into a fresh container, and subdivide `core` into three
lint-enforced sub-units (`kernel` < `authoring` < `runtime`), and
against keeping the sealed runtime as a flag on a single class, to
achieve a `core` that the layer manifest can actually protect, keeping
ADR 0017's consumer contract intact (one public type, three finishers),
accepting a third mechanical migration of the finishers and a broad
test-suite migration off `async with app:`.

## The problem

ADR 0017 collapsed ADR 0016's `AppBuilder` / `App` split back to one
public `App`, making the sealed runtime a private `_sealed` flag. That
was the right call against its forces: the sealed runtime never crosses
the consumer boundary, so a second *public* type is dead structure.

But ADR 0017 predates ADR 0015's layer manifest. The manifest tiers the
internal import graph and lint-enforces it (`A2K-LAYER`). Every package
under `src/a2kit/packages/` is a layered unit; the top-level `a2kit.*`
modules are lumped into one `core` pseudo-unit — the only unit with no
intra-unit enforcement, and the one with the highest fan-in (33).

`core` cannot be subdivided while `app.py` is one class. `App` fuses two
phases: the compose phase (`add_router` / `provide` / `health_check`)
and the sealed run phase (the validated container, the dispatch hook,
the `__aenter__` / `__aexit__` lifecycle). A module that *is* two layers
cannot be assigned to one. The `_sealed` flag is the textbook two-phase
object smell; ADR 0017 accepted it because, at the time, the only force
was the consumer contract. ADR 0015 added a new force: a flag-toggled
two-phase class blocks the layer manifest from doing its job on the
densest, most-churned code in the framework.

A new force warrants a new decision. This ADR supersedes ADR 0017 — not
because ADR 0017 was wrong, but because the forces changed.

## What we considered (and why this one)

### Option 1: Keep ADR 0017's `_sealed` flag

The shipping design. Rejected: it leaves `app.py` straddling two layers,
which blocks subdividing `core`. The densest code in the framework keeps
the least structural protection.

### Option 2: Split the DI `Container` instead

Investigated: extract the compose-time registration methods of
`Container` into a separate type. Dropped — `container.py` is ~90%
irreducible run-phase code; the three compose methods do not earn a
type, and `App` would still straddle two layers regardless.

### Option 3: Split `App` into `App` + internal `AppRuntime` — chosen

`App` keeps the public name and becomes a compose-phase-only builder.
The sealed runtime becomes an internal `AppRuntime` in its own module.
The finishers build one from the other. `core` then subdivides cleanly:
`kernel` (leaf types), `authoring` (the decoration surface), `runtime`
(`app`, `runtime`).

Why it wins: it is the *only* option that lets the layer manifest cover
`core`, and it does so without touching the consumer contract. `App` is
still the one public type; `AppRuntime` is never exported. ADR 0017's
judgement — the sealed runtime must not be a second *public* type — is
honored exactly: `AppRuntime` is internal. ADR 0017 picked a flag for
the internal representation and explicitly said "a future change may
pick otherwise, and that freedom is the point." This is that change.

## The decision

### `App` is the compose-phase builder; `AppRuntime` is the internal runtime

`a2kit.App` carries the composition verbs and the compose container. It
has no `_sealed` flag, no `_seal()`, no `__aenter__` / `__aexit__`. It
is a pure, reusable builder. `AppRuntime` (in `src/a2kit/runtime.py`,
never exported) owns the validated container, the dispatch wiring, and
the async-CM lifecycle.

### `build()` snapshots into a fresh container

A finisher's internal `build(app)` reads the App's registrations, scope
metadata, and wire scopes (via `Container.snapshot()`), constructs a
**fresh** `Container`, validates and seals it, and hands it to a new
`AppRuntime`. It does not seal the App's own container.

The consequence is the load-bearing win: `App` becomes a *true* pure
builder. Post-build composition affects only future builds; it can
never reach a running `AppRuntime`, because the runtime holds its own
snapshot. The bug ADR 0016's `_sealed` guard caught — composition
leaking into a running app — becomes *structurally impossible*. The
guard is therefore deleted, not preserved: it is dead defense once the
leak it guards cannot occur.

`build()` is idempotent on an `AppRuntime`: passing one back returns it
unchanged. The multiplex-serve parent builds the runtime once and hands
the same instance to every surface, so one process enters one lifecycle.

### Finishers own `build()`; there is no public `build()`

`a2kit.run`, `build_mcp_server`, and `a2kit.testing.client` call
`build()` internally, exactly as ADR 0017's finishers called `_seal()`.
Their public signatures are unchanged. Consumers never see `AppRuntime`.

### `core` splits into three lint-enforced sub-units

The layer manifest replaces the `core` pseudo-unit with `kernel` (1) <
`authoring` (2) < `runtime` (3). `app` and `runtime` live in the
`runtime` sub-unit. The re-export facades (`__init__.py`, `ldd.py`,
`testing.py`) are a layer-exempt group. The flat "≤ 12 core files" cap
is retired — the sub-unit manifest is the organizing principle.

### No tombstone for the removed sealed-runtime mechanism

ADR 0018 mandates a loud-crash-with-hint tombstone for removed *public*
API. The removed surface here — `App._seal`, `App._sealed`,
`App._ensure_not_sealed`, `App.__aenter__`, `App.__aexit__` — is not
public. `_seal` / `_sealed` / `_ensure_not_sealed` are underscore-named
framework internals. `App.__aenter__` / `__aexit__` were
framework-internal too: a read-only investigation confirmed every
run-phase entry (`async with app:`, `_resolver`, `_seal`) is reached
only by code under `packages/{cli,mcp,dispatch,serve,testing}` — no
example and no public path entered an `App` directly; the finishers own
the lifecycle. A consumer who reached past the finishers to
`async with app:` now gets a native `TypeError` ("`App` does not
support the asynchronous context manager protocol") — loud, immediate,
and accurate. The whole mechanism is gone; there is no public surface
to tombstone. This is recorded here per ADR 0018's requirement that a
whole-mechanism removal either tombstones or states why it need not.

## Consequences

### Positive

- `core` is subdividable: the layer manifest now covers the framework's
  densest code with `kernel` / `authoring` / `runtime` enforcement.
- `App` is a genuinely pure, reusable builder. Post-build composition
  cannot corrupt a running runtime — the `_sealed` guard's bug is
  structurally impossible, so the guard is gone, not just relocated.
- The consumer contract is unchanged: one public `App`, three finishers,
  identical signatures. `AppRuntime` is invisible.
- ADR 0017's judgement is preserved — the sealed runtime is internal —
  while its internal representation is upgraded from a flag to a type.

### Negative

- Third mechanical migration of the finishers. ADR 0016 then 0017 each
  migrated every composition site; this is a third touch. Accepted: the
  cost of having deferred the layer manifest until after ADR 0017.
- Broad test migration. ~30 test files entered the lifecycle via
  `async with app:` directly on the `App`; all move to
  `async with build(app) as app:`. Mechanical but voluminous — the
  apply step's proposal undercounted this at six tests.
- Post-build composition is silently harmless rather than a loud raise.
  Accepted: under the snapshot model it genuinely is harmless (it
  affects only the next build), so a raise would be dead defense.

## References

- `src/a2kit/app.py` — the compose-phase `App`.
- `src/a2kit/runtime.py` — `AppRuntime` and the internal `build()`.
- `src/a2kit/packages/di/container.py` — `Container.snapshot()`.
- `src/a2kit/__init__.py`, `src/a2kit/packages/mcp/server.py`,
  `src/a2kit/packages/testing/client.py` — the three finishers.
- `src/a2kit/packages/lint/layers.py` — the `kernel` / `authoring` /
  `runtime` sub-units.
- ADR 0017 — one public `App`; this ADR keeps that and supersedes only
  the internal-representation decision.
- ADR 0015 — the layer manifest; the new force that motivates this ADR.
- ADR 0018 — tombstone lifecycle; the no-tombstone rationale above.
- The `split-app-runtime` OpenSpec change.
