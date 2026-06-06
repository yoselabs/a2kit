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

The whole old vocabulary falls out of it. **Spelling:** a tuple is the
shorthand for the common case (LISTED on the named surfaces, ABSENT
elsewhere); a dict is the escape for the rare present-but-hidden
(UNLISTED) case — one knob, no second axis:

```
                                   mcp        api        cli
  default                      →   LISTED     LISTED     LISTED   everywhere
  surfaces=("mcp",)            →   LISTED     ABSENT     ABSENT   (was expose=("mcp",))
  surfaces=("mcp","cli")       →   LISTED     ABSENT     LISTED
  surfaces=("cli",)            →   ABSENT     ABSENT     LISTED   operator command (was visibility="cli")
  surfaces={"cli":"unlisted"}  →   ABSENT     ABSENT     UNLISTED present, unadvertised (was visibility="hidden")
  configure_mcp(self, server)  →   (raw)      –          –        surface-native hook, single-surface
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

**The detour — two forms (never a class-body accessor).** Under the class
authoring model (§6) the native escape lives in two places, because the
class body has no instance to mutate:

```
  (a) class body     @app.api.get("/raw")        ✗ impossible — no instance yet
  (b) bootstrap      app = Kay(); app.api.get()  ✓ escape — instance exists at the root
  (c) in-class hook  def configure_api(self,api) ✓ primary — built with the native object
```

- **Primary (c): the configurer hook.** `def configure_api(self, api): …`
  (and `configure_mcp` / `configure_cli` on demand, `api`-first) is called
  at build with the native node. Decorator ergonomics survive on the local
  param (`@api.get("/x")`). Use it for a single-surface raw feature (a
  FastAPI websocket / custom `Response`, a FastMCP resource, a click
  wizard) until you promote it to a projected verb. The Nest `configure` /
  Spring `WebMvcConfigurer` pattern — static, in one place, AI-legible.
- **Escape (b): the live instance accessor.** At the composition root the
  instance exists, so `app = Kay(); app.api.get(…)` still works when you
  genuinely need raw native with bootstrap-local runtime context. The hook
  covers the same capability in-class, so (b) is a deliberate escape, not
  the default — and it is the *only* place the old live-accessor form
  survives.

Surface-native is for genuinely surface-specific features only.

---

## 5. Naming — flat canonical, structured underneath

### Identity vs rendering

A tool's identity is two parts, **neither invented**:

```
   leaf  =  the function name        (def update → "update")
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

- **leaf = function name.**
- **router verbs**: `slug_leaf`. **app-level verbs**: bare `leaf`.
- the **app name is identity, never a prefix** (it's the FastMCP server
  name / the CLI binary `a2kay`). No `a2kay_update`.
- MCP is the only *flat* namespace; CLI/HTTP are naturally hierarchical
  but render the same flat string by default — which is *why* collisions
  only ever hit MCP.

### The override — `canonical_name_override`

One escape hatch pins the exact name. Resolution precedence:

```
   canonical_name(verb) =
      explicit canonical_name_override="…"  →  used VERBATIM, no slug prefix
      else, under a Router                  →  f"{slug}_{leaf}"
      else, app-level verb                  →  leaf
```

A pinned name is *complete* — the slug is never re-applied
(`canonical_name_override="jira_search"` under `slug="jira"` stays
`jira_search`, not `jira_jira_search`). This is also exactly what naming
does today (no prefix exists yet, so an explicit name already IS the full
name) — which is why **embracing the rename costs almost nothing**: the
consumer migration is a mechanical `s/name=/canonical_name_override=/`
with tool-name *values* unchanged; only the genuinely-unnamed router
verbs (the collision-prone auto-derived ones) actually rename.

Mixed pinning is the norm — one verb pins, the rest auto-derive and must
still satisfy uniqueness. A pin must be `[A-Za-z0-9_]` (legal on every
surface) and is **surface-flat by definition** (under a future nested CLI
layout, only auto-derived names nest; pins stay flat).

### Uniqueness — two layers over one resolver

The canonical name is also the call-log/audit key, so it MUST be unique
**globally** (not per-surface: a CLI-only `foo` and an MCP-only `foo`
still make the audit log ambiguous). Enforced over one
`resolve_canonical_name` function:

```
  LINT  (primary — complain often)        RUNTIME  (backstop — complain early)
  static rule; resolves literal slugs +   at build()/finalize, before serve;
  canonical_name_overrides; flags dup      resolves every verb, asserts global
  names before you run; ruff-compatible    uniqueness, fails loud w/ the pair;
  code (#7)                                also a standalone validate_composition(app)
                                           for tests; catches dynamic names lint can't
```

Auto-collect (§6) already removes the *registration* error class by
construction; this guards the *collision* class, which no structure can
fully prevent.

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

## 6. Composition-root parity & authoring shape

### Routers are classes; tools are auto-collected (ADR 0028 decision 7)

A router is a **class**: config is class attributes, tools and enrichers
are `@a2kit`-marked methods **collected at class-definition time**. There
is **no `tools=` tuple** — the marker *is* the registration:

```python
class Entity(a2kit.Router):
    slug = "entity"
    visibility = "all"

    @a2kit.read
    def update(self, *, id: str) -> Memory: ...      # → entity_update

    @a2kit.read(canonical_name_override="entity_find")
    def search(self, *, q: str) -> list[Memory]: ...  # → entity_find (pinned)

    @a2kit.enricher
    def on_missing(self, exc: KeyError) -> NotFound | None: ...
```

Why this shape (not FastAPI's instance + `@router.read`): a2kit's design
centre is a **static, inspectable, AI-legible** surface — the whole router
reads top-down, one local declaration per tool, lowest code volume, and
the *registration* error class is impossible by construction. That is the
enterprise-framework norm (Spring / Nest / Rails / .NET). FastAPI's
instance advantages (app-factories, versioned multi-mounts, metaclass
avoidance) are needs a2kit does not have — each router mounts **once**
under its slug. Collection is decorator-marker driven (`__init_subclass__`),
the *least*-magical option — distinct from the `dir()`-walk / naming-
convention magic ADR 0002 rejected. The tier-snapshot surface still
derives statically (decorators are AST-visible).

### App is a class too (symmetry — resolved)

Both roots share one shape. `App` is a class with the same authoring
mechanics as `Router`:

```python
class Kay(a2kit.App):
    name = "kay"
    providers = (ConnStore, (Database, make_db))
    mcp = McpConfig(instructions="…")
    cli = CliConfig(layout="flat")
    routers = (Entity, Ontology)              # reference-composition (was add_router)

    @a2kit.read
    def health(self) -> Health: ...           # app-level verb → bare "health"

    @a2kit.enricher
    def on_timeout(self, exc: TimeoutError) -> Unavailable | None: ...

    def configure_api(self, api): ...         # raw-native escape (configurer hook)

Kay().serve()                                 # instantiate at the entry point
```

Two App-specific points:

- **`routers = (...)` is reference-composition, not the `tools=`
  anti-pattern.** Routers are defined elsewhere and must be *named*
  somewhere; that's legitimate (auto-discovery would be the import-scan
  magic we reject). It replaces `add_router`.
- **The detour is the in-class configurer hook** (see §4), with the live
  instance accessor (`app = Kay(); app.api.get(…)`, form "b") surviving
  only as a bootstrap escape for genuine raw-native needs — the one
  non-trivial consequence of making `App` a class.

### The roots, side by side

```
                     App (class)                Router (class)
   projected verbs   @a2kit.read/.write/.list   @a2kit.read/.write/.list   (auto-collected)
                     (top-level, bare names)    (slug-scoped, slug_leaf)
   config            class attrs                class attrs
                     (name, providers, surface  (slug, visibility,
                      config objects)            providers)
   enrichers         @a2kit.enricher            @a2kit.enricher
   surface-native    configure_api/_mcp/_cli    configure_api/_mcp/_cli    (hooks, api-first)
   compose           routers = (...), serve()   —
```

`App` ≈ "the root router" (no slug → bare top-level commands). The parity
contract is **ours↔native at each level** (ADR 0028 decision 3): the `App`
faithfully wraps the native app, a `Router` faithfully wraps the native
router. They don't need identical menus — but they now share one authoring
shape.

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
  │                                        flat slug_leaf canonical names + canonical_name_override
  │                                        (verbatim); rich_help_panel / tags grouping.
  │                                        Breaking ONLY the auto-derived (unnamed) router verbs;
  │                                        explicitly-named tools are byte-for-byte unchanged.
  ├─ router-class-auto-collect             Drop `tools=` tuple; __init_subclass__ collects
  │                                  (decision 7) @a2kit-marked methods; enrichers unify onto
  │                                        the same pattern. Amends ADR 0002. Co-ships (it is
  │                                        the authoring half of the breaking surface).
  └─ app-as-peer-root                      @app.read/.write/.list typed-verb front door;
                                           top-level bare-named commands. (App-symmetry call —
                                           class vs instance root — resolved here.)

WAVE 3  (affordances & gaps — additive)
  ├─ ctx-surface-identity             #5   each Surface stamps surface= (+ client id) on
  │                                        the call scope; extends the ADR-0027 _CallScope.
  ├─ mcp-server-instructions          #6   McpConfig.instructions threaded by McpSurface.bind.
  └─ validate-composition             (#4-list + decision 6) standalone validate_composition(app):
                                           resolves the surfaces matrix AND canonical names for
                                           every verb, asserts global name uniqueness, callable
                                           in unit tests (no full build). Runtime backstop to the
                                           dup-name lint rule (which rides ruff-compatible-lint-codes).

ORTHOGONAL (own track, big mechanical blast radius — do isolated)
  └─ ruff-compatible-lint-codes       #7   rename A2K### / dashed codes to ruff-noqa-safe
                                           shapes + inline-suppress support. Touches every
                                           existing # noqa and the lint snapshots.
```

Dependencies: Wave 1 (`cli-as-surface`) precedes Wave 2 (the homomorphism
needs all three surfaces uniform). Within Wave 2, `surfaces-projection-axis`,
`native-tree-homomorphism`, and `router-class-auto-collect` co-ship (the
rename + the new axis + the authoring shape are one breaking surface). Wave 0
and the orthogonal lint track are independent and can land any time.

### Decisions resolved (2026-06-06)

- **Embrace the MCP-name break** — with the `canonical_name_override`
  escape hatch, the break hits *only* auto-derived (unnamed) router verbs;
  explicitly-named tools are unchanged. Soften (flat-unless-collision)
  rejected. See §5.
- **Override param name** = `canonical_name_override=` (maximally explicit
  about the no-prefix, verbatim behavior).
- **Router authoring** = class + auto-collect (no `tools=` tuple). See §6.
- **App symmetry** = `App` is a class too (same shape); `add_router` →
  `routers = (...)` ClassVar; the detour becomes a configurer hook. See §6.
- **UNLISTED spelling** = tuple shorthand (`surfaces=("mcp","cli")`) for
  the common case + dict escape (`surfaces={"cli": "unlisted"}`) for the
  rare present-but-hidden case. One knob.
- **Router native detours** = `api`-first (`configure_api`); `mcp` / `cli`
  added on demand.

All major design calls are settled; what remains is execution of the
Wave 0–3 change set above.

---

## 8. Cross-references

- [ADR 0028](adr/0028-unified-surface-architecture.md) — the decision record.
- ADRs [0001](adr/0001-typer-cli.md), [0002](adr/0002-author-annotation-surface.md),
  [0003](adr/0003-semantic-flag-vocabulary.md), [0004](adr/0004-package-layout-tiered-by-audience.md),
  [0010](adr/0010-auth-mcp-mode-only.md), 0020 — the surface decisions this model sits above
  (ADR 0002 additionally **amended**: `tools=` tuple → `__init_subclass__` auto-collect).
- [Consumer feedback doctrine](CONSUMER_FEEDBACK_DOCTRINE.md) (ADR 0005) — the a2kay frictions.
- [ADR 0027](adr/0027-refound-ldd-on-stdlib-logging.md) — the `_CallScope` that `ctx-surface-identity` extends.
