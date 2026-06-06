---
id: "0028"
status: proposed
date: 2026-06-06
last_reviewed: 2026-06-06
supersedes: []
superseded_by: null
tags: [surface, architecture, cli, mcp, http, authoring, naming, dependency]
deciders: [Denis Tomilin]
---

# ADR 0028: Unified surface architecture — CLI as a Surface, one `surfaces` axis, native-tree homomorphism, flat canonical names

## Status

Proposed, 2026-06-06. Captures a a2kay-feedback-driven brainstorm
(2026-06-06) that started as seven point-fixes and converged on a
single surface model. Awaits human confirmation (Constitution Phase A)
and is delivered by the change set sketched in
`docs/SURFACE_ARCHITECTURE.md` (§ Delivery). Touches ADRs 0001
(typer-cli), 0002 (author-annotation surface), 0003 (semantic-flag
vocabulary), 0004 (tiered package layout), 0010 (auth MCP-only) and
0020 (multi-surface authoring) — none are superseded; this ADR sits
above them as the surface-composition spine they each assumed but
never named.

## Summary

In the context of a2kit's surface layer — three transports (MCP, HTTP,
CLI) built by three bespoke functions, two overlapping "where does it
show" axes (`expose` for network reach, `visibility` for all/cli/hidden),
a CLI that is not a `Surface` at all, and an `App` that cannot author a
typed verb — facing seven downstream a2kay frictions that were all
symptoms of those asymmetries, we decided for one unified model — **CLI
becomes a third `Surface`; a single `surfaces` projection axis (each
surface ∈ {absent, listed, unlisted}) replaces `expose` + `visibility` +
the proposed `@cli()`; the `App → Router → verb` tree maps level-for-level
onto each transport's native composition tree (FastAPI `include_router`,
FastMCP `mount`, Typer `add_typer`) so the parity axis is *ours↔native*
not *App↔Router*; and a tool's canonical name is the flat `slug_leaf`
string rendered identically on every surface** — and against bolting a
`@cli()` decorator and an `expose=("local",)` value onto the existing
split, to achieve one composition model, one projection rule, one
canonical identifier, and structural namespacing that dissolves the MCP
collision class by construction, accepting a BREAKING rename of router
tool names on every surface (`update` → `entity_update`, `app entity
update` → `app entity_update`) plus the migration that imposes on
a2atlassian / a2db / a2web.

## Context

Seven verified frictions arrived from a2kay (the downstream consumer
rebuilt on a2kit-native). Investigated against the code, every one was
a symptom of a surface-layer asymmetry rather than an isolated bug:

| a2kay friction | underlying asymmetry |
|---|---|
| CLI dead on typer ≥0.26 (vendored click) | CLI is special-cased, not a `Surface` with its own contained `bind()` |
| No CLI-only / operator surface | two overlapping axes; `visibility="cli"` exists but is undiscoverable and **leaks on HTTP** |
| MCP tool names not router-qualified → silent collisions | MCP is the one flat namespace and the projection flattens to bare `leaf`, ignoring the `router_slug` already on the descriptor |
| `expose` validation never runs in `app.tools()` | validation lives in `build()`, not a standalone composition check |
| No transport/surface kind on the ctx | no surface owns "stamp my name on the call" because the CLI isn't a surface |
| No `McpConfig.instructions` | per-surface config exists but `bind()` doesn't read all of it |
| `A2K###` lint codes collide with ruff's noqa grammar | orthogonal DX; out of scope here |

Two load-bearing discoveries reframed the work:

1. **`visibility="cli"` already means "CLI only, hidden from
   MCP/API/GraphQL"** (`routers.py`) — and it is honored by MCP
   (`server.py` skips non-`"all"`) and the CLI, but **ignored by HTTP**
   (`http/build.py` filters only on `expose`). So the operator surface
   half-exists; the real defect is an HTTP visibility leak (CLI-only and
   `hidden` verbs are reachable as `POST /api/<name>` today).

2. **All three transports compose natively with prefixes** — FastAPI
   `include_router(prefix=)`, FastMCP `mount(namespace=)` (verified:
   `entity` + `update` → `entity_update`), Typer `add_typer`. The CLI
   already uses sub-Typers. So a `App→Router→verb` tree has a faithful
   native image on every surface.

## Decision

Five locked decisions (each confirmed in the brainstorm):

1. **CLI is a `Surface`.** `kind ∈ {NETWORK, LOCAL}` distinguishes it
   from MCP/HTTP. All three satisfy one `bind(runtime, descriptors)`
   protocol; `app.cli` becomes a peer of `app.mcp` / `app.api`. The
   typer≥0.26 vendored-click compatibility shim lives inside
   `CliSurface.bind` — contained, not smeared across the builder.

2. **One axis: `surfaces`.** A verb declares its presence as a matrix
   `{ surface → ABSENT | LISTED | UNLISTED }`. This subsumes `expose`
   (ABSENT vs present), `visibility="all"` (LISTED), `visibility="hidden"`
   (UNLISTED), and `visibility="cli"` (LISTED on cli, ABSENT on network).
   `expose`, `visibility`, and the proposed `@cli()` are all retired as
   distinct concepts — an operator command is `surfaces=("cli",)` on a
   normal verb (the verb still carries read/write semantics).

3. **Mirror the native trees (homomorphism).** `App ↔ native app`
   (FastAPI app / FastMCP root server / root Typer); `Router ↔ native
   router` (APIRouter / mounted sub-server / sub-Typer). Parity is
   *ours↔native at each level*, NOT *App↔Router*. The surface-native
   "detour" (`app.mcp` / `router.api` / …) hands the author the native
   node at that level for single-surface features, until they promote it
   to a projected verb.

4. **Fix the HTTP visibility leak.** `http/build.py` must honor the
   `surfaces` matrix exactly as MCP does. This is a correctness/security
   fix and may ship ahead of the rest.

5. **Flat canonical names.** A tool's identity stays *structured* on the
   descriptor (`router_slug` + `leaf`); each surface renders it. The
   canonical name is the flat `slug_leaf` (bare `leaf` for app-level
   verbs), rendered **identically** on MCP, HTTP, and the CLI, and used
   verbatim in the call-log/audit. Grouping survives as presentation
   metadata (`rich_help_panel` on Typer, `tags` on FastAPI) — organized
   discovery with no extra drill-in trip. Because identity is never
   collapsed to a bare string up front, a future **nested CLI layout**
   (`app entity update`) is a `CliConfig.layout = "flat" | "nested"`
   flag-flip, not a rewrite.

### How the seven frictions resolve

```
#1 vendored click   → contained in CliSurface.bind
#2 operator surface → surfaces=("cli",) + HTTP-leak fix (#4)
#3 MCP collisions   → GONE by construction: slug is the namespace on every surface
#5 surface on ctx   → each Surface stamps its own name as it dispatches
#6 mcp.instructions → McpSurface.bind reads its full McpConfig
#4(list) validate   → "resolve the surfaces matrix for every verb, offline"
#7 lint codes       → orthogonal; tracked separately
```

## Consequences

**Positive.**

- One composition model, one projection rule, one canonical identifier.
  The MCP collision class is impossible by construction (the slug is the
  namespace, same as the CLI has always had).
- `expose` + `visibility` collapse from two overlapping axes to one
  matrix — the redundancy a consumer kept tripping on disappears.
- The CLI joins the uniform surface set; `app.cli` parity falls out;
  the typer-compat risk is quarantined in one `bind()`.
- The flat name is the *same string* you type on the CLI, call over MCP,
  POST to HTTP, and read in the audit log — one identifier to teach,
  grep, and document. Aligns with the MCP ecosystem convention
  (`jira_get_issue`).
- Future nested-CLI is a config flag, not a migration.

**Negative / accepted.**

- **BREAKING tool-name rename on every surface.** Router verbs go from
  bare `update` (MCP/HTTP) and `app entity update` (CLI) to
  `entity_update` everywhere. a2atlassian, a2db, a2web all rename their
  router-scoped tools. Ships with a migration table; on-brand with this
  repo's recent breaking cutovers, but real work for consumers. (The
  soften-to-opt-in alternative — flat-unless-collision — was considered
  and rejected for reintroducing a special case into an otherwise
  uniform rule. Open for re-litigation before the breaking change lands.)
- The CLI trades `git`-style subcommand drill-in for flat
  underscore-named commands (mitigated by `rich_help_panel` grouping and
  tab-completion). Acceptable for operator/agent tooling, not a polished
  consumer CLI — and reversible via the `layout` flag.
- `App` gains a typed-verb front door it never had; the surface protocol
  grows a `kind` and a name-rendering responsibility. Net new machinery,
  delivered in waves (see `docs/SURFACE_ARCHITECTURE.md`).

## Open questions (carried into the design doc)

- **Embrace vs soften the MCP-name break** (the one big real-world call).
- **UNLISTED spelling** under "just surfaces" (dict form vs tuple
  shorthand + escape).
- **Router native detours** — all three (`router.mcp/api/cli`) day one,
  or `api` first?

## Related

- `docs/SURFACE_ARCHITECTURE.md` — the full model, diagrams, and the
  OpenSpec change split.
- ADRs 0001, 0002, 0003, 0004, 0010, 0020 — the surface decisions this
  one sits above.
- `docs/CONSUMER_FEEDBACK_DOCTRINE.md` (ADR 0005) — the a2kay frictions
  that drove this each get a ship/reframe answer here.
