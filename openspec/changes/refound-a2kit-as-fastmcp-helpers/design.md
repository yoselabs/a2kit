# Design — re-found a2kit as à-la-carte FastMCP helpers

Delivers ADR 0032. This document is the architecture + the migration-first
sequence; the proposal is the why/what, the spec delta is the enforceable
invariant.

## The shape change

```
  OLD (framework)                NEW (à-la-carte, extractable)
  ───────────────                ─────────────────────────────
  a2kit.App  ← god object        (no App — deleted)
    ├ DI container               a2kit.tsv     → typed TSV result type +    ┐
    ├ config                     │               serializer (needs a        │ each
    ├ transports  (delete)       │               decorator — durable core)  │ depends
    ├ code-mode   (delete)       a2kit.errors  → unified error envelope      │ ONLY on
    ├ tool-failed (delete)       a2kit.rest    → verb→REST projection (opt)  │ fastmcp +
    └ everything coupled         a2kit.cli     → verb→CLI adapter (opt)      │ pydantic
                                 a2kit.lint    → static analyzer / CLI       │ + stdlib
  consumer:                                      (zero runtime coupling)    ┘
  my_server → a2kit.App          my_server → fastmcp  +  a2kit.<helper> (optional)
```

## The governing invariant (the fitness function)

**No shared a2kit core.** No `App`, DI scope, config object, or internal
substrate that helpers depend on. Each helper imports only `fastmcp`,
`pydantic`, and the standard library. The test: any helper must be liftable
into FastMCP as *copy one file + open one issue*. A change that reintroduces an
`App`-like spine, or makes one helper import another a2kit helper's internals,
is rejected by citing this design + ADR 0032 — that coupling is what the
treadmill was made of.

This is enforceable as a lint rule (a2kit already owns the lint surface,
codes `AK###`): scan each `a2kit.*` helper module's imports and fail on any
intra-a2kit import that is not the helper's own package.

## What is deleted, and why it is safe

| Surface | Why deleted | FastMCP equivalent |
|---|---|---|
| code mode | redundant | `transforms=[CodeMode()]`, Monty sandbox |
| tool-failure response wrapping | redundant | native `ToolResult(is_error=True)` |
| transport plumbing | redundant | stdio / Streamable-HTTP / WS native |
| CLI-as-framework | mostly redundant | `fastmcp generate-cli` (reconnecting client) |
| `a2kit.App` + composition spine | the coupling anchor | plain FastMCP server is the base |

§1 (delete-don't-deprecate) makes each removal a plain language-default error;
the CHANGELOG migration row is the sole consumer channel.

## What survives, and why

- **`a2kit.tsv`** — typed TSV/`page-tsv` result type + serializer derived from
  return annotations. Genuinely needs a decorator/result-type; the least
  FastMCP-overlapping piece. The durable core.
- **`a2kit.lint`** — static analyzer with zero runtime coupling, in a
  governance niche FastMCP's "unopinionated, ship-a-package" philosophy will not
  absorb. Most durable asset; also the home for the extractability lint rule.
- **`a2kit.errors` / `a2kit.rest` / `a2kit.cli`** — optional projections kept
  only while a real consumer uses them; each is an upstream-proposal candidate.

## Migration-first sequence (the follow-on changes)

Do **not** redesign a2kit in the abstract then migrate. Let one real server fix
the helper API:

1. **Pilot.** Port one representative MCP server to plain FastMCP. Where an
   a2kit feature is missed, write that helper *inline in the server repo*. Rip
   out `a2kit.App`. (BDD-first: the server's own tests are the contract.)
2. **Observe.** Note which helpers were actually reached for and their natural
   FastMCP-native signatures.
3. **Extract.** Lift the proven helpers into the new a2kit, each standalone and
   `fastmcp`-only. Delete code-mode / tool-failed / transports / `App` in the
   same pass.
4. **Migrate the rest.** Port remaining servers to FastMCP + the new helpers.
5. **Backlog.** For each helper, record the FastMCP gap it fills — that list is
   the upstream-contribution backlog (one helper → one scoped issue), the
   FastMCP-contributor pipeline that is a2kit's new strategic purpose.

## Relationship to existing decisions

- Delivers **ADR 0032**.
- On ADR 0032 acceptance: supersedes **ADR 0028** (unified-surface: `App` as one
  type, CLI-as-surface, `surfaces` axis) and **ADR 0019** (app-runtime split) —
  both presuppose the `App` this change retires.
- Deprioritizes **ADR 0031** (MCP Apps) to a thin `ui://` surface at most; rich
  multi-file UI is bundled by a JS toolchain or hosted as an external SPA, and
  FastMCP already ships prefab UI providers. SkyBridge (TS/React) owns the UI
  layer; it is not an a2kit rival.

## Open question (deferred, with trigger)

Whether `a2kit.rest` (verb→true-REST projection) and `a2kit.cli` survive long
term, or are dropped if the pilot shows consumers do not need REST+CLI from one
definition. Revisit after step 2 (Observe) — real usage decides, not this doc.
