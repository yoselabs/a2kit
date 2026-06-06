# Surface architecture

> Status: **design** (proposed). Decision record: [ADR 0028](adr/0028-unified-surface-architecture.md).
> Drivers: a2kay feedback round (2026-06-06). This doc is the model; the
> ADR is the decision; the OpenSpec changes (§ Delivery) are the build.

a2kit's thesis is **write one typed function → project it to many
transports.** This doc defines how that projection works once the surface
layer is unified: what a surface is, how a verb chooses which surfaces it
appears on, how the `App → Router → verb` tree maps onto each transport's
native tree, and how tools are named.

---

## 1. The current state (what we're replacing)

Three transports, built three different ways, with two overlapping
"where does it show" axes and a CLI that isn't even a `Surface`:

```
                 AUTHORING                          HONORS
SURFACE   typed-verb?  surface-native?  raw?        expose?  visibility?   is a Surface?
───────   ──────────   ───────────────  ────        ───────  ──────────    ────────────
MCP       projected    @app.mcp.tool()  –           yes      yes           yes
HTTP      projected    @app.api.get()   –           yes      NO (leak!)    yes
CLI       god-view     –                add_cli()   NO       help-only     NO (special)
```

The asymmetries this doc removes:

1. CLI is special-cased → 3 bespoke `build_*` functions instead of N uniform `bind()`s.
2. `app.mcp` / `app.api` exist but there's no `app.cli`; routers have no surface-native at all.
3. The `App` can't author a typed verb directly — only routers fill `_descriptors`.
4. `visibility` is honored by MCP + CLI but **ignored by HTTP** (a live leak: CLI-only and `hidden` verbs are reachable as `POST /api/<name>`).
5. Two axes for "where does it show" — `expose` (network subset) and `visibility` (all/cli/hidden) — that overlap at the edges (`expose=()` ≈ `visibility="cli"`).
6. The two composition roots (`App`, `Router`) have different authoring menus.

---

## 2. Surfaces — one protocol, three (then N) implementations

Every transport satisfies one protocol. The CLI joins as the third.

```
Surface
├─ name: "mcp" | "api" | "cli" | <future: a2a, grpc, graphql>
├─ kind: NETWORK | LOCAL                 ← CLI is LOCAL; the rest NETWORK
├─ reserved_types, substrate_dep_markers ← (unchanged from today)
├─ bind(runtime, descriptors) → native app   (FastMCP / FastAPI / Typer)
├─ install_di_bridge(runtime, app)
└─ render_name(slug, leaf) → str         ← surface owns its name rendering
```

The CLI's typer≥0.26 vendored-click compatibility shim lives inside
`CliSurface.bind` — quarantined, not smeared across the builder.

---

## 3. One axis — `surfaces` (the projection matrix)

A verb declares where it appears. Each surface entry is one of three
states. **This single matrix replaces `expose`, `visibility`, and the
once-proposed `@cli()`.**

```
        projection(verb, surface) ∈ { ABSENT, LISTED, UNLISTED }

   ABSENT    not mounted at all          (was: surface ∉ expose)
   LISTED    mounted + advertised        (was: visibility="all")
   UNLISTED  mounted + callable, hidden  (was: visibility="hidden")
```

The whole old vocabulary falls out of it:

```
                          mcp        api        cli
  default             →   LISTED     LISTED     LISTED      everywhere
  surfaces=("mcp",)   →   LISTED     ABSENT     LISTED      (was expose=("mcp",))
  surfaces=("cli",)   →   ABSENT     ABSENT     LISTED      operator command (was visibility="cli" / @cli())
  UNLISTED on cli     →   …          …          UNLISTED    present, unadvertised (was visibility="hidden")
  @app.mcp.tool()     →   LISTED     –          –           surface-native, single-surface
```

An operator command is just a normal verb that lives only on the CLI —
the **verb** still carries semantics (`read`/`write` → readOnlyHint /
destructiveHint), `surfaces` carries **placement**:

```python
class Admin(a2kit.Router):
    slug = "admin"
    @a2kit.write(surfaces=("cli",))      # CLI-only, audited, DI'd, policy-gated
    def trust_vault(self, ...): ...
```

Every native surface supports all three states (MCP hidden-meta, Typer
`--help` hide, FastAPI `include_in_schema=False`), so UNLISTED is faithful,
not faked.

---

## 4. The homomorphism — mirror the native trees

The `App → Router → verb` tree maps **level-for-level** onto each
transport's native composition tree. `App`/`Router` are typed,
surface-agnostic; each `Surface` materializes the same tree natively.

```
   a2kit (what you author)        FastMCP             FastAPI            Typer
   ───────────────────────        ───────             ───────            ─────
   App ───────────────────  ↔     root server         FastAPI app        root Typer
   │   • app-level verbs     ↔     root tools          app routes         top-level cmds
   │   • app.mcp/api/cli  ───↔──── native node, app level  ──── surface-native detour
   │
   └── Router(slug="entity") ↔    mount(namespace=…)  include_router      add_typer
       │   • router verbs    ↔     entity_*            /api/entity/…       app entity …(*)
       └── router.mcp/api/cli ↔─── native node, router level ── surface-native detour

   PARITY AXIS:  our-App ↔ native-app    our-Router ↔ native-router
                 (NOT our-App ↔ our-Router)
   (*) CLI default layout is FLAT (§5); nested shown for the tree mapping.
```

Feasibility verified (2026-06-06): `fastapi.include_router(prefix=…)`,
`fastmcp.FastMCP.mount(namespace=…)` (`entity` + `update` → `entity_update`),
`typer.Typer.add_typer`.

**The detour.** `app.mcp` / `router.api` / `app.cli` / … return the native
node *at that level*. Use it for a single-surface feature that needs raw
native power (FastAPI `Request`/`Response`, a FastMCP resource, a click
wizard) — until you promote it to a projected verb. Surface-native is for
genuinely surface-specific features only.

---

## 5. Naming — flat canonical, structured underneath

### Identity vs rendering

A tool's identity is two parts, **neither invented**:

```
   leaf  =  the function name        (def update → "update"; override: name="…")
   path  =  position in the tree     ([] at app level, [slug] under a router)
```

The **canonical name is flat** — `slug + "_" + leaf` (bare `leaf` for
app-level verbs) — rendered **identically on every surface** and used
verbatim in the call-log/audit:

```
   author                          MCP            CLI (flat, default)    HTTP
   ─────────────────────────       ───────────    ───────────────────    ──────────────────
   @app.read def health      →     health         app health             /api/health
   Entity(slug="entity")
     @read def update        →     entity_update  app entity_update      /api/entity_update
     @read def search        →     entity_search  app entity_search      /api/entity_search
   Ontology(slug="ontology")
     @read def update        →     ontology_update app ontology_update    /api/ontology_update
```

Rules:

- **leaf = function name**, overridable via `name="…"`.
- **router verbs**: `slug_leaf`. **app-level verbs**: bare `leaf`.
- the **app name is identity, never a prefix** (it's the FastMCP server
  name / the CLI binary `a2kay`). No `a2kay_update`.
- MCP is the only *flat* namespace; CLI/HTTP are naturally hierarchical
  but render the same flat string by default — which is *why* collisions
  only ever hit MCP.

### Grouping without an extra trip

Flat names still group in discovery UIs via presentation metadata, so you
don't pay a drill-in step:

- CLI: `typer ... rich_help_panel=<slug>` clusters flat commands in `--help`.
- HTTP: `add_api_route(tags=[<slug>])` clusters flat paths in OpenAPI/Swagger.

### The door stays open

Identity is kept **structured** on the descriptor (`router_slug` + `leaf`)
and only flattened at `render_name` time. So a future nested CLI is a
config flag, not a rewrite:

```
   CliConfig.layout = "flat"   (default)  →  app entity_update
                    = "nested" (opt-in)   →  app entity update   (sub-Typers)
```

Same descriptors, same canonical id for logs/audit, zero re-authoring.

---

## 6. Composition-root parity

```
                     App (root)                 Router (root)
   projected verbs   @app.read/.write/.list     @a2kit.read/.write/.list
                     (top-level, bare names)    (slug-scoped, slug_leaf)
   surface-native    app.mcp / app.api / app.cli   router.mcp / router.api / router.cli
   compose           add_router, provide,       (deps, enrichers)
                     enricher, auth, health…
```

`App` ≈ "the root router" (no slug → bare top-level commands). The parity
contract is **ours↔native at each level** (ADR 0028 decision 3): the `App`
faithfully wraps the native app, a `Router` faithfully wraps the native
router. They don't need identical menus.

---

## 7. Delivery — how this splits into OpenSpec changes

Sequenced so each lands green and independently shippable. Names are
proposals.

```
WAVE 0  (unblock + correctness — can ship ahead, small)
  ├─ fix-cli-typer-vendored-click     #1   CliSurface compat shim (or pre-Surface fix).
  │                                        Ship + patch release; unblocks a2kay's dead CLI.
  └─ fix-http-visibility-leak         #4   http/build.py honors the surfaces matrix.
                                           Security-flavored; CLI-only/hidden verbs stop
                                           leaking onto /api. Standalone, non-breaking.

WAVE 1  (the spine)
  └─ cli-as-surface                        CLI becomes a Surface; CliSurface.bind owns the
                                           Typer build + compat shim; app.cli accessor.
                                           Folds in #1 properly if Wave 0 was a stopgap.

WAVE 2  (the model — BREAKING, ships together with a migration table)
  ├─ surfaces-projection-axis         #2   Introduce the {absent,listed,unlisted} matrix;
  │                                        map expose/visibility onto it; retire @cli idea.
  ├─ native-tree-homomorphism         #3   Router→native-router mount/include/add_typer;
  │                                        flat slug_leaf canonical names; rich_help_panel /
  │                                        tags grouping. THE breaking tool-name rename.
  └─ app-as-peer-root                      @app.read/.write/.list typed-verb front door;
                                           top-level bare-named commands.

WAVE 3  (affordances & gaps — additive)
  ├─ ctx-surface-identity             #5   each Surface stamps surface= (+ client id) on
  │                                        the call scope; extends the ADR-0027 _CallScope.
  ├─ mcp-server-instructions          #6   McpConfig.instructions threaded by McpSurface.bind.
  └─ validate-composition             (#4-list) standalone validate_composition(app) that
                                           resolves the matrix for every verb, callable in
                                           unit tests (no full build needed).

ORTHOGONAL (own track, big mechanical blast radius — do isolated)
  └─ ruff-compatible-lint-codes       #7   rename A2K### / dashed codes to ruff-noqa-safe
                                           shapes + inline-suppress support. Touches every
                                           existing # noqa and the lint snapshots.
```

Dependencies: Wave 1 (`cli-as-surface`) precedes Wave 2 (the homomorphism
needs all three surfaces uniform). Within Wave 2, `surfaces-projection-axis`
and `native-tree-homomorphism` co-ship (the rename + the new axis are one
breaking surface). Wave 0 and the orthogonal lint track are independent and
can land any time.

### The one decision still open before Wave 2

**Embrace vs soften the MCP-name break.** Wave 2 renames every
router-scoped tool (`update` → `entity_update`) on every surface — breaking
for a2atlassian / a2db / a2web. Embrace = clean uniform rule + migration
table. Soften = flat-unless-collision (keeps names, reintroduces a special
case). ADR 0028 leans embrace; the call is Denis's before the breaking
change lands.

---

## 8. Cross-references

- [ADR 0028](adr/0028-unified-surface-architecture.md) — the decision record.
- ADRs [0001](adr/0001-typer-cli.md), [0002](adr/0002-author-annotation-surface.md),
  [0003](adr/0003-semantic-flag-vocabulary.md), [0004](adr/0004-package-layout-tiered-by-audience.md),
  [0010](adr/0010-auth-mcp-mode-only.md), 0020 — the surface decisions this model sits above.
- [Consumer feedback doctrine](CONSUMER_FEEDBACK_DOCTRINE.md) (ADR 0005) — the a2kay frictions.
- [ADR 0027](adr/0027-refound-ldd-on-stdlib-logging.md) — the `_CallScope` that `ctx-surface-identity` extends.
