## Why

a2web's round-11 feedback (`A2KIT_FEEDBACK_v0.39.md`) reports the smoothest migration of all eleven rounds: four of six round-10 frictions adopted clean, 414 tests green, wire surfaces unchanged. Two of the parked frictions (A3, E) were **retracted by the consumer on second look** — A3 was a helper-vs-use-case mismatch, E was a correct architectural split misread as forced verbosity. The consumer explicitly asked these two meta-lessons be documented so future rounds carry a "did we misdiagnose?" check.

Round 11 also surfaced one small new friction: the autouse re-export pattern for `a2kit.testing.ambient_for_tests` reaches through `__wrapped__` (a quirky-looking pytest internal) and requires three lines of consumer ceremony for the 95% case. The cheapest fix is a pre-decorated variant.

Carry-overs C (canonical `a2kit.Lazy` / `a2kit.LddEmission` surface) and D (`pydantic.Field` description sugar) stay parked — no fresh signal this round. Health-check no-body shorthand was explicitly not raised formally by the consumer and is out of scope.

## What Changes

- **Consumer-feedback doctrine v2 addendum.** Extend `docs/CONSUMER_FEEDBACK_DOCTRINE.md` with two new sections distilled from round 11:
  - *Friction-filing misdiagnosis.* Filings can be wrong in two distinguishable ways: (1) right primitive, wrong use case (A3 shape); (2) correct design mistaken for accidental ceremony (E shape). Add a "did we misdiagnose?" checkbox to the consumer intake template and an explicit step that says: *before adopting a capability shipped in response to your filing, re-validate the original friction still holds.*
  - *Capability shipping vs adoption pressure.* When a2kit ships a capability in response to a friction, the framework's responsibility is to ship quietly — no migration nag, no deprecation of the prior shape. The consumer's responsibility is to re-validate before adopting. Both halves are load-bearing.
- **New ADR** in `docs/adr/` recording the doctrine v2 decision with Y-statement framing, referencing ADR 0005 (the v1 doctrine) and the round-11 source feedback file.
- **`a2kit.testing.ambient_for_tests_autouse`** ships as a pre-decorated peer of `ambient_for_tests`. Strictly additive — the existing fixture is untouched. Consumers wanting project-wide ambient binding write `from a2kit.testing import ambient_for_tests_autouse` in their conftest and that's it. No `__wrapped__`, no three-line re-export.
- **`OPERATIONAL_CONTRACTS.md`** gains a short note next to the existing Q-AmbientForTests entry pointing at the two flavors and when to pick each.

Carry-overs C and D remain in `A2KIT_WISHES_DEFERRED.md` (entries 7 and 8) untouched.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `in-process-test-client`: Adds `a2kit.testing.ambient_for_tests_autouse` as a peer to the existing `ambient_for_tests` fixture. Behavior of the existing fixture is unchanged; the new variant is `pytest.fixture(autouse=True)`-decorated at module scope so consumers can re-export with a single import.

The doctrine addendum and ADR are documentation-only and do not modify a runtime capability spec.

## Impact

- **API.** One additive surface: `a2kit.testing.ambient_for_tests_autouse`. No breaking changes. Existing `ambient_for_tests` and the documented `__wrapped__` re-export pattern keep working.
- **Code.** ~5 LOC in `a2kit/packages/testing/` (the new variant + re-export from `a2kit.testing`). ~30 LOC test asserting both flavors bind ambient correctly under autouse and non-autouse use.
- **Docs.** New ADR (~80 LOC) + addendum sections in `CONSUMER_FEEDBACK_DOCTRINE.md` (~50 LOC) + paragraph in `OPERATIONAL_CONTRACTS.md` Q-AmbientForTests (~10 LOC).
- **Consumer savings (a2web).** Three lines of `__wrapped__` ceremony + quirky import collapse to one line. Future rounds use the doctrine v2 checklist before filing.
- **Backwards compat.** Strict additive. No deprecation. No migration required.
- **Release.** Patch bump (v0.39.3) — additive testing helper + docs. Solo repo, merge to main per `feedback_no_prs`.
