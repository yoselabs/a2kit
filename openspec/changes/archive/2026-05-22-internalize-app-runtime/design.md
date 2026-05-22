## Context

`split-app-builder-runtime` (ADR 0016) made the two-phase lifecycle a
compile-time fact by splitting one `App` into a mutable `AppBuilder` and
a sealed `App`. The motivating problem it named was real — a two-phase
object whose valid operations depend on a hidden mode flag — but the
fix over-reached. The two-class split only earns its keep if the sealed
type **crosses the consumer boundary**: only then does "the consumer's
editor stops them mutating it" buy anything.

It does not have to cross that boundary. a2kit already funnels every
"finish" through an entry point — `a2kit.run` (production), `build_mcp_server`
(embed), `a2kit.testing.client` (test). If those entry points seal the
App internally, the consumer holds only the mutable object; the sealed
runtime is produced and held entirely inside the framework. Nothing
untrusted ever holds it, so there is nothing for a separate sealed type
to protect — and AGENTS.md principle 3 explicitly rejects defensive
structure against types the framework itself controls.

This change removes the boundary crossing instead of guarding it. The
result is the smallest honest framework⇄consumer contract: one type,
`a2kit.App`, plus the entry functions.

## Goals / Non-Goals

**Goals:**

- One public composition type, `a2kit.App` — constructed, wired, handed
  to a finisher. No second public type, no public seal step.
- The sealed-runtime mechanism (seal point, validation, runtime
  representation) is entirely internal — free to change without
  breaking consumer code.
- Keep every behavioural invariant `split-app-builder-runtime`
  established: the container still seals, the provider graph is still
  validated, the post-seal test-override seam stays deleted.

**Non-Goals:**

- Not re-introducing `TestClient.override` or `Container._override` /
  `_snapshot` / `_restore`. Those stay deleted; ADR 0006 stays honored.
- Not changing DI semantics, lifecycle order, or lazy-first-use entry.
- Not deciding `a2kit.run(app)` vs `app.run()` — see D6, deferred.
- Not renaming the `app-builder-runtime` capability folder (the name is
  organizational; "builder" is now an internal concept).

## Decisions

### D1. One public type, named `App`

`a2kit.App` is the single public composition type. It is constructed
directly (`a2kit.App("svc")`), carries the composition verbs
(`add_router`, `add_cli`, `add_mcp_middleware`, `provide`,
`health_check`, each chainable), and is what the consumer holds from
construction through to handing it to a finisher. `a2kit.AppBuilder` is
removed.

### D2. The sealed runtime is a private `_sealed` flag, not a type

Sealing flips a private `_sealed` flag on `App` and seals the container.
There is no separate runtime class. ADR 0016's two-class split existed
to make post-seal mutation a *type* error for consumers; with the
consumer no longer holding the sealed object, a runtime flag is
sufficient — the only code that could mutate post-seal is framework
code, which is trusted and tested. The two-phase object is acceptable
precisely because the two phases no longer both face the consumer: the
consumer interacts only with the mutable phase, then lets go.

The runtime representation (flag vs. private class) is explicitly an
internal detail — this change picks the flag; a future change may pick
otherwise, and that is the point: it is no longer contract.

### D3. Finishers seal; there is no public `build()`

`a2kit.run`, `a2kit.packages.mcp.build_mcp_server`, and
`a2kit.testing.client` accept an `App` and call the internal
`App._seal()` before running / serving / testing. `_seal()` validates
the provider graph and locks the container; it is idempotent. No
public `build()` exists. Consumer code never calls a seal step.

### D4. `_seal()` is idempotent, so an `App` is reusable across finishers

Because sealing is idempotent and finishers only *read* the sealed App,
one `App` can be passed to more than one finisher and reused across
test sessions. This dissolves the single-use-builder friction the
`AppBuilder` design carried (a builder was spent after one `build()`):
there is no "spent" state, only "sealed", and sealed is reusable.
Per-test isolation is the normal fresh-`App`-per-test pytest fixture.

### D5. Post-seal composition raises a loud-crash

Calling a composition verb on an `App` a finisher has already sealed
raises `TypeError` with a migration hint. This is a same-object,
same-consumer misuse ("you wired it after you ran it") — a runtime
raise is the right tool, consistent with AGENTS.md "no silent errors"
and the existing sealed-container message.

### D6. `a2kit.run(app)` stays a free function — `app.run()` deferred

`builder.run()` / `app.run()` as a method would be the most literal
"looks like FastMCP" shape. It is deferred: putting a transport verb on
the composition type is a separate decision, and the free function
`a2kit.run(app)` already delivers the one-object-plus-one-finisher
contract. Parked; not in scope here.

### D7. Supersedes ADR 0016

A new ADR records the narrowed contract and marks ADR 0016 as
superseded (`superseded_by`). ADR 0016's behavioural wins — the seal,
the deleted override seam — are retained; only its *public structure*
(two types, public `build()`) is undone. ADR 0006 stays honored: test
overrides are still re-build, now expressed as "construct a fresh
`App`".

## Risks / Trade-offs

- **Re-migration churn.** Every composition site moves
  `AppBuilder(...).build()` → `App(...)` — re-touching the sites
  `split-app-builder-runtime` migrated three hours earlier. Accepted:
  the sites are mechanical, the repo is solo, and this lands on a
  contract there is no reason to move again. It is the *last* such
  migration.
- **Post-seal mutation is a runtime raise, not a type error.** ADR
  0016 bought a compile-time guarantee here; this change trades it back
  for a runtime crash. Accepted: the guarantee only ever mattered at
  the consumer boundary, and that boundary no longer carries the
  sealed object. Defending framework code against itself is the dead
  defense AGENTS.md principle 3 forbids.
- **ADR churn.** ADR 0016 is superseded ~hours after acceptance. This
  is the decision log working as intended — a fast revisit because the
  cost of the original call was caught fast — not thrash. The
  append-only ADR system records both, with `superseded_by` linking
  them.
- **Capability name drift.** The `app-builder-runtime` capability keeps
  its folder name though "builder" is now internal. Renaming a
  capability folder is friction for no consumer-visible gain; the name
  is left as organizational debt, noted here.
