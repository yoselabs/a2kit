---
id: "0017"
status: superseded
date: 2026-05-22
last_reviewed: 2026-05-22
supersedes: ["0016"]
superseded_by: "0019"
tags: [architecture, di, testing, surface]
deciders: [Denis Tomilin]
---

# ADR 0017: One public App — the sealed runtime is internal

## Status

Superseded by ADR 0019, 2026-05-22.

Accepted 2026-05-22; superseded the same day. ADR 0017's core
judgement — the sealed runtime never crosses the consumer boundary, so
it must not be a second *public* type — still holds, and ADR 0019 keeps
it: `App` stays the one public name. What ADR 0019 changes is the
sealed runtime's *internal* representation. ADR 0017 made it a private
`_sealed` flag on `App`; ADR 0015's layer manifest (a force ADR 0017
never weighed) later showed that a flag-toggled two-phase `App` cannot
sit in a single layer. ADR 0019 splits the runtime into an internal
`AppRuntime` type — invisible to consumers, exactly as ADR 0017
required — to let the layer manifest subdivide `core`. See ADR 0019.

## Summary

In the context of ADR 0016's `AppBuilder` / `App` split, facing the fact
that the two-class split only earns its keep if the sealed type
*crosses the consumer boundary* — and it does not, because a2kit funnels
every "finish" through an entry point (`a2kit.run`, `build_mcp_server`,
`a2kit.testing.client`) — we decided to collapse `AppBuilder` and `App`
back into one public `a2kit.App`, make the sealed runtime an internal
`_sealed` flag, drop the public `build()`, and have the finishers seal
the App internally, and against guarding a boundary crossing that need
not exist, to achieve the smallest honest framework⇄consumer contract
(one type plus the entry functions), keeping every behavioural win of
ADR 0016 (the container seal, the provider-graph validation, the deleted
test-override seam), accepting a second mechanical migration of every
composition site hours after the first.

## The problem

ADR 0016 split a2kit's central type into a mutable `AppBuilder` and a
sealed, mutation-free `App`, with a terminal `build()` as the seal
point. The motivating problem was real — a two-phase object whose valid
operations depend on a hidden mode flag is the textbook two-phase-object
smell — and the seal-side wins (provider-graph validation, the deletion
of the `Container._override` / `_snapshot` / `_restore` machinery) were
genuine.

But the *structural* fix over-reached. A separate sealed type buys
exactly one thing: the consumer's editor and type-checker stop them
mutating the runtime after the seal. That payoff only exists if a
consumer ever *holds* the sealed type. And in a2kit, none does.

a2kit already routes every "finish" through a framework entry point:

```
        compose                          finish
  a2kit.App(...) ──add_router──provide──▶ a2kit.run(app)
                                          build_mcp_server(app)
                                          a2kit.testing.client(app)
```

The consumer constructs the App, wires it, and hands it to one of three
functions. The sealed runtime — whatever it is — is produced and held
*inside* those functions. Nothing untrusted ever holds it. ADR 0016 paid
a second public type, a public `build()`, and a `build()`-shaped
migration of every call site to protect a boundary that the framework's
own entry-point shape already closes.

AGENTS.md principle 3 — "no dead defensive structure against types the
framework itself controls" — names this directly. The sealed type was
defending framework code against framework code.

## What we considered (and why this one)

### Option 1: Keep ADR 0016's two types

The shipping design. Rejected: it carries a public type and a public
`build()` whose only justification is a consumer-boundary crossing that
does not happen. The cost (two Tier-1 names, a `build()` call at every
site) is paid; the benefit is unrealised.

### Option 2: Collapse to one `App`, sealed runtime internal — chosen

One public `a2kit.App`. It is the mutable composition object. Sealing
flips a private `_sealed` flag and locks the container; the finishers do
it internally. There is no public `build()` and no second type.

Why it wins: the consumer holds exactly one object across the App's
whole life, and the framework⇄consumer contract is the smallest honest
shape — one type plus three entry functions. The entire sealed-runtime
mechanism (the seal point, the validation, the runtime representation)
becomes a framework implementation detail, free to change without ever
breaking consumer code. ADR 0016's behavioural wins are *kept* — the
container still seals, the graph is still validated, the override seam
stays deleted; only ADR 0016's public *structure* is undone.

### Option 3: One `App`, a private sealed *class* held internally

Collapse the public surface but still build a distinct private runtime
class inside the finishers.

Why it lost: with no consumer holding it, a private class is ceremony
for no reader benefit. The only code that could mutate post-seal is
framework code, which is trusted and tested. A `_sealed` boolean plus a
loud raise on the composition verbs is sufficient and simpler. The
runtime representation is explicitly *not* contract — this ADR picks the
flag; a future change may pick otherwise, and that freedom is the point.

## The decision

### One public type, `a2kit.App`

`a2kit.App(name, *, debug=False)` is the single public composition type.
It carries the composition verbs (`add_router`, `add_cli`,
`add_mcp_middleware`, `provide`, `health_check`, each chainable) and the
runtime surface (`tools`, `routers`, `container`, the async-CM
lifecycle, the LDD kill-switch). `a2kit.AppBuilder` is removed.

### The sealed runtime is a private flag, not a type

Sealing flips a private `App._sealed` and calls `Container.seal()`
(provider-graph validation + registration lock). No separate class. The
runtime representation is a framework implementation detail, outside the
consumer contract.

### Finishers seal; there is no public `build()`

`a2kit.run`, `a2kit.packages.mcp.build_mcp_server`, and
`a2kit.testing.client` accept an `App` and call the internal
`App._seal()` before running / serving / testing. `_seal()` is
idempotent, so one `App` may be handed to more than one finisher and
reused across test sessions — there is no "spent builder" state. No
public `build()` exists; consumer code never calls a seal step.

### Composition after sealing is a loud-crash

A composition verb called on an `App` a finisher has already sealed
raises `TypeError` with an action-oriented hint. This is a same-object,
same-consumer misuse ("you wired it after you ran it") — a runtime raise
is the right tool, consistent with AGENTS.md "no silent errors" and the
existing sealed-container message. ADR 0016 bought a *compile-time*
guarantee here; this change trades it for a runtime crash, because the
guarantee only ever mattered at a consumer boundary that no longer
carries the sealed object.

### `a2kit.run(app)` stays a free function

`app.run()` as a method — the most literal "looks like FastMCP" shape —
is deferred. Putting a transport verb on the composition type is a
separate decision; the free function `a2kit.run(app)` already delivers
the one-object-plus-one-finisher contract. Parked, not in scope.

### ADR 0006 stays honored

Test overrides remain composition-root re-registration: construct a
fresh `a2kit.App`, `provide` the fake last (last-write-wins). The
post-seal override seam stays deleted. ADR 0006's examples — which
already wrote `a2kit.App(...)` directly — are correct again under this
design without edits.

## Consequences

### Positive

- The framework⇄consumer contract is its smallest honest form: one
  type, `a2kit.App`, plus three entry functions.
- The sealed-runtime mechanism — seal point, validation, runtime
  representation — is fully internal and free to change without
  breaking consumer code.
- One object for the App's whole life. No `build()` call, no second
  name to learn; the Tier-1 surface (ADR 0004) shrinks back by one.
- Idempotent sealing dissolves ADR 0016's single-use-builder friction:
  an `App` is reusable across finishers and test sessions.
- Every behavioural invariant of ADR 0016 is retained — the container
  seals, the provider graph is validated, the override seam stays gone.

### Negative

- Re-migration churn. Every composition site moves
  `AppBuilder(...).build()` → `App(...)`, re-touching the sites
  `split-app-builder-runtime` migrated hours earlier. Accepted: the
  sites are mechanical and this is the *last* such migration.
- Post-seal mutation is a runtime raise, not a compile error. Accepted:
  the compile-time guarantee only mattered at a consumer boundary that
  no longer carries the sealed object.
- ADR 0016 is superseded the same day it was accepted. This is the
  decision log working as intended — a fast revisit because the cost of
  the original call was caught fast — not thrash. The append-only log
  records both, linked by `superseded_by`.

## References

- `src/a2kit/app.py` — the single `App`, `_seal()`,
  `_default_dispatch_hook`.
- `src/a2kit/packages/di/container.py` — `Container.seal()`.
- `src/a2kit/__init__.py`, `src/a2kit/packages/mcp/server.py`,
  `src/a2kit/packages/testing/client.py` — the three finishers that
  seal internally.
- ADR 0016 — the `AppBuilder` / `App` split this ADR supersedes. Its
  behavioural wins are kept; its public structure is undone.
- ADR 0006 — no dedicated test-override seam; stays honored, its
  examples correct again under the one-`App` model.
- ADR 0004 — audience-tiered public surface; the Tier-1 surface shrinks
  back by one name.
- The `internalize-app-runtime` OpenSpec change.
