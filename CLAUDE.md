# a2kit — Claude Code overlay

**Tool-agnostic conventions live in [`AGENTS.md`](AGENTS.md).** Read
that file first; it sets the rules for working on a2kit (core
principles, patterns, anti-patterns, workflow, architecture strategy,
project state hooks). This file overlays Claude-specific behaviour
only.

If `AGENTS.md` and `CLAUDE.md` disagree on any tool-agnostic rule,
`AGENTS.md` is canonical and this file gets corrected.

## Claude-specific overlay

### Memory hygiene

The user's Claude Code auto-memory lives at
`~/Documents/Knowledge/Agents/Claude/MEMORY.md`. When a session
changes a2kit's design state meaningfully, update
`project_a2kit_design_state.md`. Delete obsolete `feedback_*`
memories when their issue resolves.

### Loading priority for Claude sessions

When starting a Claude Code session in this repo, the recommended
context-loading order is:

1. `AGENTS.md` (tool-agnostic conventions — loaded automatically).
2. `CLAUDE.md` (this file — Claude-specific overlay; auto-memory
   reminders).
3. **`CONSTITUTION.md`** (the rules above the rules; substrate/product
   governance for the a2 ecosystem — read before any non-trivial
   change). Currently Phase A: agents apply, human confirms each
   Constitution-touching change. Articles VIII's mechanical
   enforcement layer is `[pending]`.
4. `docs/adr/INDEX.md` (decision log entry point; ~hundreds of tokens,
   covers every recorded ADR with status + tags + Y-statement).
5. Specific ADR bodies as needed (follow links from INDEX).
6. `BACKLOG.md` if planning new work.

This split keeps Claude's instruction budget under the empirical
~150-instruction soft cap. The bulk of project-specific guidance is
in AGENTS.md (shared); the auto-memory specifics stay here;
Constitution governs cross-cutting placement decisions.

## Related memories (in user's MEMORY.md)

- `project_a2kit_design_state` — post-v0.33 surface
- `feedback_no_prs` — solo repos merge to main directly
- `feedback_bdd_first` — write the test first
- `feedback_a2kit_ldd_wire_format` — LDD channels invariants
- `project_a2kit_format_routing` — JSON | TSV | page-tsv wire shapes
