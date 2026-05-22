---
id: "0016"
status: accepted
date: 2026-05-22
last_reviewed: 2026-05-22
supersedes: []
superseded_by: null
tags: [architecture, di, testing, surface]
deciders: [Denis Tomilin]
---

# ADR 0016: AppBuilder / App split — composition and runtime are distinct types

## Status

Accepted, 2026-05-22.

## Summary

In the context of a2kit's central `App` being a two-phase object — a
mutable builder before `async with app:`, a sealed runtime after — with
the phase boundary invisible to the type system, facing `provide()`
after the seal being a *runtime* raise rather than a compile error and a
distributed test-override seam (`Container._override` / `_snapshot` /
`_restore` driven by `TestClient.override()`) that mutated an
already-sealed container in direct contradiction of ADR 0006, we decided
for splitting `App` into a mutable `AppBuilder` whose terminal `build()`
yields the sealed, mutation-free `App`, and against a `frozen` flag on a
single class, to achieve a lifecycle phase that is a fact in the type
system and a test-override story that is pure composition-root
re-registration, accepting a breaking migration of every composition
site (examples, tests, downstream consumers) and the deletion of the
`Container` snapshot/restore machinery.

## The problem

`App` had two lives separated by `async with app:`.

Before the seal it was a **mutable builder**: `add_router`, `add_cli`,
`add_mcp_middleware`, `provide`, `health_check`. After the seal it was a
**sealed runtime**: `tools()`, `container()`, `_resolver`, the
async-context-manager lifecycle, the LDD kill-switch. One class carried
both roles — seven-plus responsibilities — and the reader could not tell,
from a type, which methods were legal when.

The phase boundary was real (the container seals at `__aenter__` —
ADR 0006) but invisible. `provide()` after the seal raised *at runtime*.
Mutating wiring after entry was a runtime surprise, not a compile error.
This is the textbook two-phase-object smell: an object whose valid
operations depend on an internal mode flag the caller cannot see.

A deeper review surfaced a sharper, second problem. The test-override
seam was a **distributed post-seal mutation mechanism**:
`App._test_override_owner` + `Container._override` / `_snapshot` /
`_restore` + `TestClient.override()`. It overrode an *already-sealed*
container mid-test. ADR 0006 (accepted 2026-05-18) records the exact
opposite: *"there is no in-context override after `async with app:`
because the container is sealed at that point."* The code contradicted
its own four-day-old ADR. Either the ADR was wrong or the code was; the
code was — the seam had grown by accretion, never by decision.

## What we considered (and why this one)

### Option 1: Keep one `App`, add a `frozen` boolean

A `frozen` flag flipped at `__aenter__`; composition verbs raise when
`frozen`.

Why it lost: it keeps the runtime-surprise. `app.provide(...)` still
type-checks after entry — the failure is still a raise, just a
better-explained one. The reader still cannot tell from a type which
methods are legal. It is the status quo with a nicer error message.

### Option 2: One `App`, composition verbs raise after entry (status quo)

The shipping behaviour. Rejected for the same reason as Option 1, plus:
it gives the test-override seam nowhere to go. As long as one object is
both builder and sealed runtime, "override after seal" remains
expressible, and the contradiction with ADR 0006 stands.

### Option 3: Two types — `AppBuilder` (mutable) + `App` (sealed) — chosen

`AppBuilder` carries every composition verb and a terminal
`build() -> App`. `App` carries only the runtime surface and has no
`provide` to call. The phase becomes a **compile-time fact**: the sealed
`App` simply does not have the mutating methods. Misuse — constructing
`a2kit.App(...)` directly, or calling a verb on a built `App` — crashes
loud with a migration hint per AGENTS.md "no backward-compat shims".

Why it wins: it is the Builder pattern done properly — a distinct
builder type whose terminal method yields the immutable product. It
makes the two-phase shape visible in the type system instead of hidden
behind a flag. And it gives the test-override seam a principled
replacement (see below) that finally makes ADR 0006 true.

## The decision

### Two types, `build()` is the seal point

`a2kit.AppBuilder(name, *, debug=False)` is the mutable composition
surface: `add_router`, `add_cli`, `add_mcp_middleware`, `provide`,
`health_check`. Each verb returns the builder for chaining.

`AppBuilder.build() -> App` is the seal point. It constructs the sealed
`App` over the builder's state, validates the DI provider graph
(rejecting app-scope factories that depend on per-call types — the check
`Container.__aenter__` already did), and seals the container against
further `provide()`. A builder produces exactly one `App`; a second
`build()`, or any verb after `build()`, raises.

`a2kit.App` is the sealed runtime: `tools()`, `routers()`,
`container()`, the async-context-manager lifecycle, the LDD kill-switch.
No composition verb. `App.__aenter__` keeps today's lazy-first-use
resource entry unchanged — `build()` validates, entry still resolves
lazily.

Both types live in `src/a2kit/app.py` — no new core source file
(the core-file-count budget in `module-layout-discipline` is tight).

### Old surface crashes loud

Per AGENTS.md "no backward-compat shims": `a2kit.App(...)` direct
construction raises `TypeError` naming `AppBuilder(...).build()`. A
composition verb on a built `App` raises `TypeError` (via `__getattr__`)
with the same hint. No alias, no deprecation window.

### Test overrides become re-build; the Container does not split

ADR 0006 chose composition-root re-registration over a dedicated
override seam. The code grew one anyway. With `AppBuilder`, a test that
wants `StubLLM` instead of `RealLLM` calls `builder.provide(LLM,
StubLLM)` (last-write-wins) and `build()`s a fresh `App`. That is pure
re-registration — exactly what ADR 0006 prescribes — so the
snapshot/restore machinery (`Container._override` / `_snapshot` /
`_restore` / `_ContainerSnapshot`), the `App._test_override_owner` flag,
and `TestClient.override()` are **deleted, not ported**. The removed
`TestClient.override` raises a migration hint pointing at the re-build
recipe.

The `Container` itself is *not* split. It is two-phase (mutable
`provide` → sealed `seal()`), but `AppBuilder` / `App` is precisely the
public expression of those two phases: `AppBuilder` owns the container
while mutable, `build()` seals it. The container's internal two-phase
shape needs no separate builder type once the public surface has one.
`Container.seal()` is the new public seal point; the root container's
`__aenter__` still calls it (idempotent) as defence in depth.

### This makes ADR 0006 true

ADR 0006 stays accepted — its decision (no dedicated `override()`
method; overrides are re-registration) is now not just recorded but
*enforced* by the type system. This ADR is the structural change that
removes the code which contradicted it.

### Transport-neutral core — considered, deferred

`add_mcp_middleware` is MCP-specific surface on a transport-neutral
composition root. Generalising it to `add_extension(transport, obj)` was
considered and **deferred**: there are exactly two transport verbs
(`add_cli`, `add_mcp_middleware`), both explicit and single-purpose,
matching `core-composition`'s "three named verbs, no polymorphic
dispatch" intent. A generic `add_extension` would reintroduce the
polymorphic dispatch the project deliberately removed. Parked in
`BACKLOG.md` (Thread E) with trigger "a third transport adapter is
added".

## Consequences

### Positive

- The lifecycle phase is a compile-time fact. The sealed `App` has no
  `provide`; "can I still wire this?" is answered by the type, not by a
  runtime raise.
- One responsibility per type: `AppBuilder` composes, `App` runs.
- The test-override seam is re-build, not post-seal mutation. ~50 LOC of
  distributed coupling (`_override` / `_snapshot` / `_restore` /
  `_ContainerSnapshot` / `_test_override_owner`) is deleted, and
  ADR 0006's recorded invariant is finally true in the code.
- Misuse (`a2kit.App(...)`, a verb on a built `App`) crashes loud with a
  migration hint instead of failing silently or late.

### Negative

- Largest blast radius of the post-explore architecture wave: every
  `a2kit.App(...)` construction site — every example, the whole test
  suite, downstream consumers — migrates to
  `a2kit.AppBuilder(...).build()`.
- Two public names where there was one (`AppBuilder` and `App`). The
  Tier-1 surface (ADR 0004) grows by one entry — judged worth it: the
  builder is a name essentially every tool author uses.
- Tests lose the ability to swap a binding *mid-session*. A test that
  needs that builds a second `App` from a second builder — "composition
  is cheap, reset is loud", consistent with ADR 0006's own consequence
  note.

## References

- `src/a2kit/app.py` — `AppBuilder`, `App`, `_default_dispatch_hook`.
- `src/a2kit/packages/di/container.py` — `Container.seal()`; the
  deleted `_override` / `_snapshot` / `_restore` / `_ContainerSnapshot`.
- `src/a2kit/packages/testing/client.py` — `TestClient` without the
  override seam; the `override` migration hint.
- ADR 0006 — no dedicated `app.override()` test seam. This ADR removes
  the code that contradicted it and makes its invariant enforceable.
- ADR 0004 — audience-tiered public surface; `AppBuilder` joins Tier 1.
- ADR 0009 — `per_call=True` scoping; `build()` runs the scope-graph
  validation that gates it.
- The `split-app-builder-runtime` OpenSpec change.
