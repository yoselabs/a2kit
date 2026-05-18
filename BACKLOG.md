# Backlog

Active queue of work that's been thought through and parked, not work-in-progress. Items leave this file by being done, being filed as an ADR/OpenSpec change, or being decided as won't-do.

For historical context (pre-v0.20 design audits and exploration notes), see `todo.md`. For shipped work, see `CHANGELOG.md` and `docs/adr/INDEX.md`.

## How this file works

- One section per category (governance, tooling, ADRs, framework features, etc.).
- One bullet per item. Lead with what triggers picking it up; not when.
- If an item is conditional on a real signal (e.g. "ADR count exceeds 30"), state the trigger inline.
- Items that get picked up move to a commit + ADR/OpenSpec/CHANGELOG entry, then disappear from here.
- No dates. The order is by significance within a section, not chronology.

## Governance + process

- **Round-12 doctrine validation.** ADR 0005 predicts that future a2web rounds will surface fewer re-litigations and more retract-before-submit behaviour as C3 (misdiagnosis self-check) takes hold. Round 12 is the validation test. If the round is materially smoother, the doctrine holds. If not, revisit which clause failed and amend with a follow-up ADR.
- **Sibling doctrines if other consumer types emerge.** The current doctrine assumes a small set of close, named downstream consumers. If an external contributor pattern emerges (anonymous bug reports, third-party plugin authors), the doctrine needs either an update or a sibling document. Trigger: first non-named-consumer filing.

## ADR backlog

- **Shadow ADRs for other patterns.** Each `docs/patterns/*.md` implies an underlying decision (why the framework is shaped this way). 0008 (Lazy[T]) and 0009 (per_call) shipped. Remaining shadows surface when a contributor or consumer asks "why isn't there X?" — don't write speculatively.
- **`last_reviewed` 12-month CI gate.** ADR frontmatter has `last_reviewed`; nothing enforces it. Trigger: first ADR hits 12 months without a re-validation. Implementation: extend `scripts/adr_index.py --check` to fail if any accepted ADR has `last_reviewed` older than 12 months.
- **`proposed` age gate.** Same shape as above for `status: proposed` ADRs older than N days. Trigger: first proposed ADR sits unresolved long enough to matter. No proposed ADRs today.
- **Static-site reconsideration.** ADR 0007 explicitly defers the static-site question. Revisit when ADR count exceeds ~30 AND a contributor reports concrete navigation pain, OR when a2kit grows a full docs site (MkDocs Material, Diátaxis) for other reasons.

## Tooling

- **Re-enable disabled pymarkdown rules over time.** `.pymarkdown.json` disables several rules to land the initial integration without auditing every doc. The disabled list: `line-length`, `no-duplicate-heading`, `first-line-heading`, `no-inline-html`, `no-emphasis-as-heading`, `ul-indent`, `code-block-style`, `ol-prefix`, `no-bare-urls`, `fenced-code-language`, `no-reversed-links`. Each disable has a reason; re-enable when the corresponding cleanup makes sense (e.g. `fenced-code-language` after auditing every code block).
- **CHANGELOG automation.** Manual `CHANGELOG.md` editing per commit is fine for solo + AI-agent contribution today. If AI agents start landing changes in parallel and merge conflicts on `CHANGELOG.md` become real, adopt towncrier-style fragment files (`changes/<slug>.feature.md`). Don't speculate.
- **Mutation testing baseline.** `docs/MUTATION_BASELINE.md` is blocked on mutmut 3.5 compatibility. Tracked there, not here.

## Framework features

- **AGENTS.md drift policy.** Once AGENTS.md is the canonical agent-instruction file, decide whether CLAUDE.md stays as Claude-specific overlay or symlinks to AGENTS.md. Trigger: a Claude-specific behaviour that AGENTS.md cannot capture cleanly. Until then, current split is the default.
