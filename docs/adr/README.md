# ADRs: how we write them

An ADR (Architecture Decision Record) is a short document that captures
a single architectural decision: what changed, why, and what we accepted
in return. We keep them per-project under `docs/adr/`, numbered, append
only. The point is not paperwork. The point is that six months later a
contributor (or future you) can read one file and understand why the
codebase looks the way it does, without re-running the conversation that
produced the decision.

This doc is the prescription: what an ADR for this project must contain,
what it must not, and how we tell good ones from bad ones.

## When to write one

Write an ADR when the decision is **load-bearing and non-obvious**:

- It affects code outside the immediate change (public surface,
  dependency graph, deployment shape, contributor workflow).
- A reader looking at the code later would reasonably ask "why did
  they do it this way and not the obvious alternative?"
- The decision constrains future work (committing to a framework,
  declaring a contract, accepting a breaking change).

Do NOT write an ADR for: a refactor, a bug fix, naming a function,
choosing a CSS unit. Most code changes do not need an ADR. If in doubt,
the rule is: would someone disagreeing with this decision need a
reasoned answer? If yes, ADR. If "it's just how we wrote it," no.

## Required sections

Every ADR in this repo must have these sections, in this order. Section
names are literal; do not rename them.

### Status

One word per line: `Proposed` / `Accepted` / `Superseded by ADR NNNN` /
`Deprecated`. Plus the date in `YYYY-MM-DD`. If a follow-up ADR
supersedes this one, edit the Status line here so a reader landing on
this file sees the redirect.

### The problem

Name the **bottleneck**, not the topic. "We need to choose a CLI
framework" is a topic. "Our 350-LOC hand-rolled Click reflection layer
accumulates a new conditional every cleanup round because Click is not
a reflection library" is a bottleneck.

If you cannot describe the problem in concrete, falsifiable terms
(LOC numbers, specific file paths, specific conditionals, a benchmark,
an incident date), the decision is probably premature. Go back and
find the bottleneck first.

### What we considered (and why this one)

List the realistic alternatives. Not strawmen. The reader should be
able to see that you actually weighed them.

For each, one sentence on what it would have looked like and one
sentence on why it lost. The point is not exhaustiveness. The point is
to prove the chosen option beat the closest realistic alternative, not
just a fake comparison.

Common trap: writing "considered argparse / cleo / cyclopts" when none
of them were ever a real option (because they don't speak Click).
That is not consideration. That is decoration. If you would not have
seriously merged it, do not list it.

The most important alternative to address: **the status quo**. Why was
"keep doing what we do" not the right call? If you cannot answer that,
the decision is not ready.

### The decision

One paragraph. What changes, concretely, in the codebase. Reference
files and modules by path. Reference public-API or wire-format changes
explicitly. If the decision is conditional ("we adopt X for the Python
SDK; the Rust SDK will revisit"), say so.

### Consequences

Two subsections, both required:

- **Positive.** What gets easier or cheaper. Be concrete: "the per-tool
  CLI plumbing is now framework-owned" beats "improved maintainability."
- **Negative.** What gets harder, what we now own that we did not
  before, what we accepted as a trade-off. If a section reads like
  marketing copy with no real cost, you have written a Fairy Tale (see
  anti-patterns). Go back and find the cost.

If the decision has a migration cost or a deprecation window, say so
here. If a downstream consumer must change code, name the public
symbol or flag.

### References

Links to: the change proposal (openspec), the spike (if any), key code
paths, the commit that landed the change. ADRs are entry points into
the conversation, not replacements for it.

## Optional: Y-statement summary

For decisions that fit in one sentence, you may add a Y-statement at
the top, under Status:

> In the context of `<area>`, facing `<constraint>`, we decided for
> `<choice>` and against `<closest alternative>`, to achieve
> `<benefit>`, accepting `<cost>`.

It is a one-line TL;DR, not a replacement for the full sections. Use it
when it forces clarity; skip it when it would just be ceremony.

## Anti-patterns (do not ship these)

| Smell | What it looks like | Why it is bad |
|---|---|---|
| **Fairy Tale** | Consequences section lists only benefits. "Improves maintainability, aligns with industry standards, easier to onboard." | If there is no cost, you did not actually choose. A free decision is a non-decision. |
| **Status quo not addressed** | "Considered Alternatives" lists every framework on GitHub except "keep what we have." | The most expensive option is always switching. If staying put was not the real comparator, the decision is undefended. |
| **Bureaucratic shell** | Each section has one sentence of generic content. "Context: we need a CLI. Decision: use Typer. Consequences: better DX." | A reader six months later learns nothing they could not infer from the commit message. |
| **Fake-considered alternatives** | Lists three options the author would never have merged. Often "argparse" appears for performative breadth. | Reads as decoration, undermines trust in the real comparison. |
| **Post-hoc justification** | ADR written after the code shipped, framing the chosen path as inevitable. | Engineers will recognize it instantly. Better to write nothing than to write a fake. |
| **Sprint anti-pattern** | Consequences only discuss the next sprint or two. No mention of multi-year maintenance, ports, deprecation. | Architectural decisions outlive their authors. Name the long tail. |
| **Tunnel Vision** | Only one perspective considered (e.g. developer ergonomics, ignoring ops / security / cost). | Decisions have second-order effects. Name them or someone else will inherit them. |
| **Vague pain** | "The current approach is complex / hard to maintain / not scalable." | Complexity, maintainability, and scalability are not metrics. Replace with concrete code references, LOC counts, or incident dates. |
| **Status drift** | ADR says X, codebase does Y, neither is marked superseded. | The log is now actively misleading. Either fix the code, write a superseding ADR, or mark this one Deprecated. |

## The smell test

Before merging an ADR, the author re-reads it and asks:

1. **Could a hostile reviewer rewrite the title as a question and find
   the answer in the file?** "Why Typer and not better Click?" should
   be answerable from the ADR alone.
2. **Did I name the bottleneck in concrete terms?** Numbers, file
   paths, specific conditionals, a benchmark.
3. **Did I address the strongest realistic alternative, including
   "keep doing what we do"?**
4. **Does the Consequences section have a real cost, not just
   trade-off theatre?**
5. **Would a contributor disagreeing with this decision get a fair
   answer, or would they need to ask the author?**

If any answer is no, the ADR is not ready. The fix is rarely to add
sections. It is usually to cut filler and add specificity.

## Operations

- **Location.** `docs/adr/NNNN-kebab-case-title.md`. Number is
  monotonic and never reused. Title is verb-first when natural
  ("replace-cli-builder-with-typer"), noun otherwise.
- **Append-only.** Do not edit an accepted ADR's content. Edits to
  fix typos or clarify wording are fine; substantive changes require
  a new ADR that supersedes the old one.
- **Status updates.** When a new ADR supersedes an old one, edit the
  Status line of the old ADR to read `Superseded by ADR NNNN
  (YYYY-MM-DD)`. This is the only allowed content edit to an accepted
  ADR.
- **Length.** No upper bound, but a good ADR is rarely over 250 lines.
  If it is longer, ask whether some content belongs in the proposal
  or design doc instead.
- **One decision per ADR.** A single ADR captures a single choice. If
  the change bundles two decisions, write two ADRs that cross-reference.

## Example

The canonical worked example in this repo is `0001-typer-cli.md`. Read
it as the shape these files should take: named bottleneck, alternatives
considered including "keep what we have", explicit comparison against
the closest realistic option ("better Click"), concrete trade-offs in
Consequences (including disabled completion subcommands and the
list-of-BaseModel passthrough), references to the spike and proposal.

## References

- [Michael Nygard, "Documenting Architecture Decisions" (2011)](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [MADR (Markdown ADR) template](https://adr.github.io/madr/)
- [Y-statement format (Olaf Zimmermann)](https://medium.com/olzzio/y-statements-10eb07b5a177)
- [How to create ADRs, and how not to (Zimmermann)](https://www.ozimmer.ch/practices/2023/04/03/ADRCreation.html)
- [adr.github.io: ADRs index](https://adr.github.io/)
