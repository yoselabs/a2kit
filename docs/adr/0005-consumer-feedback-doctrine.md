---
id: "0005"
status: accepted
date: 2026-05-18
last_reviewed: 2026-05-18
supersedes: []
superseded_by: null
tags: [process, feedback, governance]
deciders: [Denis Tomilin]
---

# ADR 0005: Adopt framework⇄consumer feedback doctrine

## Status

Accepted, 2026-05-18.

## Summary

In the context of a2kit's relationship with downstream consumers
(a2web, a2atlassian, a2db, a2sdlc), facing the fact that two
consecutive a2web feedback rounds (10 and 11) re-litigated the same
asks without recorded answers and produced two consumer-side
retractions caught only after a release cycle, we decided to adopt
the written doctrine at `docs/CONSUMER_FEEDBACK_DOCTRINE.md` as the
binding rulebook for triaging filings and re-validating capabilities
on adoption, and against continuing to decide each filing
case-by-case in conversation, to achieve a feedback loop where every
filing gets a substantive answer (ship / decline-with-reason /
reframe / defer), every decline cites the conflicting principle or
ADR, and consumers re-validate frictions before adopting newly-
shipped capabilities, accepting a small process cost on both sides
(a misdiagnosis self-check in filings, a release-reading checklist on
adoption) in exchange for eliminating round-over-round drift.

## The problem

By the close of a2web round 11, the framework⇄consumer interaction
had two concrete failure modes that the existing CLAUDE.md core
principles did not address:

1. **Re-litigation without recorded answers.** Friction C
   ("promote `Lazy` and `LddEmission` to top-level") was filed in
   round 10, declined in conversation, and refiled identically in
   round 11. Nothing in the repo recorded why it was declined.
   Without a citable answer, every future round will refile the
   same ask, and the framework author has to re-argue the same
   case from scratch. This is the gap ADR 0004 (package layout)
   closes — but only retroactively, after the second refile.

2. **Misdiagnosed filings consumed release cycles.** Two round-10
   filings were retracted in round 11 on adoption:
   - **A3** (`resolve(app, T)` as a replacement for `make_default_state`):
     the consumer assumed two helpers were redundant; on adoption
     they realized they served different shapes (outside-app vs
     inside-app testing). The primitive shipped was correct; the
     mapping the filing assumed was wrong.
   - **E** (`Lazy[T]` in factory params to collapse `AppState` split):
     the consumer assumed a verbosity was friction; on adoption they
     realized the architectural split was correct design.

   Both consumed a release cycle for capabilities that turned out
   to be unneeded. Cheaper if the original filing had asked "what
   would make this diagnosis wrong?" before submission.

A third failure mode appeared while drafting the doctrine itself:
the `docs/feedback-responses/` directory created in round 10 coupled
the framework repo to one consumer's round cadence. Future rounds
would either bloat the directory or quietly drift; either way the
framework was paying for record-keeping that belongs in the
consumer's repo.

Without a written rulebook, these failure modes recur every round
without anyone noticing the pattern.

## What we considered (and why this one)

### Option 1: Status quo — decide each filing case-by-case in conversation

The default. Every filing is debated on its own, declines are
verbal or live in the source PR/issue thread, no repo-level record.

Why it lost: rounds 10 and 11 are the demonstration. The cost of
re-running the same conversation every round, plus the cost of
debugging misdiagnosed filings post-release, accumulates faster
than the cost of writing the doctrine down once.

### Option 2: Per-round response logs under `docs/feedback-responses/`

The approach round 10 briefly adopted: each consumer's round gets a
markdown response file. The framework records its decisions per
round.

Why it lost: the file's existence creates an implicit contract that
*every* round produces a response file, which pulls the framework
into the consumer's round cadence. The framework's natural
record-keeping is CHANGELOG entries (for shipped capabilities) and
ADRs (for class-declines). Per-round files duplicate that and rot
when neglected. The doctrine's F1 explicitly forbids this pattern;
the directory was deleted in the same change that introduced the
doctrine.

### Option 3: Adopt the written doctrine (chosen)

Codify F1-F5 (framework-side rules: every filing gets an answer,
ship the primitive not the mapping, refuse use-case-specific asks,
no adoption pressure, record decisions in ADRs) and C1-C4
(consumer-side rules: read every release, re-validate frictions,
misdiagnosis self-check, cite ADRs when contradicting). Make
CHANGELOG entries the primary response medium for shipped
capabilities; make ADRs the primary medium for class-declines;
keep one-off declines in the conversation that produced them.

Why it wins:

- Addresses both failure modes directly. Re-litigation is killed
  by F5 (record decisions in ADRs) and C4 (consumers cite ADRs
  before filing). Misdiagnosis is killed by C3 (the self-check)
  combined with F2 (ship primitive, not mapping).
- Stays decoupled from any one consumer's round cadence. The
  framework repo records *decisions*, not *interactions*.
- The doctrine itself can evolve via subsequent ADRs that
  supersede this one; it is not frozen by adoption.

### Option 4: A lighter version — just record the F-rules, skip C-rules

Argument: framework can govern its own behaviour but cannot
prescribe consumer behaviour.

Why it lost: the misdiagnosis problem (A3, E retractions) is
fundamentally consumer-side. The framework cannot fix it
unilaterally. Without C1-C4, the cycle continues. The C-rules are
not enforcement against consumers — they are expected discipline
the framework can point at when a consumer asks "how do I file a
good friction?"

## The decision

`docs/CONSUMER_FEEDBACK_DOCTRINE.md` is the binding prescription
for framework⇄consumer feedback. Every framework response to a
filing follows F1-F5. Every consumer adoption of a shipped
capability follows C1-C4 (the framework cannot enforce these but
can cite them in conversations).

The response media stack is:

- **CHANGELOG.md** — when a release addresses asks, one line per ask
  in the release notes. Primary record for ships.
- **ADRs** — when a decline applies to a class of asks. Primary
  record for class-declines. This very ADR is the model.
- **The originating conversation** — for one-off declines that do
  not warrant an ADR. Not promoted into the repo.

No `docs/feedback-responses/` directory exists; the prior
`v0.38-a2web-round-10.md` was deleted in the same change.

The doctrine file is referenced from `CLAUDE.md` under "Project
state hooks" so every Claude Code session loads it implicitly.

## Consequences

### Positive

- Future rounds can refile the same friction and get a one-line
  answer ("see ADR NNNN"). Both sides save the conversation cost.
- The misdiagnosis self-check (C3) catches A3/E-shaped filings
  before they consume release cycles. The cost is one extra line
  per filing.
- Framework⇄consumer interactions have a documented shape both
  sides can point at when one feels the other is operating outside
  the rules. This is healthier than ad-hoc norm-setting.
- The doctrine itself is meta-load-bearing — ADRs cite it, filings
  cite it, CLAUDE.md cites it. The doctrine adopts itself by
  example: this ADR is the decision; the doctrine doc is the
  prescription; F5 says "record decisions in ADRs."

### Negative

- A small process tax. Filings now include a misdiagnosis self-check
  line; framework responses now have to identify which F-rule they
  are invoking. Both are cheap (a few lines) but non-zero.
- Consumer-side rules (C1-C4) are not enforceable. The framework
  can decline to engage with filings that ignore C3, but cannot
  *make* the consumer write the self-check. In practice this is
  fine — the doctrine is a coordination point, not a contract.
- The doctrine couples the framework to one model of consumer
  relationships (small set of close downstream consumers, named
  filings, multi-round cadence). If a future consumer pattern
  emerges that does not fit (e.g. anonymous bug reports from
  end-users), the doctrine will need an update or a sibling
  document.
- A new contributor must read both this ADR and the doctrine doc
  before authoring a feedback response. The doctrine is ~250
  lines; not free.

## References

- `docs/CONSUMER_FEEDBACK_DOCTRINE.md` — the prescription this ADR
  adopts. F1-F5 (framework rules), C1-C4 (consumer rules), filing
  and response templates, the discipline-loop diagram.
- `docs/adr/0004-package-layout-tiered-by-audience.md` — the first
  ADR that exists specifically to cite-and-decline a recurring
  filing class (Friction C). This ADR's F5 generalizes that pattern.
- `CLAUDE.md` "Architecture strategy" + "Project state hooks"
  sections — pointers into the doctrine and ADR registry.
- a2web `docs/history/A2KIT_FEEDBACK_v0.38.md` and
  `A2KIT_FEEDBACK_v0.39.md` — the round-10 and round-11 reports
  that surfaced the failure modes. Lives in the consumer repo, not
  this one (F1: framework does not mirror consumer round logs).
