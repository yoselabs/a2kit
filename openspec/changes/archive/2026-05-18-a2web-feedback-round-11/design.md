## Context

a2kit's consumer-feedback loop with a2web is now eleven rounds deep. Round 11 is the first round where the consumer retracted two of its own filings on second look, having spent v0.39 adopting the shipped capabilities and discovering both were either misdirected (A3) or misdiagnosed (E). This is signal that the doctrine codified in ADR 0005 (`CONSUMER_FEEDBACK_DOCTRINE.md`) needs one more turn of the crank: a re-validation step on the consumer side, paired with a quiet-shipping discipline on the framework side.

The autouse-fixture friction is the smallest possible parallel change — strictly additive testing helper, no spec drift, ~5 LOC of code plus tests. It ships in the same release because both items came out of the same round and both are cheap.

## Goals / Non-Goals

**Goals:**
- Bottle round-11's two meta-lessons in a form that future consumer filings can use as a checklist before submission.
- Make the framework's "ship quietly, no adoption pressure" stance explicit and tied to a concrete ADR, not folklore.
- Remove the one new friction (`__wrapped__` autouse re-export) with the smallest possible addition.

**Non-Goals:**
- No changes to existing `ambient_for_tests` behavior or signature.
- No deprecation of the documented re-export pattern — it remains valid for consumers who already adopted it.
- No movement on carry-overs C (canonical surface promotion) or D (Field description sugar) — consumer flagged "no fresh signal."
- No health-check no-body shorthand — explicitly not raised formally by the consumer; would be solving for one.
- No changes to ADR 0005; the v2 doctrine is an *addendum*, not a replacement.

## Decisions

### Decision 1: Doctrine v2 as addendum + new ADR, not rewrite of ADR 0005

The original doctrine (ADR 0005, landed in v0.39.2) is sound. The round-11 lessons extend it rather than correct it. A new ADR with a "Supersedes: none / Extends: 0005" relationship keeps the audit trail clean. The `CONSUMER_FEEDBACK_DOCTRINE.md` document gains new sections rather than being rewritten — readers of the v1 sections still see the same words.

**Alternative considered.** Rewrite ADR 0005 in place. Rejected: ADR immutability after acceptance is a useful discipline, and we have a fresh ADR slot available cheaply.

### Decision 2: Misdiagnosis taxonomy gets two named shapes

The doctrine text names the two shapes from round 11 explicitly so future filings can self-classify:
- **Shape A3 ("right primitive, wrong use case"):** consumer files a helper request describing a use case the proposed primitive doesn't actually address. Mitigation in the doctrine: the consumer-side intake template asks "what use case does this primitive replace, and is the use case I'm describing the same shape?"
- **Shape E ("design mistaken for ceremony"):** consumer files "the framework forces me to write N lines" when the N-line shape is correct design. Mitigation: the doctrine asks "if the framework shipped exactly what I asked for, would the code be better or just shorter?"

Naming the shapes (rather than describing them abstractly) makes them recognisable.

**Alternative considered.** Generic "did we misdiagnose?" checkbox with no taxonomy. Rejected: a checkbox without examples is process theatre; the named shapes give the consumer something to pattern-match against.

### Decision 3: Capability-shipping discipline goes both ways

The doctrine v2 section on adoption pressure makes both halves explicit:
- **Framework side:** ship the capability, no migration nag, no deprecation of the prior shape, no "you should adopt this" in release notes. The release note format already does this (round 10 / v0.39 was the proof); the doctrine just makes it a rule.
- **Consumer side:** before adopting a capability that was shipped in response to *your* filing, re-run the original friction filing as if writing it fresh. If you wouldn't file it now, the capability is a quiet capability for someone else.

This is the load-bearing pair. Either half alone produces wrong incentives.

### Decision 4: `ambient_for_tests_autouse` over `autouse()` helper

The consumer offered two options ((a) pre-decorated variant, (b) `a2kit.testing.autouse(fixture)` helper). Picking (a):
- **One import, no function call.** `from a2kit.testing import ambient_for_tests_autouse` reads as a fixture name. `ambient_for_tests = a2kit.testing.autouse(ambient_for_tests)` reads as plumbing.
- **Discoverable.** `dir(a2kit.testing)` shows both flavors. The helper hides the autouse variant behind a verb.
- **Less surface.** No new general-purpose autouse-wrapping primitive that other fixtures might want to use later; we ship exactly the one shape consumers asked for.

**Alternative considered.** Option (b) `autouse()` helper. Rejected for the reasons above; if a future round shows demand for autouse-wrapping a *different* a2kit fixture, we can introduce the helper then.

### Decision 5: Existing `ambient_for_tests` stays unchanged

The documented `__wrapped__` re-export pattern remains valid. Consumers who already adopted it (a2web has) do not need to migrate. The new variant is for the next consumer to land here, and for a2web's next-round cleanup if they choose.

## Risks / Trade-offs

- **Risk: doctrine addendum reads as performative process.**
  Mitigation: keep the misdiagnosis taxonomy concrete (Shape A3 / Shape E references the actual round-11 filings) and short. If it grows past one printed page, it's drifted into theatre.

- **Risk: two near-identical fixture exports cause confusion ("which do I want?").**
  Mitigation: the `OPERATIONAL_CONTRACTS.md` Q-AmbientForTests entry includes a one-line decision rule ("project-wide ambient → `_autouse`; per-test opt-in → bare fixture"). Both docstrings cross-link.

- **Risk: future capability shipped in response to a filing gets adoption-pressured anyway (release notes drift).**
  Mitigation: the doctrine v2 ADR is the place release notes get reviewed against. If a release note pressures adoption, the addendum is the lint.

## Migration Plan

No migration required. Strictly additive on both the docs and the code side. a2web continues with its existing `__wrapped__` re-export until they choose to swap (or never — both shapes stay supported).
