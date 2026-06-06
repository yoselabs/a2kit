## ADDED Requirements

### Requirement: `validate_composition(app)` resolves the surfaces matrix and canonical names without a full build

a2kit SHALL expose a standalone `validate_composition(app)` function that
resolves the projection state of a compose-phase `App` **without
performing a full surface build**. It MUST NOT seal the App's container,
MUST NOT re-materialize wire/lazy descriptor fields, and MUST NOT
construct any transport (FastAPI / FastMCP / Typer) object. For every
projection verb on the App (app-level verbs and every router's verbs),
the function SHALL resolve both:

- the `surfaces`/`expose` matrix (which surfaces the verb appears on), and
- the **canonical name** of the verb, via the single shared
  `resolve_canonical_name` resolver (the same resolver the static
  dup-name lint rule uses).

The function SHALL be callable directly against a compose-phase `App`
(the object returned by `a2kit.App(...)` after `add_router`/`provide`
calls), so a unit test MAY assert that an App composes cleanly without
standing up a runtime. On success the function SHALL return normally
(no exception); the return value carries no transport state.

#### Scenario: Validator runs on a compose-phase App with no build

- **GIVEN** an `App` composed with one or more routers via `add_router`
- **AND** the App has **not** been handed to any finisher (`build()` was never called)
- **WHEN** user calls `validate_composition(app)`
- **THEN** the call completes without raising
- **AND** no transport object (FastAPI / FastMCP / Typer) was constructed
- **AND** the App's compose-phase container is left unsealed and mutable

#### Scenario: Validator resolves a canonical name for every verb

- **GIVEN** an `App` with an app-level verb `health` and a router `Entity(slug="entity")` whose verbs are `update` and `search`
- **WHEN** `validate_composition(app)` resolves canonical names
- **THEN** the app-level verb resolves to the bare leaf `health`
- **AND** each router verb resolves through `resolve_canonical_name` to its `slug_leaf` form (`entity_update`, `entity_search`) unless a `canonical_name_override` pins it verbatim

#### Scenario: Validator surfaces the same surface-name check as build

- **GIVEN** an `App` with a verb whose `surfaces`/`expose` names an unknown surface
- **WHEN** `validate_composition(app)` runs
- **THEN** it reports the unknown-surface error for that verb, matching the check `build()` performs today
- **AND** the error is available **without** calling `build()`

### Requirement: `validate_composition` asserts global canonical-name uniqueness and fails loud

`validate_composition(app)` SHALL assert that no two projection verbs
resolve to the same canonical name **globally** — across all routers and
all app-level verbs, **independent of which surface each verb appears
on**. Uniqueness MUST NOT be scoped per-surface: a verb present only on
the CLI and a verb present only on MCP that resolve to the same canonical
name SHALL be reported as a collision, because the canonical name is the
single shared call-journal/audit key (ADR 0028 decision 6).

On detecting a collision the function SHALL **fail loud** by raising,
naming the colliding canonical name and **both** offending verbs (each
identified by its router slug — or app-level — plus leaf), so the
diagnostic points directly at the duplicate. The function MUST NOT
silently pick a winner, MUST NOT rename, and MUST NOT defer the failure
to first dispatch.

This runtime assertion is the **backstop layer** (layer 2) over the
single `resolve_canonical_name` resolver; the **static dup-name lint
rule** (layer 1) consumes the same resolver and lives in the separate
`ruff-compatible-lint-codes` change. The two layers SHALL therefore agree
on every resolved name by construction. The runtime layer additionally
catches **dynamically-named** verbs that the static linter cannot resolve
ahead of time.

#### Scenario: Two verbs resolving to the same canonical name fail loud

- **GIVEN** an `App` where router `A(slug="a")` has a verb pinned `canonical_name_override="dup"` and router `B(slug="b")` has a verb also pinned `canonical_name_override="dup"`
- **WHEN** user calls `validate_composition(app)`
- **THEN** the call raises
- **AND** the error names the colliding canonical name `dup`
- **AND** the error identifies both offending verbs (router slug + leaf for each)

#### Scenario: Global uniqueness ignores per-surface placement

- **GIVEN** a verb `foo` present only on the CLI (`surfaces=("cli",)`) and a different verb that resolves to canonical name `foo` present only on MCP (`surfaces=("mcp",)`)
- **WHEN** `validate_composition(app)` runs
- **THEN** the two verbs are reported as a canonical-name collision
- **AND** the report does **not** treat disjoint surfaces as resolving the ambiguity (the audit key is global)

#### Scenario: A uniquely-named composition passes

- **GIVEN** an `App` where every verb resolves to a distinct canonical name (auto-derived `slug_leaf` plus any verbatim overrides)
- **WHEN** `validate_composition(app)` runs
- **THEN** the call returns normally with no exception

#### Scenario: A dynamically-named verb collision is caught at runtime

- **GIVEN** an `App` containing a verb whose canonical name is produced dynamically (a value the static linter cannot resolve) that collides with another verb's canonical name
- **WHEN** `validate_composition(app)` runs
- **THEN** the collision is detected and the call fails loud
- **AND** this is the case the static lint layer (layer 1) cannot catch, justifying the runtime backstop
