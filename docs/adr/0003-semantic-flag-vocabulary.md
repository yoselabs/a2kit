# ADR 0003: Semantic-flag vocabulary on verb decorators

## Status

Accepted, 2026-05-13.

## Summary

In the context of the four kwargs `idempotent`, `open_world`,
`destructive`, `title` on the verb decorators, facing audit pressure
to collapse them into a single `annotations={...}` dict on the read
that they were MCP-shaped escape hatches, we decided to keep them as
first-class transport-neutral semantic flags and against the
`annotations={...}` collapse, to achieve a single vocabulary every
transport adapter lifts as it sees fit (MCP `ToolAnnotations`, CLI
`--help` warnings, future REST method routing, future GraphQL
directives), accepting that the vocabulary is locked at four entries
and that additions require an ADR superseding this one.

## The problem

The consumption-interface audit (2026-05-13) measured real usage of
every decorator kwarg across the in-repo examples. The numbers
for these four kwargs:

| flag         | uses in 6 example apps |
|--------------|:----------------------:|
| `title`      | 2                      |
| `idempotent` | 1                      |
| `open_world` | 1                      |
| `destructive`| 0                      |

The initial audit conclusion was: low usage + the four fields
match MCP `ToolAnnotations.idempotentHint`/`openWorldHint`/
`destructiveHint`/`title` one-for-one → these are MCP-spec escape
hatches dressed as first-class kwargs → collapse them into a single
`annotations={"idempotent": True, ...}` dict and remove 16 kwarg
slots from the decorator surface.

That reasoning was wrong. The right framing emerged in the same
session: **MCP just shipped the spec for these first.** The flags
describe properties of the tool itself, not properties of how it's
exposed via MCP. Every plausible transport has a read on each:

| flag           | MCP                | CLI                                       | REST                              | GraphQL              |
|----------------|--------------------|-------------------------------------------|-----------------------------------|----------------------|
| `idempotent`   | `idempotentHint`   | safe to retry on `^C`; `--retry` default-on | GET/PUT/DELETE vs POST routing  | `@safe` directive    |
| `destructive`  | `destructiveHint`  | confirmation prompt; `--yes` to bypass    | requires `X-Confirm` header       | `@dangerous`         |
| `open_world`   | `openWorldHint`    | warn in `--help` ("hits external")        | bypass cache; longer timeout      | `@external`          |
| `title`        | `title`            | `--help` header / `[default:]` line       | OpenAPI `summary`                 | field description    |

Collapsing into an `annotations={...}` dict would promote MCP to a
privileged transport in the author surface: dict keys would have to
match MCP's field names (`idempotentHint` etc.), and authors writing
non-MCP transports would be reaching into MCP-shaped metadata to
declare transport-neutral facts. That contradicts the contract
ADR 0002 locked in: **the wire is plural, the author surface is
singular.**

The bottleneck is not "too many kwargs"; it's that the audit's first
pass mistook transport-neutral semantics for MCP escape hatches. The
fix is not a refactor — it's a documented framing that prevents the
next audit from making the same mistake.

## What we considered

**Status quo: keep the four kwargs as first-class.** Each is one
named kwarg per verb decorator (`@a2kit.read(idempotent=True)`).
Author writes once, every transport adapter reads. Locks transport
neutrality into the surface shape. Cost: four named slots × four
verbs = 16 documented kwarg positions an author has to ignore if
they don't care. Live readers today (MCP server building
`ToolAnnotations`) work unchanged. **Chosen.**

**Collapse into `annotations={...}` dict.** One kwarg per verb,
takes a dict of MCP-shaped keys. Cuts the kwarg surface by 12 slots
across four verbs. Rejected: makes MCP the privileged shape (dict
keys = MCP field names). Future transport adapters reading the dict
would either inherit MCP key spellings (`idempotentHint`) for
non-MCP semantics, or build a parallel translation layer. Either
way, the asymmetry leaks. Same anti-pattern ADR 0002 rejected for
`typer.Option` in tool signatures: do not promote one transport
in the cross-transport author surface.

**Delete the four flags entirely.** Strongest move. Authors who
need transport-specific behaviour reach into transport-specific
escape hatches (MCP middleware, CLI `add_cli`, etc.). Rejected: the
**information** these flags carry is real. `destructive=True`
genuinely changes how a tool should be invoked — interactively
(CLI prompt), via a confirmation header (REST), with a `@dangerous`
directive (GraphQL). Forcing every transport to re-discover that
property from naming heuristics or scattered overrides loses the
single-declaration win.

**Rename to align with one transport.** E.g., `mcp_destructive_hint`,
`cli_destructive_warning`. Rejected: trades one privileged transport
for many, multiplies the surface, and still doesn't capture that
the underlying semantic ("this tool destroys data") is the same
across transports.

## The decision

**Lock the four kwargs as a transport-neutral semantic vocabulary.**

The set is fixed at v1:

| name         | type             | default | semantic                                                  |
|--------------|------------------|---------|-----------------------------------------------------------|
| `idempotent` | `bool`           | `False` | calling N times == calling once (modulo time)             |
| `open_world` | `bool`           | `False` | effects extend beyond the system (external API, hardware) |
| `destructive`| `bool \| None`   | `None`  | invocation destroys data; `None` = inherit verb default   |
| `title`      | `str \| None`    | `None`  | human-readable label                                      |

**Each flag MUST have a meaningful read on at least two transports.**
This is the contract for the vocabulary. The audit produced the table
above; future flags MUST pass the same bar.

**Transport adapters lift the flags into their native idiom.** MCP
server reads them into `ToolAnnotations`. CLI builder reads `title`
for `--help` and (in the future) `destructive`/`open_world` for
warnings. REST/GraphQL adapters, when they land, read them for HTTP
method routing and field directives respectively.

**Adding a new flag to this vocabulary requires an ADR superseding
or extending ADR 0003.** The two-transport-read bar applies. The
ADR MUST list the per-transport read for the new flag, name what it
adds that the existing four don't carry, and update the table in
this ADR (via supersession). This deliberately gates additions; the
vocabulary stays small and learnable.

**`destructive=True` on `@a2kit.read` raises `TypeError`** (current
behaviour, locked in). A read tool is non-destructive by spec; the
contract is self-documenting at the type-checker / decoration
boundary. The same constraint applies to `@a2kit.list_` (read-shaped).

## Consequences

### Positive

- **Single declaration, plural reads.** An author writes
  `idempotent=True` once; today MCP reads it, tomorrow REST reads
  it for method routing, no decorator change.
- **Audit-resistant.** This ADR is the answer to "why these four
  flags?" — future audits don't re-litigate the collapse question.
- **Bounded vocabulary.** Locked at four; additions require a
  documented case, which keeps the surface small.
- **Type-checker friendly.** Each flag is a typed kwarg; misspellings
  fail at lint time. The collapse-to-dict path would have lost that.

### Negative

- **16 kwarg positions in IDE autocomplete.** Four flags × four
  verbs (`read`/`write`/`list_`/`tool`). Authors who care about
  none of them see all four; the noise is unavoidable cost of the
  shape.
- **Vocabulary requires learning.** A new author can't infer
  "what does `open_world` mean?" from the type signature alone.
  This ADR doubles as documentation; the README and example apps
  reinforce.
- **Adding flags is gated.** Future "useful one-off" flags can't
  land as an opportunistic kwarg — the two-transport-read bar and
  the ADR requirement add friction by design. Cost: real demand
  may sit behind ad-hoc workarounds until it crosses the bar.

## References

- ADR conventions: `docs/adr/README.md`
- ADR 0002 (author annotation surface, "wire is plural, author
  surface is singular"): `docs/adr/0002-author-annotation-surface.md`
- Audit session (2026-05-13): the explore transcript that produced
  the framing this ADR locks in.
- Related change (orthogonal — routing axis, not semantic axis):
  `openspec/changes/replace-surfaces-with-visibility/` — handles
  the *transport-visibility* dimension (`visibility="cli"`); this
  ADR handles the *semantic* dimension.
- MCP `ToolAnnotations` spec: <https://modelcontextprotocol.io/specification/2025-06-18/server/tools#tool-annotations>
