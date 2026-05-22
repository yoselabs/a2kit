## Context

`App` has two lives separated by `async with app:`. Before the seal it
is a mutable builder; after, an immutable runtime. ADR 0006 already
records that the container seals at `__aenter__` and that re-registration
must happen at the composition root before entry. The type system says
nothing about this — `provide()` after seal is a runtime raise, not a
compile error.

This is the classic two-phase-object smell. The fix is the Builder
pattern done properly: a distinct builder type whose terminal method
yields the sealed runtime.

The deeper review found a second motivation. The test-override seam —
`App._test_override_owner` + `Container._override` / `_snapshot` /
`_restore` + `TestClient.override()` — overrides a *sealed* container
mid-test. ADR 0006's Y-statement says that cannot happen. The code and
the ADR disagree. The builder/runtime split is the lever that fixes
both at once.

## Goals / Non-Goals

**Goals**

- The phase ("can I still wire this?") is a fact in the type system.
- `App` — the thing handed to `run()` / `build_mcp_server()` — has no
  mutating surface.
- One responsibility per type: `AppBuilder` composes; `App` runs.
- The test-override seam is re-build, not post-seal mutation —
  reconciling code with ADR 0006.

**Non-Goals**

- Not changing DI semantics, lifecycle order, or lazy-first-use entry —
  `build()` validates, `__aenter__` still does lazy resource entry.
- Not adding a new core source file (`AppBuilder` lives in `app.py`).
- Not splitting the `Container` (see D6).
- Not generalizing the transport verbs (see D5 — deferred).

## Decisions

### D1. Two types, not a mode flag or a frozen-after-enter guard

A `frozen` boolean on one `App` would keep the runtime-surprise. Two
types make the phase a compile-time fact: the sealed `App` simply has
no `provide` to call.

### D2. `build()` is the seal point

`AppBuilder.build()` constructs the `Container`, validates the provider
graph (rejecting app-scope factories that depend on per-call types —
the check `Container.__aenter__` does today), auto-installs the
`_meta.health` router when checks were registered, and returns `App`.
`App.__aenter__` keeps today's lazy-first-use resource entry.

### D3. Old surface crashes loud with a hint

Per AGENTS.md "no backward-compat shims": `a2kit.App(...)` direct
construction and composition verbs on a built `App` raise `TypeError`
naming `AppBuilder` and the new call shape. No alias, no deprecation
window.

### D4. `health_check` is a builder method

Registering a probe is composition. It stays on `AppBuilder`; the
`_meta.health` router is materialized inside `build()`, not lazily on
first registration — keeping all router installation at the seal point.

### D5. Thread E — transport-neutral core — considered, deferred

`add_mcp_middleware` is MCP-specific surface on a supposedly
transport-neutral composition root. Generalizing it to
`add_extension(transport, obj)` was considered and **deferred**:

- There are exactly two transport verbs (`add_cli`,
  `add_mcp_middleware`), both explicit, both single-purpose. This
  matches `core-composition`'s "three named verbs, no polymorphic
  dispatch" intent — a generic `add_extension` would *reintroduce*
  polymorphic dispatch the project deliberately removed.
- The generalization pays off only at a third transport. Until then it
  is speculative.

Parked in BACKLOG with trigger "a third transport adapter is added".

### D6. Test overrides become re-build; the Container does not split

ADR 0006 chose "re-registration, not a dedicated override seam." Yet
the code grew one anyway — `Container._override` / `_snapshot` /
`_restore` driven by `TestClient.override()`, mutating a sealed
container. With `AppBuilder`, a test that wants `StubLLM` instead of
`RealLLM` calls `builder.provide(LLM, StubLLM)` (last-write-wins) and
`build()`s a fresh `App`. That is pure re-registration — exactly what
ADR 0006 prescribes — so the snapshot/restore machinery and the
`_test_override_owner` flag are deleted, not ported.

The `Container` itself is *not* split. It is two-phase (mutable
`provide` → sealed `__aenter__`), but `AppBuilder` / `App` is precisely
the public expression of those two phases: `AppBuilder` owns the
container while mutable, `build()` hands it over, `App.__aenter__`
seals it. The container's internal two-phase shape needs no separate
builder type once the public surface has one.
