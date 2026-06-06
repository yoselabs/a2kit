# Design — native-tree-homomorphism

> Wave 2, BREAKING. Decision record:
> [ADR 0028](../../../docs/adr/0028-unified-surface-architecture.md)
> (decisions 3 + 5); model:
> [SURFACE_ARCHITECTURE.md](../../../docs/SURFACE_ARCHITECTURE.md) §4–§5.

## 1. The homomorphism, in words

a2kit's authored tree has two composition levels: the **App** (root) and
its **Routers** (each with an explicit `slug`). Today every surface
*flattens* that tree — it walks `runtime.tools()` and emits one node per
verb on the **root** native object, throwing the slug away on the wire.
This change makes each surface **mount the tree level-for-level onto its
own native composition tree**:

```
   a2kit (authored)          FastMCP                 FastAPI                  Typer
   ────────────────          ───────                 ───────                  ─────
   App ─────────────  ↔      root FastMCP server     root FastAPI app         root Typer
   │  app-level verbs ↔      root tools              root /api routes          top-level cmds
   │
   └─ Router(slug=    ↔      sub-server, mounted     APIRouter, included       sub-Typer, added
        "entity")            via mount(             via include_router(       via add_typer(
        │                      namespace="entity")    prefix=…, tags=["entity"]) …)
        └─ verbs      ↔      entity_*                /api/entity_*             app entity_*
```

The native composition calls are all verified feasible (2026-06-06):
`fastapi.APIRouter` + `include_router(prefix=…)`,
`fastmcp.FastMCP.mount(sub, namespace="entity")` (`entity` + `update` →
`entity_update`), `typer.Typer.add_typer(sub)`.

**Parity axis (decision 3): ours↔native at each level, NOT
App↔Router.** The `App` faithfully wraps the native app; a `Router`
faithfully wraps the native router. The two roots do not need identical
menus — the contract is that each level has a faithful native image. The
surface-native detour (`configure_api` / live `app.api.*`) hands the
author the native node *at that level* for single-surface features; it is
out of scope for this change (it rides the authoring-shape and
projection-axis siblings) and is named here only to fix the boundary.

## 2. Name-resolution precedence (one rule, every surface)

There is exactly **one** resolver, `resolve_canonical_name(descriptor)`,
and every surface renders through it. Precedence:

```
   canonical_name(verb) =
      1. explicit canonical_name_override="…"   →  used VERBATIM, no slug prefix
      2. else, under a Router (has slug)        →  f"{slug}_{leaf}"   (leaf = fn.__name__)
      3. else, app-level verb (no router)       →  leaf
```

- **Step 1 wins absolutely.** A pin is a *complete* name; the slug is
  **never** re-applied. `canonical_name_override="jira_search"` under
  `slug="jira"` resolves to `jira_search`, not `jira_jira_search`.
- **Step 2** is the only place a name is *constructed*: `slug` + `"_"` +
  `fn.__name__`. This is the auto-derived case and the **only** one that
  renames versus today.
- **Step 3** is the app-level bare leaf. The **app name is identity, not
  a prefix** — it is the FastMCP server name / the CLI binary name. There
  is no `a2kay_health`.

## 3. The `canonical_name_override` verbatim rule

`canonical_name_override="…"` is the one escape hatch. Its contract:

- **Verbatim.** The string is the canonical name on every surface,
  byte-for-byte, with **no** slug prefix and **no** transformation.
- **Constrained to `[A-Za-z0-9_]`** — legal as an MCP tool name, a
  FastAPI path segment, and a Typer command name simultaneously.
- **Surface-flat by definition.** Under a future nested-CLI layout, only
  auto-derived names nest into sub-commands; a pinned name stays a flat
  top-level command.
- **Why migration is nearly free.** Names carry no prefix today
  (`desc.name` = `meta.tool_name` = `fn.__name__`, `app.py:578`), so an
  explicit name *already is* the full name. The consumer migration is a
  mechanical `s/name=/canonical_name_override=/` with the **values
  unchanged**. Only the genuinely-unnamed router verbs actually rename
  (step 2). Mixed pinning is the norm: one verb pins, the rest
  auto-derive.

## 4. Grouping mechanics per surface

Flat names must still *cluster* in discovery UIs so the author does not
pay a drill-in trip for the loss of nesting:

| Surface | Native mount | Flat name shown | Grouping affordance |
|---|---|---|---|
| **MCP** | `mount(namespace=slug)` | `entity_update` | none needed — flat namespace is the point; the slug *is* the prefix |
| **HTTP** | `include_router(prefix=…, tags=[slug])` | `/api/entity_update` | `tags=[slug]` clusters paths in OpenAPI/Swagger |
| **CLI** | `add_typer(sub)` + `rich_help_panel=slug` | `app entity_update` | `rich_help_panel=slug` clusters flat commands in `--help` |

MCP is the **only** flat namespace; CLI and HTTP are naturally
hierarchical but render the same flat canonical string by default —
which is exactly *why* collisions only ever hit MCP, and why mounting the
slug as the namespace dissolves that collision class by construction.

The flat HTTP path is `/api/{slug}_{leaf}` (the canonical name), not
`/api/{slug}/{leaf}` — the path segment is the canonical name so the wire
identifier is identical across surfaces and in the audit log. `prefix`
and `tags` carry the grouping; the rendered name carries identity.

## 5. Why identity stays structured

The descriptor keeps `router_slug` + `leaf` and only flattens at
render-name time. This keeps the door open for `CliConfig.layout =
"nested"` (sub-Typers, `app entity update`) as a pure config flag-flip,
with the **same canonical id** for logs/audit and zero re-authoring.
Flattening up front would foreclose that; we do not.

## 6. Blast radius and co-ship

- **BREAKING set = auto-derived router verbs only.** Explicitly-named
  tools are byte-for-byte unchanged (verbatim override); app-level bare
  verbs are unchanged (bare leaf). See the migration table in
  `proposal.md`.
- **Co-ships (Wave 2):** `surfaces-projection-axis` (the new placement
  matrix), `router-class-auto-collect` (the `@a2kit`-marked authoring
  shape), `app-as-peer-root` (App typed-verb front door). The rename +
  the new axis + the new authoring shape are **one breaking surface** and
  must land together with a single migration table.
- **Gated behind Wave 1 `cli-as-surface`.** The homomorphism requires all
  three surfaces to satisfy one uniform `bind()` protocol; until the CLI
  is a `Surface`, there is no uniform per-level mount to apply.

## 7. Decisions deferred out of scope

- **Global name-uniqueness enforcement** (decision 6) — the lint rule and
  the runtime `validate_composition(app)` backstop. This change defines
  the single `resolve_canonical_name` resolver they will run over, but the
  enforcement layers themselves land in Wave 3 `validate-composition` +
  the orthogonal lint-codes track.
- **Nested CLI layout** — kept reachable (§5) but not enabled.
- **The surface-native detour** — `configure_api` hook and the live
  `app.api.*` escape ride the authoring-shape / projection-axis siblings.
