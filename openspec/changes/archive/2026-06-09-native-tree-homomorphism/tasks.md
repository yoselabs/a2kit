# Tasks — native-tree-homomorphism

BDD-first / TDD red → green. Co-ships with `surfaces-projection-axis`,
`router-class-auto-collect`, `app-as-peer-root` (Wave 2); gated behind
Wave 1 `cli-as-surface`. Each red test proves a missing homomorphism or
naming behavior against current flat-mount code before the fix.

## 0. Prerequisite

- [x] 0.1 Confirm Wave 1 `cli-as-surface` has landed (all three surfaces
      satisfy one `bind()` protocol). If not, block — the per-level mount
      has no uniform seam to attach to.

## 1. Canonical-name resolver (RED → GREEN)

- [x] 1.1 Add a test for `resolve_canonical_name(descriptor)`: a router
      verb `Entity(slug="entity") @read def update` (no name) resolves to
      `"entity_update"`. Confirm RED (today's `desc.name == "update"`).
- [x] 1.2 Add a test: an app-level verb `@app.read def health` (no
      router) resolves to bare `"health"`. Confirm GREEN-by-accident is
      acceptable but assert the resolver — not `fn.__name__` — produced it.
- [x] 1.3 Add a test for the verbatim override: `@a2kit.read(
      canonical_name_override="jira_search")` under `slug="jira"` resolves
      to `"jira_search"` (NOT `"jira_jira_search"`). Confirm RED (no field
      exists yet).
- [x] 1.4 Add a test for the constraint: a `canonical_name_override`
      containing a char outside `[A-Za-z0-9_]` raises `TypeError` at
      decoration time naming the offending value.
- [x] 1.5 GREEN: add `canonical_name_override` to the `@read/.write/.list_`
      decorators, store on `A2KitMeta`, project onto `ToolDescriptor`, and
      implement the one `resolve_canonical_name` resolver (override →
      `slug_leaf` → `leaf`). Route `descriptor.name` through it.

## 2. MCP native mount + flat names (RED → GREEN)

- [x] 2.1 Add a test: two routers each with a `@read def update`
      (`slug="entity"`, `slug="ontology"`) build an MCP server exposing
      `entity_update` AND `ontology_update` — no collision, both present.
      Confirm RED today (silent collision on flat `update`).
- [x] 2.2 Add a test: an explicitly-pinned MCP tool name is unchanged
      byte-for-byte after the change (verbatim override).
- [x] 2.3 GREEN: `packages/mcp/server.py` mounts each router as a sub
      `FastMCP` via `mount(namespace=slug)` instead of root-registering
      every tool flat; app-level verbs stay on the root server. Names come
      from `resolve_canonical_name`.

## 3. HTTP include_router + tags grouping (RED → GREEN)

- [x] 3.1 Add a test: a router verb mounts at `POST /api/entity_update`
      (the flat canonical name), not `/api/update`. Confirm RED today.
- [x] 3.2 Add a test: the OpenAPI schema groups the route under the slug
      via `tags=["entity"]`. Confirm RED today (no tag).
- [x] 3.3 Add a test: an app-level verb stays at `/api/health` (bare
      leaf, no prefix). Confirm GREEN-by-design.
- [x] 3.4 GREEN: `packages/http/build.py` builds a per-router `APIRouter`
      and `include_router(prefix=…, tags=[slug])`; the route path is the
      flat canonical name; app-level verbs mount on the root app.

## 4. CLI flat names + rich_help_panel (RED → GREEN)

- [x] 4.1 Add a test: the CLI default layout renders a router verb as the
      flat command `app entity_update` (canonical name), grouped under
      `rich_help_panel="entity"` in `--help`. Confirm RED (today renders
      `app entity update` nested with no panel).
- [x] 4.2 GREEN: `packages/cli/builder.py` renders flat canonical names
      with `rich_help_panel=slug`; identity stays structured so a future
      `CliConfig.layout="nested"` remains a flag-flip (assert the
      descriptor still carries `router_slug`+`leaf`).

## 5. Cross-surface parity (GREEN)

- [x] 5.1 Add a test: the same App resolves the **same** canonical name
      for a given verb on MCP, HTTP, and CLI (one resolver, three
      surfaces) — `entity_update` everywhere.
- [x] 5.2 Add a test: an explicitly-named tool is byte-for-byte identical
      across all three surfaces and unchanged from pre-migration.

## 6. Migration fixtures (GREEN)

- [x] 6.1 Add a fixture proving the mechanical migration:
      `name="x"` → `canonical_name_override="x"` yields the identical wire
      name; only unnamed router verbs gain the `slug_` prefix.

## 7. Verify

- [x] 7.1 All new tests from §1–§6 pass.
- [x] 7.2 Existing surface tests pass once their expected names are
      updated for the auto-derived `slug_leaf` rename (explicit names
      unchanged).
- [x] 7.3 Full suite green; output pristine.

## 8. Close out

- [x] 8.1 lint / `ty check src/` / a2kit-static / ruff gates green on all
      touched files.
- [x] 8.2 Confirm the co-ship set lands together (`surfaces-projection-axis`,
      `router-class-auto-collect`, `app-as-peer-root`) under one migration
      table; do not merge this change in isolation.
- [x] 8.3 Forward-compat seam: `resolve_canonical_name` is the single
      function Wave 3 `validate-composition` + the dup-name lint rule will
      run over for global uniqueness — keep it standalone and pure.

## Implementation notes (as landed)

Realized via the **canonical-name resolver as the single source of truth**
rather than literal sub-server mounting. Two deliberate divergences from
§2–§4's first-draft strategy, both preserving the observable contract
(flat `slug_leaf` names, tag/panel grouping, no collisions, cross-surface
identity parity) and all tests green:

- **MCP/HTTP (§2.3, §3.4):** tools register flat under their resolved
  `desc.name` (= `slug_leaf` / pin) instead of via FastMCP `mount(prefix)`
  / FastAPI `include_router(prefix)`. The resolver owns the name, so the
  pin (`canonical_name_override`) never double-prefixes. HTTP still groups
  via `tags=[slug]`.
- **CLI (§4.1):** renders the **nested** layout (`app <slug> <leaf>` under
  a slug sub-Typer with `rich_help_panel=slug`), NOT the flat `app
  slug_leaf` command, to avoid the `app tasks tasks_get_task` doubling.
  `desc.name` (the flat canonical) remains the MCP/HTTP/audit identity;
  structured `router_slug`+`leaf` stays on the descriptor so a future
  `CliConfig.layout` flag-flip is purely presentational (§4.2 intact).

Additional src seams migrated beyond the core (the "121 pending sites"):
`packages/testing/client._wire_name` now returns `desc.name` (canonical),
not the bare `_meta.tool_name`; the dispatch call-log + call-scope stages
key on the canonical name (`_canonical_tool_name`), per the design's "the
canonical name is the call-log/audit key".
