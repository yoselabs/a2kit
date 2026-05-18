# Consumer feedback doctrine

How a2kit and its downstream consumers (a2web, a2atlassian, a2db, a2sdlc, …) interact on framework evolution. The doctrine governs both sides of the boundary: how a2kit answers friction filings, and how consumers act on the resulting releases.

a2kit is **generic shared software**. Consumers are **specific use cases**. The relationship is collaborative but asymmetric: the consumer feels the pain first, the framework owns the surface that everyone else also depends on. Most friction filings are real signal. Some are real signal pointing at the wrong fix. A small number are use-case-specific demands that would harm other consumers if shipped. Telling them apart is the discipline.

## Why this exists

Without written discipline, every feedback round repeats the same three mistakes:

1. Framework ships what the consumer asked for, only to discover later the ask was a misdiagnosis.
2. Consumer adopts a new capability because it shipped, only to realize the original friction did not actually hold.
3. Both sides re-litigate decisions that were already made and recorded, because nobody pointed at the existing record.

The doctrine bottles the rules that prevent each.

## Framework-side rules — when a consumer files friction

### F1. Every filing gets an answer — but the answer lives in framework-canonical places

A friction filing is a contract: the consumer paid the cost of writing it down, the framework owes a substantive response. The shapes of valid responses are:

- **Ship the primitive** the friction needs. Cleanly, with no migration pressure on the existing shape. The shipping itself is the answer; the durable record is the CHANGELOG entry.
- **Decline with reason.** Cite the conflicting principle, the relevant ADR, or the broader-consumer cost. "No" is a valid answer; silent inaction is not.
- **Reframe.** "What you described is symptom X; the underlying issue is Y; here is what we will do about Y."
- **Defer with conditions.** "Not now, because <X>. We revisit when <signal Y> appears."

**Where the answer lives.** a2kit does not maintain a per-consumer or per-round response log. The framework's durable artefacts are:

- **CHANGELOG.md** — when a release addresses asks, the release notes name them in a single short paragraph ("v0.X addresses <ask Y from <consumer>>, and <ask Z>; see ADR NNNN for the class-decline of <ask W>"). One line per ask. No deep response file.
- **ADRs** — when a decline applies to a *class* of asks (e.g. "we will not promote DI primitives to top-level"), the reason gets an ADR. Future asks in that class are answered with a citation, not a fresh response.
- **The conversation itself** — for one-off declines that do not warrant an ADR, the response lives in whatever medium the filing arrived in (issue, PR review, chat). It is not promoted into the repo.

Silent rejection is forbidden. But a "recorded answer" is a CHANGELOG line or an ADR — not a `docs/feedback-responses/v0.N-<consumer>-round-M.md` file. The framework stays independent of any one consumer's round cadence; round-keeping is the consumer's repo's job.

### F2. Ship the primitive, not the consumer's mapping

When a consumer reports "framework forces N lines of boilerplate," they are reporting **symptoms** (verbose code), not **diagnosis** (which surface is wrong). The consumer's proposed fix may be miscategorized.

Rule: ship the smallest, most general primitive that addresses the symptom. Do not also try to delete the consumer's helper for them. Let the consumer map the new primitive to their use cases on adoption — they may find the mapping is different from what they originally claimed.

Worked example: a2web round 10 filed A3 as "`make_default_state` is reinvented boilerplate, ship a helper to delete it." a2kit v0.39 shipped `a2kit.testing.resolve(app, T)` — the smallest correct primitive for resolving inside an app scope. On adoption, a2web realized `make_default_state` and `resolve` solve **different** problems (outside-app vs inside-app construction). The primitive was right; the mapping a2web proposed was wrong. Because the framework shipped only the primitive, the misdiagnosis cost zero rework.

### F3. Refuse asks that violate generic-shared-software discipline

Some filings encode demands that are correct for the filer's use case and wrong for everyone else's. The framework's job is to refuse them on behalf of consumers who did not file.

Heuristics for "use-case-specific, not framework-generic":

- The ask hard-codes a value, format, or workflow that other consumers would have to opt out of.
- The ask creates a second way to do something the framework already has one way to do (violates "no multiple ways" — see `CLAUDE.md` core principle 2).
- The ask contradicts an existing accepted ADR.
- The ask would force every other consumer to update code they have no incentive to touch.

Decline with the conflicting principle named. Point at the ADR or the CLAUDE.md section. The consumer can disagree with the principle and propose changing it — that is a separate, higher-bar conversation.

### F4. Don't ship adoption pressure

When the framework ships a capability in response to a friction, the migration must be optional. The old shape keeps working. No deprecation nag, no "you should adopt this" message, no version-gated lint warning.

Reason: see consumer-side rule C2. The consumer must re-validate the friction before adopting, and the framework cannot know whether the re-validation will succeed. Adoption pressure pre-empts that validation and forces consumers into shape changes they may not actually need.

### F5. Record decisions in ADRs

Any framework-side decision that will be load-bearing for future rounds — a primitive shape, a refused class of asks, a deferred capability with conditions — goes into an ADR under `docs/adr/`. See `docs/adr/README.md` for the prescription. The ADR is the durable answer; the feedback response is the conversational answer that points at it.

Without ADRs, every round re-runs the same arguments. With ADRs, the framework author replies "see ADR 0002" and the conversation moves on.

## Consumer-side rules — when the framework ships a capability

### C1. Read every release; try every applicable capability

A new framework release is not noise to skim. It is a list of capabilities the framework now offers — some of which may apply to code the consumer has already written. The consumer's obligation, on every release:

1. Read the changelog.
2. Read the migration notes.
3. Scan the consumer's own codebase for places where the new capability would simplify existing code.
4. **Try** at least one application of each applicable capability. Not "consider trying" — actually attempt the migration in a branch.

This is not adoption pressure (the framework will not enforce it). It is consumer discipline. If a capability ships and no consumer ever tries it, one of two things is true:

- The capability is wrong-shaped and should be retracted.
- The capability solves a problem no consumer actually has, and the framework should not have shipped it.

Both are valuable signals back to the framework. Untried capabilities produce no signal at all.

### C2. Re-validate the original friction before adopting

When the framework ships in response to a friction, the consumer must re-check that the friction **still holds** before migrating. Sometimes, in the time between filing and shipping, the consumer's codebase has moved and the original pain is gone. Sometimes the consumer realizes the friction was a misdiagnosis (see F2).

Adopt the new capability only if the re-validation confirms the original problem. If not, **retract the friction publicly** and explain why. The retraction is more valuable than the adoption — it teaches both sides where the diagnosis was weak.

Worked example: a2web round 10 filed Friction E ("`AppState` is forced to split into always-on vs lazy"). v0.39 shipped `Lazy[T]`-in-factory recognition. On adoption, a2web realized the architectural split was **correct design**, not friction. They retracted Friction E and documented the lesson. The framework keeps the capability available; a2web does not adopt; both decisions are correct.

### C3. Friction filings include a misdiagnosis self-check

Every friction filing should answer, before submission:

- **What is the symptom?** Specific: LOC count, file paths, repeated patterns.
- **What is the proposed fix?** What surface would change, and how.
- **What is the assumed diagnosis?** "We believe the framework forces X because Y." This is the hypothesis the framework will evaluate.
- **What would make this diagnosis wrong?** The consumer's own attempt at falsification. If the consumer cannot imagine a way the diagnosis is wrong, the filing is too confident.

The fourth point is the misdiagnosis self-check. It does not have to be exhaustive — one or two plausible "if we are wrong about this, it's because…" lines are enough. They turn the filing from a demand into a hypothesis, which is what the framework needs to evaluate it fairly.

### C4. Cite ADRs when proposing changes that touch recorded decisions

Before filing a friction that proposes changing a public surface, check `docs/adr/` for relevant accepted decisions. If the ask contradicts an ADR, name it in the filing and argue against the ADR's reasoning directly. Do not file in ignorance of the existing record.

The framework's first move on receiving such a filing is to check the same registry, so the consumer saves a round-trip by doing it first.

## The discipline loop

```
            ┌──────────────────────────────────────────────────────┐
            │                                                      │
            ▼                                                      │
   ┌────────────────┐    ┌──────────────────┐    ┌──────────────┐  │
   │ Consumer files │    │ Framework triages│    │  Framework   │  │
   │   friction     ├───▶│ (F1–F5: answer,  ├───▶│ ships / docs │  │
   │  (C3 included) │    │  reframe, refuse,│    │ / refuses /  │  │
   │                │    │  defer, record)  │    │   defers     │  │
   └────────────────┘    └──────────────────┘    └──────┬───────┘  │
                                                       │           │
                                                       ▼           │
                                            ┌──────────────────┐   │
                                            │   New release    │   │
                                            └──────┬───────────┘   │
                                                   │               │
                                                   ▼               │
                                          ┌────────────────────┐   │
                                          │ Consumer reads,    │   │
                                          │ scans codebase,    │   │
                                          │ tries capabilities │   │
                                          │ (C1)               │   │
                                          └──────┬─────────────┘   │
                                                 │                 │
                                                 ▼                 │
                                       ┌────────────────────────┐  │
                                       │ Re-validate friction   │  │
                                       │ (C2). Adopt OR retract │  │
                                       │ with reason.           │  │
                                       └─────┬─────────────┬────┘  │
                                             │ retract     │ adopt │
                                             ▼             ▼       │
                                  ┌────────────────────────────┐   │
                                  │ Report back. New round.    ├───┘
                                  └────────────────────────────┘
```

The loop's value is in the **back edges**: retractions and adoption reports. They tell the framework whether the previous round's decisions were correct in practice, which is the only feedback signal that improves future rounds.

## Templates and checklists

### Friction filing template (consumer side)

```markdown
## Friction <ID> — <one-line summary>

**Symptom (concrete).**
- Specific LOC count or file path
- Repeated pattern, with one example block

**Proposed fix.**
- Surface that would change, and how

**Assumed diagnosis.**
- "We believe the framework <does X> because <Y>."

**Misdiagnosis self-check.**
- "If we are wrong about this, it is probably because <plausible alternative>."

**Relevant ADRs.**
- ADRs we checked and how this filing relates (supports / contradicts / orthogonal).
```

### Framework response template

```markdown
## Friction <ID> — response

**Decision.** Ship / Decline / Reframe / Defer.

**Reason.** <one paragraph. Cite ADR if applicable.>

**If ship:** which primitive ships, where, what shape. No adoption pressure language.

**If decline:** which principle / ADR / broader-consumer cost. The consumer may push back; that is a separate conversation about the principle.

**If reframe:** the diagnosis we propose instead, and what we will do about it.

**If defer:** the condition under which we revisit.
```

### Release-reading checklist (consumer side)

On every framework release, before continuing other work:

- [ ] Read the changelog top-to-bottom.
- [ ] Read the migration notes.
- [ ] For each new capability, grep the consumer codebase for shapes it could simplify.
- [ ] Try at least one migration per applicable capability in a branch.
- [ ] For each open friction filing, re-validate it still holds (C2). Retract if not.
- [ ] Report adoption results back (adopted N callsites / retracted M filings / new friction Z surfaced during migration).

## What this doctrine is not

- Not a process tax. The filing template is four lines. The framework response is one paragraph. The whole point is to make interactions denser, not longer.
- Not a hierarchy. Consumers are not subordinate; the framework is not above review. Both sides operate under the same discipline.
- Not a substitute for conversation. Real-time discussion is faster than written rounds for many things. The doctrine governs what gets **written down** — which is the small fraction of interactions that future maintainers will read.

## References

- `docs/adr/README.md` — the ADR prescription. The durable decision record.
- `docs/adr/0002-author-annotation-surface.md` — example of an ADR that pre-empts a class of friction filings ("ship a description sugar," "extract descriptions from docstrings").
- `docs/adr/0004-package-layout-tiered-by-audience.md` — example of an ADR that pre-empts the "promote X to top-level" class of filings.
- `CHANGELOG.md` — the release-by-release record of what got addressed and what got declined. The framework's primary response medium; no parallel feedback-response log exists.
- `CLAUDE.md` — core principles (no backward-compat shims, no multiple ways, no silent errors, errors carry migration hints).
- `OPERATIONAL_CONTRACTS.md` — the framework's behavior contract. ADRs and friction filings reference its clauses.
- `ANTIPATTERNS.md` — concrete consumer-facing anti-patterns. Sometimes the right response to a friction filing is "this filing describes an anti-pattern; we should add it here instead of shipping a workaround."
