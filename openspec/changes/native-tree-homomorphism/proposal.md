## Why

a2kit's `App → Router → verb` tree is **flattened** onto each transport
today rather than **mounted level-for-level** onto that transport's
native composition tree. Every surface walks `runtime.tools()` and emits
one flat node per descriptor:

- **MCP** (`packages/mcp/server.py`) registers every tool on the *root*
  `FastMCP` server under its bare `meta.tool_name` (= `fn.__name__`,
  `app.py:578`). It never calls `FastMCP.mount(namespace=…)`, so the
  router slug is on the descriptor but absent from the wire name. Two
  routers each defining `update` collide silently on the one flat MCP
  namespace.
- **HTTP** (`packages/http/build.py`) adds `POST /api/{desc.name}` on the
  *root* FastAPI app for each tool; it never calls
  `include_router(prefix=…)`.
- **CLI** (`packages/cli/builder.py`) already builds a per-router
  sub-Typer (`add_typer`), so it is the *one* surface that partially
  mirrors the tree — but it renders `app <slug> <leaf>` (god-view
  nesting), out of step with the flat names the network surfaces use.

The defect is structural: there is **no namespace homomorphism**. The
slug exists on the descriptor (`router-conventions`) but is not the
namespace on any network surface, so the MCP collision class is reachable
by construction. This is friction #3 from the a2kay round and decision 3
of [ADR 0028](../../../docs/adr/0028-unified-surface-architecture.md).

## What Changes

Mount the App/Router tree onto each transport's **native** tree at each
level, and adopt **flat canonical names** with a verbatim escape hatch.

1. **Tree-mount homomorphism (decision 3).** Each surface materializes
   `App ↔ native-app`, `Router ↔ native-router`:
   - HTTP: `FastAPI.include_router(APIRouter, prefix=…, tags=[slug])`.
   - MCP: `FastMCP.mount(sub_server, namespace=slug)` (verified:
     `entity` + `update` → `entity_update`).
   - CLI: `Typer.add_typer(sub_typer)` (already present).
   The parity axis is **ours↔native at each level**, never `App↔Router`.

2. **Flat canonical names (decision 5).** A descriptor's identity stays
   *structured* (`router_slug` + `leaf`); each surface renders the **same
   flat string**. Name-resolution precedence (one rule, every surface):

   ```
   canonical_name(verb) =
      explicit canonical_name_override="…"  →  used VERBATIM, no slug prefix
      else, under a Router                  →  f"{slug}_{leaf}"   (leaf = fn.__name__)
      else, app-level verb                  →  leaf
   ```

   A pinned `canonical_name_override` is **complete** — the slug is never
   re-applied (`canonical_name_override="jira_search"` under `slug="jira"`
   stays `jira_search`, never `jira_jira_search`). A pin is constrained to
   `[A-Za-z0-9_]` and is surface-flat by definition.

3. **`canonical_name_override` field on the verb decorators.** New
   keyword on `@a2kit.read` / `.write` / `.list_`; recorded on
   `A2KitMeta` and projected to `ToolDescriptor`; consumed by the one
   `resolve_canonical_name(descriptor)` resolver every surface uses.

4. **Grouping without an extra drill-in trip.** Flat names still cluster
   in discovery UIs via presentation metadata: CLI
   `rich_help_panel=<slug>`; HTTP `add_api_route(tags=[<slug>])` /
   `include_router(tags=[<slug>])`. MCP is the only flat namespace;
   CLI/HTTP are naturally hierarchical and group flat names visually.

## Capabilities

### Modified Capabilities

- `core-composition` — App/Router composition now produces a **tree
  mounted level-for-level onto each surface's native tree**, not a flat
  node list. Composition records `router_slug`+`leaf` per verb so every
  surface can render the canonical name from one resolver.
- `router-conventions` — a Router mounts as a **native sub-router** under
  its `slug` (include_router / mount / add_typer); auto-derived router
  verb names become `slug_leaf`.
- `http-surface` — projection tools mount via `include_router(prefix,
  tags=[slug])`; routes carry the flat canonical name and are grouped by
  slug `tags` in OpenAPI/Swagger.
- `tool-descriptors` — `ToolDescriptor` gains `canonical_name_override`
  and the **canonical-name resolution** contract (override → `slug_leaf`
  → `leaf`); `descriptor.name` resolves through it.
- `mcp-tool-annotations` — MCP tool names are the **flat `slug_leaf`**
  (bare `leaf` at app level) produced by `mount(namespace=slug)`, and
  `canonical_name_override` is honored verbatim.

## Impact

- **Affected code**: `packages/mcp/server.py` (root-register → `mount`
  per router), `packages/http/build.py` (root routes → `include_router`),
  `packages/cli/builder.py` (flat-name + `rich_help_panel` rendering),
  `metadata.py` / `tool.py` / `app.py` (the `canonical_name_override`
  field + `resolve_canonical_name` resolver).

- **BREAKING — but ONLY the auto-derived (unnamed) router verbs.** Names
  carry **no prefix today** (`desc.name` = `meta.tool_name` =
  `fn.__name__`, confirmed at `app.py:578`), so today's *explicit* names
  already equal their post-change values. The consequence:

  | Verb authored as | Today's name | Post-change name | Changed? |
  |---|---|---|---|
  | `Entity(slug="entity")` `@read def update` (no name) | `update` | `entity_update` | **YES** (auto-derived) |
  | `Entity(slug="entity")` `@read def search` (no name) | `search` | `entity_search` | **YES** (auto-derived) |
  | `@a2kit.read(name="jira_search")` (explicit) | `jira_search` | `jira_search` | NO (verbatim) |
  | app-level `@app.read def health` (no router) | `health` | `health` | NO (bare leaf) |
  | CLI rendering of a router verb | `app entity update` | `app entity_update` | flat name only |

  Consumer migration is two mechanical steps: (a) rename the decorator
  kwarg `s/name=/canonical_name_override=/` with **tool-name values
  unchanged** (an explicit name is already the full name), and (b) accept
  the rename of the genuinely-unnamed router verbs to `slug_leaf` (or pin
  them with `canonical_name_override` to keep the old bare name). Imposes
  on a2atlassian / a2db / a2web; each `update`-style collision they were
  living with disappears by construction.

- **Co-ship dependency (Wave 2).** This change is BREAKING and co-ships
  with `surfaces-projection-axis` and `router-class-auto-collect` (the
  rename + the new axis + the authoring shape are one breaking surface)
  and with `app-as-peer-root`. It is **gated behind Wave 1
  `cli-as-surface`** (the homomorphism needs all three surfaces uniform).

## Non-goals

- **Not** the nested-CLI layout. The CLI default stays **flat**
  (`app entity_update`); `CliConfig.layout = "nested"` is a future
  flag-flip enabled by keeping identity structured — out of scope here.
- **Not** the `surfaces` projection matrix (sibling Wave 2 change
  `surfaces-projection-axis`); this change keeps using the
  visibility/expose vocabulary as it stands at co-ship time.
- **Not** the `router-class-auto-collect` authoring shape (sibling
  change); the `@a2kit`-marked-method collection is its own delta.
- **Not** global name-uniqueness enforcement (the lint rule + runtime
  `validate_composition`); decision 6 lands in Wave 3
  `validate-composition` + the lint track. This change only defines the
  *resolver* those layers run over.
- **Not** changing per-surface error rendering, DI, or auth.
