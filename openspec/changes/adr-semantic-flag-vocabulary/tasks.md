# Tasks — ADR 0003 semantic flag vocabulary

## 0. Prerequisites

- [ ] 0.1 Confirm ADR 0002 (`docs/adr/0002-author-annotation-surface.md`)
      is current. ADR 0003 cross-references it.
- [ ] 0.2 Read `docs/adr/README.md` (the prescription). ADR 0003
      must comply.

## 1. Draft the ADR

- [ ] 1.1 Create `docs/adr/0003-semantic-flag-vocabulary.md`.
- [ ] 1.2 Follow the README prescription structure:
      Status / Summary / The problem / What we considered /
      The decision / Consequences / References.
- [ ] 1.3 Optional Y-statement summary at the top.
- [ ] 1.4 In "What we considered", address the rejected
      `annotations={...}` collapse explicitly. The audit considered
      it; the ADR explains why it lost.
- [ ] 1.5 In "The decision", list:
      - Vocabulary (4 flags, locked v1 set).
      - Contract for adding new flags (two-transport-read minimum).
      - Reserved-for-future extensions (none today; pointer at how
        a future addition would supersede this ADR).
- [ ] 1.6 Consequences must include a real negative cost
      (per `docs/adr/README.md` anti-pattern table: no Fairy Tale).
      Candidate cost: authors must learn a fixed four-flag set
      rather than discover them transport-by-transport.

## 2. Cross-reference

- [ ] 2.1 In `docs/adr/0002-author-annotation-surface.md`, if it
      mentions semantic flags or transport-routing metadata,
      add a "See also" pointer to ADR 0003.
- [ ] 2.2 In `replace-surfaces-with-visibility` proposal, add a
      pointer to ADR 0003 in its References section if appropriate.

## 3. Verify

- [ ] 3.1 ADR is ≤ 250 lines per `docs/adr/README.md` length norm.
- [ ] 3.2 Smell-test pass:
      - Names a concrete bottleneck.
      - Addresses status quo + closest realistic alternative
        (the `annotations={...}` collapse).
      - Consequences has a real cost.
      - Hostile reviewer can answer "why these 4 flags and not
        others?" from the file alone.

## 4. Commit

- [ ] 4.1 Commit on a feature branch.
- [ ] 4.2 No CHANGELOG entry (docs-only).
