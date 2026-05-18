---
id: "0007"
status: accepted
date: 2026-05-18
last_reviewed: 2026-05-18
supersedes: []
superseded_by: null
tags: [docs, adr, infrastructure, process]
deciders: [Denis Tomilin]
---

# ADR 0007: ADR system design — frontmatter, auto-INDEX, no static site

## Status

Accepted, 2026-05-18. This ADR records the **why** behind the ADR
system itself. The **how** (template prescription, sections, anti-
patterns, smell test) is documented in `docs/adr/README.md`.

## Summary

In the context of a2kit's need for a durable architecture-decision
record readable by both AI agents and humans, facing a 2026
ecosystem split between full-featured static-site renderers
(`log4brains`, Node) and bare markdown templates (`MADR`, `adr-tools`),
we decided to ship our own thin three-layer system — Nygard-style
prose template + YAML frontmatter validated against
`docs/adr/schema.json` + auto-generated `INDEX.md` rendered by
`scripts/adr_index.py` — and against adopting any off-the-shelf tool
wholesale, to achieve agent-loadable metadata (the INDEX),
human-readable narrative (the prose ADRs), and zero non-Python
toolchain, accepting that we maintain a ~200-line generator script
that orchestrates three mature libraries (`python-frontmatter`,
`jsonschema`, `jinja2`).

## The problem

a2kit's primary ADR reader is an **AI agent**. The secondary reader
is a contributor (human or AI) using a chat or IDE interface. There
is no third reader profile (no docs-site visitors, no marketing-
adjacent surface).

Off-the-shelf ADR tooling in 2026 splits along three axes:

- **Agent vs human optimization.** `log4brains` renders HTML for
  humans; agents do not benefit. `adr-tools` and `MADR` produce
  raw markdown; both audiences can read it, but neither gets
  agent-specific affordances (structured frontmatter for grep).
- **Toolchain footprint.** `log4brains` is Node.js. `pyadr` is
  pre-alpha Python. `adr-tools` is bash. `MADR` is pure markdown
  (no toolchain). a2kit's existing stack is uniformly Python via
  `uv`; mixing in Node or bash adds operational surface for every
  contributor and every CI environment.
- **Activity signal.** Most ADR tools have one active maintainer
  or are frozen. `log4brains` is alive but slowing; `adr-tools`
  hasn't shipped meaningfully since 2017; `adr-manager` is dead;
  `MADR 4.0` is the de-facto markdown template but is just a
  template, not a tool.

The concrete questions a2kit had to answer:

1. **Template shape** — strict MADR 4.0 (enumerated pros/cons), or
   Nygard-style prose with Y-statement summary?
2. **Frontmatter** — none (pure prose), inline (HTML comments), or
   structured YAML at the top of the file?
3. **INDEX** — none (let agents `grep`), manually maintained,
   tool-generated, or part of a rendered site?
4. **Static site** — yes (humans get a graph view), or no (agents
   and humans share the markdown substrate)?

Without recording the answers, every future "should we add X?"
filing would re-litigate the same trade-offs.

## What we considered (and why this one)

### Option 1: Adopt `log4brains` wholesale

Get the full ADR experience: timeline, supersession graph, hot
reload, search, hosted site.

Why it lost: Node toolchain in a Python repo for an audience
(agents) that does not consume HTML. The features are real but the
intended audience is wrong. Speculative buy.

### Option 2: Adopt `MADR 4.0` template, no tooling

Use the de-facto markdown template; let agents `grep` raw files;
no INDEX, no validation, no generator.

Why it lost: agents loading every ADR body to scan for relevance
burns tokens. A condensed agent-loadable INDEX is high-leverage. No
frontmatter validation means structural drift (status typos,
missing fields, broken supersession links) goes undetected. The
template alone is half a system.

### Option 3: Hybrid — MADR 4.0 + adr-log + check-jsonschema

Standard pieces: MADR template, `adr-log` (npm) for index generation,
`check-jsonschema` (Python) for frontmatter validation.

Why it lost: `adr-log` produces only a basic linked list (`ADR-0001
| Title`), not the rich INDEX we want (status, tags, Y-statement).
`check-jsonschema` has no native frontmatter-extraction mode (only
azure-pipelines / gitlab-ci transforms). The combination delivers
less than what we want and still adds Node (adr-log). All cost, no
fit.

### Option 4: Thin custom layer over mature libraries (chosen)

Own only the orchestration:

- **Template** — Nygard prose with mandatory `## Summary` Y-statement
  (closer to ozimmer.ch's MADR-with-Y than strict MADR). README.md
  prescribes the sections.
- **Frontmatter** — YAML at the top, validated against
  `docs/adr/schema.json` (JSON Schema 2020-12). The agent-grep layer.
- **INDEX** — `scripts/adr_index.py` (~200 LOC) orchestrating
  `python-frontmatter` + `jsonschema` + `jinja2`. Generates
  `docs/adr/INDEX.md` with id, status, title, tags, Y-statement,
  supersession sections.
- **No static site.** INDEX.md plus GitHub's native markdown
  rendering covers the human case at the current scale.

Why it wins:

- **Single audience optimization.** Agents get structured frontmatter
  and a condensed INDEX. Humans browsing via GitHub get markdown
  rendered for free. No content layer optimized for an audience that
  does not exist.
- **Python-only toolchain.** Every contributor already has
  `uv run`; nothing new to install for ADR work after `make bootstrap`.
- **Mature dependencies.** All three libraries
  (`python-frontmatter`, `jsonschema`, `jinja2`) are widely deployed.
  The orchestration script is small enough to read in one sitting
  and contains no bespoke YAML or markdown parsing.
- **Staleness-proof by construction.** `scripts/adr_index.py --check`
  in pre-commit blocks any commit where frontmatter is invalid or
  INDEX is stale. Deterministic, no LLM in the loop.

### Option 5: Defer everything — write ADRs as plain markdown, decide later

Why it lost: this is the trajectory that produces inconsistent ADRs
(some with frontmatter, some without, some MADR-shaped, some Nygard-
shaped) and forces a later cleanup that touches every file. Cheap
now, expensive later.

## The decision

a2kit ships its own ADR system, composed of:

| Layer | Surface | Tool |
|-------|---------|------|
| Template prescription | `docs/adr/README.md` | Doctrine (this is the how-to) |
| Frontmatter contract | `docs/adr/schema.json` | JSON Schema 2020-12 |
| Frontmatter validator | `scripts/adr_index.py --check` | `jsonschema` library |
| INDEX generator | `scripts/adr_index.py` | `python-frontmatter` + `jinja2` |
| Staleness gate | `.pre-commit-config.yaml` (`adr-index` hook) | `pre-commit` |
| Human navigation | GitHub markdown rendering | (no build step) |
| Agent navigation | `docs/adr/INDEX.md` (~ hundreds of tokens) | (already loaded by CLAUDE.md pointer) |

No `log4brains`, no `adr-tools`, no static-site renderer, no Node
toolchain.

### Specific sub-decisions captured here

1. **Template is Nygard prose with mandatory Y-statement Summary**,
   not strict MADR 4.0. Reason: Y-statements compress an entire
   decision into ~200 tokens — invaluable for the INDEX. Strict MADR's
   enumerated pros/cons is fine for some teams but doesn't add
   agent-readability over our prose template.
2. **Frontmatter is mandatory and validated.** Reason: agents
   scanning by `tags: [...]`, `status: ...`, `supersedes: [...]` need
   guaranteed structure. Optional frontmatter is no frontmatter for
   automation.
3. **INDEX is auto-generated, never hand-edited.** Reason: drift
   between source ADRs and a hand-maintained index is the
   single most predictable doc-rot failure.
4. **No static-site renderer.** Reason: the primary reader is an
   agent; humans get rendered markdown free via GitHub. Adopting
   `log4brains` is revisitable when ADR count exceeds ~30 and a
   contributor reports concrete navigation pain.

## Consequences

### Positive

- One toolchain (`uv`) for everything in the repo, including ADR
  authoring.
- Agents load `docs/adr/INDEX.md` once and have the complete decision
  landscape in a few hundred tokens.
- Frontmatter validation catches structural drift before it lands.
- INDEX freshness is enforced by pre-commit; no manual upkeep.
- The system documents itself recursively — this ADR explains the
  ADR system; ADR 0005 explains the doctrine that mandates ADRs; the
  doctrine adopts itself by example.

### Negative

- We own a ~200-line generator script (`scripts/adr_index.py`). It
  is small and uses mature libraries, but it is ours to maintain.
  Any bugs in INDEX rendering or frontmatter validation fall on us,
  not an upstream maintainer.
- Contributors arriving from teams that use `log4brains` will look
  for `log4brains preview` and not find it. The README and this ADR
  answer the question, but the friction is real for the first 10
  seconds.
- The template prescription in README.md is a2kit-specific. An author
  who knows MADR 4.0 still has to read the README to learn our
  conventions. The cost is one file read.
- No supersession graph. With six ADRs the supersession links in
  INDEX.md are sufficient. With fifty, a graph might be missed.
  Revisitable.
- The "no static site" stance is a deferral, not a foreclosure. If
  the human-navigation case strengthens, a follow-up ADR can adopt
  `log4brains` (or MkDocs Material if a2kit grows a broader docs
  site) — this ADR does not block that.

### Revisit triggers

This ADR holds until any of:

- ADR count exceeds ~30 AND a contributor reports concrete
  navigation pain that INDEX.md does not solve.
- a2kit grows a full docs site (MkDocs Material, Diátaxis, etc.) for
  other reasons, in which case ADRs naturally embed and the static-
  site question changes shape.
- `scripts/adr_index.py` exceeds ~400 LOC, signalling that the
  "thin orchestration" claim is no longer honest and we should
  consider replacing custom code with a third-party tool that
  matches our needs.
- A second consumer audience emerges (e.g. external contributors
  browsing decisions before filing PRs) and the markdown-only
  surface is reported as insufficient.

If a revisit fires, write a follow-up ADR superseding this one.

## References

- `docs/adr/README.md` — the template prescription (sections, anti-
  patterns, smell test). This ADR records the *why*; the README is
  the *how*.
- `docs/adr/schema.json` — frontmatter contract enforced by
  `scripts/adr_index.py`.
- `scripts/adr_index.py` — the generator + validator. Read the
  module docstring for the data model.
- `docs/adr/INDEX.md` — the agent-loadable entry point this ADR
  sanctions as the sole presentation layer.
- ADR 0005 — the doctrine that mandates ADRs as the canonical
  decline-class response medium. ADR 0007 is the infrastructure ADR
  0005 depends on.
- Research note (not in repo): 2026 ADR tooling landscape —
  `log4brains` is the active leader; `adr-tools` is frozen;
  `MADR 4.0` is the de-facto template; AGENTS.md is the Linux
  Foundation-backed agent-instruction standard; no off-the-shelf
  tool generates the rich agent-loadable INDEX a2kit needs.
