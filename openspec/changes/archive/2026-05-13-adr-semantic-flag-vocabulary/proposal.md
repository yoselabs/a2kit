# ADR 0003: Semantic flag vocabulary (idempotent / open_world / destructive / title)

## Why

The consumption-interface audit (explore session 2026-05-13)
initially proposed collapsing the four decorator kwargs
`idempotent`, `open_world`, `destructive`, `title` into a single
`annotations={...}` dict, on the read that they were MCP-shaped
escape hatches.

The right framing surfaced in the same session: these flags are
**transport-neutral tool semantics**, not MCP escape hatches.
Every plausible transport has a meaningful read on each:

| flag           | MCP                | CLI                              | REST                       | GraphQL              |
|----------------|--------------------|----------------------------------|----------------------------|----------------------|
| `idempotent`   | `idempotentHint`   | safe to retry on ^C              | GET/PUT/DELETE vs POST     | `@safe` directive    |
| `destructive`  | `destructiveHint`  | confirmation prompt; `--yes`     | requires `X-Confirm` header | `@dangerous`        |
| `open_world`   | `openWorldHint`    | warn in `--help`                 | bypass cache; longer timeout | `@external`        |
| `title`        | `title`            | `--help` header                  | OpenAPI `summary`          | field description    |

MCP shipped the spec for these first, so they look MCP-shaped —
but they're actually a vocabulary about the tool itself,
independent of how it's exposed. This matches the ADR 0002 stance:
"the wire is plural, the author surface is singular." A flag
declared once should lift to whatever transport reads it.

Without an ADR locking the framing, the next audit will try to
collapse the kwargs again. This change captures the framing
so it sticks.

## What changes

- **ADD** `docs/adr/0003-semantic-flag-vocabulary.md` (Accepted,
  2026-05-13). Status: Accepted (current); no "Anticipated"
  block — the contract is fully active.
- The ADR documents:
  - The four-flag vocabulary as transport-neutral semantics.
  - Per-flag reads on every plausible transport (the table above).
  - The contract for adding new flags: any addition MUST have a
    meaningful read on at least two transports (so the vocabulary
    stays generic, not transport-specific).
  - The decision against collapsing into `annotations={...}` (which
    would promote MCP to a privileged transport in the surface).
  - Cross-reference to ADR 0002 (single author surface, plural wire)
    and `replace-surfaces-with-visibility` (related but orthogonal
    cleanup).
- **NO CODE CHANGES.** This is a documentation-only change to
  prevent re-litigation.

## Non-goals

- Adding new semantic flags. The current four are the locked set
  for v1.
- Changing existing flag semantics or default values.
- Touching `visibility` (different axis — routing, not semantics).

## Migration

None. Documentation-only.

## Risk

XS. Pure documentation.
