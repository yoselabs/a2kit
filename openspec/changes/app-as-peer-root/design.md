# Design — app-as-peer-root (Wave 2, BREAKING)

This change makes `App` a class authored the same way as a Router, so the
two composition roots share one shape (ADR 0028 decision 7, "App is a
class too"; `docs/SURFACE_ARCHITECTURE.md` §6). It is the app-root half of
the Wave 2 breaking authoring surface.

## The roots, side by side

Parity is **ours↔native at each level** (ADR 0028 decision 3): the `App`
faithfully wraps the native app (FastAPI app / FastMCP root server / root
Typer), a `Router` faithfully wraps the native router. They do not need
identical menus — but after this change they share one authoring shape.

```
                     App (class)                Router (class)
   projected verbs   @a2kit.read/.write/.list   @a2kit.read/.write/.list   (auto-collected)
                     (top-level, bare names)    (slug-scoped, slug_leaf)
   config            class attrs                class attrs
                     (name, providers,          (slug, visibility,
                      per-surface config objs)   providers)
   enrichers         @a2kit.enricher            @a2kit.enricher
   surface-native    configure_api/_mcp/_cli    configure_api/_mcp/_cli    (hooks, api-first)
   compose           routers = (...), serve()   —
```

`App` ≈ "the root router" — no slug, so its verbs render as bare top-level
commands. Two App-specific points carry the weight of this change:

1. **`routers = (...)` is reference-composition, not the `tools=`
   anti-pattern.** Routers are defined elsewhere and must be *named*
   somewhere; the tuple names them. That is legitimate (auto-discovery
   would be the import-scan magic the project rejects). It replaces
   `add_router`. Contrast: `router-class-auto-collect` *removes* the
   co-located `tools=` tuple precisely because the methods are already
   local to the class — there is nothing external to name. Routers are
   external to the App, so the App must name them.

2. **The surface-native detour cannot be a class-body live accessor.**
   See below.

Authored shape:

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

## The detour — two forms, and why form (a) is impossible

Under the class authoring model the class body runs with **no instance**.
So a live mutable accessor in the class body cannot exist. ADR 0028
decision 3 / §4 resolve the detour into exactly three positions, of which
two are real:

```
  (a) class body     @app.api.get("/raw")        ✗ impossible — no instance yet
  (b) bootstrap      app = Kay(); app.api.get()  ✓ escape — instance exists at the root
  (c) in-class hook  def configure_api(self,api) ✓ primary — built with the native object
```

| form | where | status | why |
|---|---|---|---|
| (a) class-body live accessor (`@app.api.get`) | inside the `class` body | **impossible by construction** | the class body has no `app` instance to mutate; this is a hard fact of Python, not a policy choice |
| (b) bootstrap live accessor (`app = Kay(); app.api.get(…)`) | the composition root, after instantiation | **kept — deliberate escape** | the instance exists at the root; the only place the old live-accessor form survives. For genuine raw-native needs that want **bootstrap-local runtime context** |
| (c) in-class configurer hook (`def configure_api(self, api): …`) | a method on the App class | **primary** | called at build with the native object; decorator ergonomics survive on the local `api` param (`@api.get("/x")`). Static, in one place, AI-legible — the Nest `configure` / Spring `WebMvcConfigurer` pattern |

**Primary is (c).** `def configure_api(self, api): …` (and `configure_mcp`
/ `configure_cli` on demand, shipped `api`-first) is the sanctioned in-
class way to add a single-surface raw feature (a FastAPI websocket /
custom `Response`, a FastMCP resource, a click wizard) until the author
promotes it to a projected verb. It is more static and more AI-legible
than a mutable accessor, with the same raw native power. Routers get the
symmetric `configure_<surface>` hooks.

## Why (b) is kept rather than removed

The configurer hook (c) covers the in-class capability completely, so one
could argue for removing the live accessor outright. The user's explicit
decision is to **keep (b) as a deliberate escape**, not remove it:

- (c) runs at build with the native object but inside the App's own
  configuration flow. (b) runs at the **composition root**, where the
  author has **bootstrap-local runtime context** — the assembled
  instance, any locally-constructed dependencies, environment decided at
  `main()` time — that a class-body method does not naturally see.
- Removing (b) would force every genuinely raw-native, bootstrap-context
  need through a less natural in-class path, trading a real escape for
  purity. The decision keeps the escape and marks it as deliberate: (b)
  is **not** the default (the hook is), and (b) is the *only* surviving
  live-accessor form (form (a) is gone by construction, not by policy).

So the rule is: prefer (c) in-class; reach for (b) only when bootstrap-
local context is genuinely required; (a) never happens.

## App-level verbs render bare (no slug prefix)

The app name is **identity, never a prefix** (it is the FastMCP server
name / the CLI binary name) — there is no `kay_health`. An app-level verb
has no slug, so the naming rule (ADR 0028 decision 5 / §5; the flat-name
rule defined in `native-tree-homomorphism`) resolves to the **bare
`leaf`**:

```
   author                     MCP        CLI (flat)      HTTP
   @app.read def health  →    health     app health      /api/health
```

This contrasts with a Router verb (`slug_leaf`, e.g. `entity_update`).
The auto-derive-from-`fn.__name__` rule is the same; only the prefix
differs (none at the app level, `slug_` under a Router).

## Co-ship + Wave-1 dependency

`docs/SURFACE_ARCHITECTURE.md` §7: within Wave 2,
`surfaces-projection-axis`, `native-tree-homomorphism`,
`router-class-auto-collect`, and **this change** co-ship — the rename, the
new axis, the Router authoring shape, and the App authoring shape are one
breaking surface and land together under a single migration table. This
change reuses the `__init_subclass__` auto-collect mechanic that
`router-class-auto-collect` defines (the App is collected the same way a
Router is) and the bare/`slug_leaf` naming rule that
`native-tree-homomorphism` defines.

Wave 2 (and so this change) **depends on** Wave 1 (`cli-as-surface`),
which makes MCP, HTTP, and CLI share one `bind(...)` model and adds the
`app.cli` accessor. Without that, the symmetric `configure_cli` hook and
the bare-named CLI commands would have to special-case the CLI a second
time. With Wave 1 in place, the App authors all three surfaces uniformly.

## Non-goals (boundary with the co-shipping siblings)

- No `surfaces=` projection matrix — `surfaces-projection-axis` owns it.
- No `slug_leaf` rename machinery / `canonical_name_override` —
  `native-tree-homomorphism` owns it; this change only states app-level
  verbs are bare by that same rule.
- No redefinition of the auto-collect mechanic — `router-class-auto-collect`
  owns it; this change reuses it for the App.
- No `CliConfig.layout = "nested"` — flat default; bare names stay flat.
