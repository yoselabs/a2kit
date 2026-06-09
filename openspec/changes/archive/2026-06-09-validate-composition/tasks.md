# Tasks — validate-composition

BDD-first / TDD red → green. The global canonical-name **collision** test
is a first-class RED scenario: it must fail (no validator exists / no
uniqueness check) before any implementation, then pass once the backstop
lands.

## 1. Prove the gap (RED)

- [x] 1.1 **Global-uniqueness collision (the headline RED).** Add a test:
      build an `App` with two routers (`A(slug="a")`, `B(slug="b")`),
      each carrying a verb pinned `canonical_name_override="dup"`. Call
      `validate_composition(app)` and assert it raises, with the message
      naming the canonical name `dup` and **both** offending verbs
      (slug + leaf each). Confirm it FAILS today (no
      `validate_composition`, no uniqueness assertion).
      → `test_global_canonical_name_collision_fails_loud`.
- [x] 1.2 **Per-surface placement does NOT rescue a collision.** Add a
      test: verb `foo` on `surfaces=("cli",)` and a different verb that
      resolves to `foo` on `surfaces=("mcp",)`. Assert
      `validate_composition(app)` still reports the collision (audit key
      is global, not per-surface). Confirm RED today.
      → `test_disjoint_surfaces_still_collide`.
- [x] 1.3 **No-build callability.** Add a test: compose an `App`, never
      call `build()`, call `validate_composition(app)`, assert no
      transport object is constructed and the compose-phase container is
      left unsealed (`app.container()` still mutable). Confirm the
      function is missing today (import/attr error = RED).
      → `test_validate_runs_without_full_build`.
- [x] 1.4 **Surface-name check available offline.** Add a test: a verb
      with an unknown `surfaces`/`expose` name is reported by
      `validate_composition(app)` **without** calling `build()` (today
      this only fires inside `build()` via `_validate_descriptor_expose`).
      Confirm RED (no standalone path today).
      → `test_unknown_surface_reported_without_build`.
- [x] 1.5 **Happy path (RED only because the function is absent).** Add a
      test: an App where every verb resolves to a distinct canonical name
      returns normally from `validate_composition(app)`.
      → `test_unique_composition_passes`.
- [x] 1.6 **build() invokes the backstop (core-composition MODIFIED).**
      Add a test: `build(app)` on the §1.1 colliding App fails loud with
      the same offending-pair message and produces no `AppRuntime`.
      Confirm RED today (build does no name-uniqueness check).
      → `test_build_invokes_uniqueness_backstop`.

## 2. Share the resolver (GREEN — foundation)

- [x] 2.1 Extract / introduce a single `resolve_canonical_name(verb)`
      function implementing ADR 0028's precedence
      (`canonical_name_override` verbatim → `slug_leaf` under a router →
      bare `leaf` app-level). This is the **one** resolver both layers
      use; the static lint rule (separate `ruff-compatible-lint-codes`
      change) will import the same function. Do not duplicate the rule.

## 3. Implement the validator (GREEN)

- [x] 3.1 Add `validate_composition(app)` that walks app-level verbs +
      every router's verbs, resolving the surfaces matrix and the
      canonical name via `resolve_canonical_name`, **without** sealing
      the container, re-materializing descriptors, or building any
      transport.
- [x] 3.2 Assert **global** canonical-name uniqueness across all verbs.
      On collision, fail loud naming the canonical name and both
      offending verbs (slug-or-app + leaf each). No silent winner, no
      rename, no deferral to dispatch.
- [x] 3.3 Reuse the existing surface-name validation logic
      (`_validate_descriptor_expose` equivalent) so the offline path and
      `build()` apply one identical surface check.
- [x] 3.4 Export `validate_composition` from the public surface so unit
      tests and consumers can call it directly.

## 4. Wire build() to the backstop (GREEN — core-composition)

- [x] 4.1 In `runtime.build()`, invoke the uniqueness backstop over the
      snapshotted descriptors (call `validate_composition` or the shared
      resolver path) during finalize, before the `AppRuntime` is
      returned, so production builds always run layer 2.
- [x] 4.2 Confirm `build()` failure carries the offending-pair message
      and that the same App fails identically standalone (shared
      resolver, no drift).

## 5. Verify (GREEN)

- [x] 5.1 All §1 tests now pass (collision fails loud, disjoint surfaces
      still collide, no-build callability, offline surface check, happy
      path, build backstop).
- [x] 5.2 Existing `core-composition` / runtime / build tests stay green
      (additive change — uniquely-named Apps see no behavior change).
- [x] 5.3 Full suite green, output pristine.

## 6. Close out

- [x] 6.1 lint / `ty check src/` / a2kit-static / ruff gates green on all
      touched files.
- [x] 6.2 Confirm the resolver is the single shared function the
      forthcoming static dup-name lint rule (`ruff-compatible-lint-codes`)
      will import — no second copy of the resolution precedence.
- [x] 6.3 Confirm scope boundaries hold: no lint-rule code added here
      (layer 1 lives in `ruff-compatible-lint-codes`); no change to the
      `slug_leaf` scheme (defined in `native-tree-homomorphism`); no HTTP
      leak fix (that is `fix-http-visibility-leak`).

## Status: LANDED (2026-06-09)

Shipped to main. `validate_composition(app)` lives in `a2kit.runtime`
(Tier 2, alongside `build`): iterates compose-phase `app.tools()` (no seal,
no transport), runs the offline `_validate_descriptor_expose` surface-name
check, then `_assert_unique_canonical_names` — global canonical-name
uniqueness keyed on `desc.name` (the one `resolve_canonical_name` output),
failing loud naming both offending verbs (slug-or-app + leaf). `build()`
invokes the same `_assert_unique_canonical_names` helper over its
snapshotted descriptors, so the two entry points share one resolver and
cannot drift. Tier-2 (not Tier-1) exposure recorded in design.md
(ADR-0004 ≤10-name front-door cap). 6 new tests
(`tests/test_validate_composition.py`); full suite 1571 passed; ty / ruff /
a2kit-lint / spec-drift / surface-snapshot all green.
