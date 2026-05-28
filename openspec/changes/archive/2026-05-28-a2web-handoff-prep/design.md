## Context

a2web's `~/Workspaces/a2web/docs/history/A2KIT_WISHES_DEFERRED.md`
catalogues 5 wishes accumulated over rounds 10-12. This change ships 3
of them; the remaining 2 are deferred:

- **In scope:** A1 formatter exclude_empty, A2 runtime tool selection,
  A3 Lazy/LddEmission top-level promotion
- **Deferred:** LDD severity levels (bigger design; not blocking),
  `a2kit.desc()` sugar (refused under Article VI — pydantic-sacred)

Each change is small and orthogonal but bundled so a2web's upgrade
work picks them up in one a2kit release cut, not three.

## Goals / Non-Goals

**Goals:**
- A1: Per-call or per-model opt-in to empty-field pruning.
  Schema/output-shape unchanged by default.
- A2: Runtime tool-subset selection via env or CLI flag. No code
  changes required at the product level to ship a tool-filtered build.
- A3: Top-level `a2kit.Lazy` and `a2kit.LddEmission`. Documentation
  positions `a2kit.packages.*` as private.

**Non-Goals:**
- Server-side filtering of tool *output* fields (out of scope; only
  empty-field pruning).
- Per-request tool selection (only server-start).
- Dynamic tool registration (compile-time + start-time only).
- `a2kit.desc()` shorthand sugar (refused under Article VI).
- LDD severity levels (deferred to a separate change).

## Decisions

### Decision 1 — A1: model-level marker, not formatter kwarg

`format_response` is called deep in the dispatch pipeline and doesn't
know whether the consumer wants empty pruning. The cleanest opt-in is
**a model-level marker on the return type**: add a `prune_empty: bool`
attribute to a return type's pydantic config (via a small
`a2kit.formatter` helper or via `model_config`), and have
`format_response` consult it.

```python
from a2kit.formatter import prune_empty

class FetchResponse(BaseModel):
    url: str
    byline: str | None = None
    next_links: list[Link] = []
    model_config = prune_empty()  # opt-in marker
```

Alternative considered: a `format_response(..., exclude_empty=True)`
kwarg threaded through dispatch. Rejected — would need plumbing through
4 stages and every surface to expose the flag; the model-level marker
is local to the type and surfaces don't need to know.

Alternative considered: model serializer (`@model_serializer(mode="wrap")`)
helper. Rejected — that's what a2web has TODAY as the workaround;
adopting the workaround as the official API doesn't reduce LOC.

### Decision 2 — A1: empty = `None | "" | [] | {}` only

Match a2web's existing `_prune_wire` definition. `0`, `False`, and
`Decimal(0)` are NOT empty — they carry information. Future
extensions (per-field exclusion rules) are out of scope.

### Decision 3 — A2: env var + CLI flag, intersection semantics

```
A2KIT_TOOLS=ask,refresh        # env var (comma-separated tool names)
serve --tools=ask,refresh      # CLI flag
```

Both apply at `build_mcp_server` / CLI-build time. Intersection
semantics: when both are set, the more restrictive set wins (env
intersect CLI). Unknown tool names fail closed with a clear error.

The selector runs AFTER compile-time `visibility=` filtering, so
`visibility="hidden"` tools cannot be re-enabled via env. The env-flag
is a SUBSET selector, not an override.

Alternative considered: per-surface flag (`--mcp-tools=`,
`--cli-tools=`). Rejected — would multiply complexity for a use case
nobody has (a2web wants the same subset on both).

### Decision 4 — A2: implementation seam

Add a new `runtime_tool_selection` module under
`a2kit.packages.serve` (or a new `a2kit.packages.runtime_tools`):
- Parses env + CLI args
- Validates against the descriptor set
- Returns a `frozenset[str]` of allowed tool names
- Consumed by `build_mcp_server` (filters before FastMCP registration)
  and by CLI builder (filters before Click subcommand registration)

This is one filter applied at two surfaces, not two implementations.

### Decision 5 — A3: re-export, not move

`a2kit.Lazy` and `a2kit.LddEmission` are added as **re-exports** in
`a2kit/__init__.py`. The canonical implementations stay at
`a2kit.packages.di.Lazy` and `a2kit.packages.ldd.LddEmission`. Both
import paths continue to work; the top-level is canonical going
forward.

Update README + relevant docstrings to use the top-level paths.
Document `a2kit.packages.*` as "private; do not import directly outside
the substrate" in `CONSTITUTION.md` Article VI or in a separate
`a2kit.packages.__init__` docstring.

### Decision 6 — Surface vocabulary check (Article VI)

| Symbol | Public name | Consumer-facing? |
|---|---|---|
| `prune_empty()` (A1 marker helper) | YES — new | yes (return-type config) |
| `--tools=` / `A2KIT_TOOLS=` (A2 selector) | YES — new | yes (operator surface) |
| `a2kit.Lazy` (A3 re-export) | NO new symbol | yes (already existed) |
| `a2kit.LddEmission` (A3 re-export) | NO new symbol | yes (already existed) |

Net new consumer concepts: 2 (`prune_empty` marker, `--tools` flag).
Within Article VI's ≤2 per minor-release budget. PASS.

## Risks / Trade-offs

- **Risk:** A1 model-level marker means schema and payload can
  desync (schema advertises optional fields, payload omits them when
  empty). Mitigation: documented behavior; consumers opt in
  knowingly; the JSON schema's `required` set still reflects what's
  always present.
- **Risk:** A2 env-var name (`A2KIT_TOOLS`) might collide with future
  tool-related env vars. Mitigation: explicit naming
  (`A2KIT_TOOLS_SELECT` could be safer); decide during implementation.
- **Trade-off:** A2 forbids overriding `visibility="hidden"`. A
  more flexible design would allow ops to surface hidden tools via
  env. Rejected — `visibility="hidden"` is a deliberate compile-time
  signal; operators should not silently bypass it.
- **Trade-off:** A3 re-exports add 4 lines to the top-level surface.
  This pushes against Article VI's "thin core" posture. Justified
  because both symbols are already canonical at the tool seam; we're
  promoting reality, not introducing new concepts.

## Migration Plan

No migration needed. All three are additive.

For a2web's downstream cleanup (separate change, after this lands):
- A1 → delete `_prune_wire`, add `model_config = prune_empty()` to
  `FetchResponse` and `AskResponse`
- A2 → delete `ask_only: bool` setting + constructor-time
  `WebRouter.tools` rebuild; configure via `A2KIT_TOOLS=ask` or
  `--tools=ask` instead
- A3 → search-replace `from a2kit.packages.di import Lazy` →
  `from a2kit import Lazy` (and same for `LddEmission`)

Rollback: revert the change; no data migration; consumers ignore the
new optional APIs.

## Open Questions

- Final name for the A2 env var: `A2KIT_TOOLS` vs `A2KIT_TOOLS_SELECT`
  vs `A2KIT_ENABLED_TOOLS`? Resolve during implementation —
  consistency with existing env-var naming (`A2KIT_LDD__OTEL_SINK`,
  etc.) suggests `A2KIT_TOOLS` is fine since there's no nested config
  under it.
- A1 marker helper API: `prune_empty()` returning a `ConfigDict`, or
  a bare `dict` literal helper? Lean toward the function form for IDE
  discoverability.
