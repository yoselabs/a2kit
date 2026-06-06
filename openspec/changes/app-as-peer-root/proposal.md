## Why

`App` is the one composition root that **cannot be authored like a
Router**. Routers are classes (config as class attrs, tools as
`@a2kit`-marked methods); `App` is an *instance* you build imperatively —
`App("svc").add_router(...).add_cli(...)` — and it cannot carry a typed
verb at all (only routers fill `_descriptors`). Three concrete frictions
fall out of that asymmetry:

- **No symmetry.** Two composition roots, two authoring menus. A reader
  who has internalized the Router shape (class + decorated methods) must
  learn a second, imperative shape for the App. ADR 0028 decision 7
  ("App is a class too") closes this: both roots share one shape.
- **`add_router(...)` boilerplate.** Composing routers is an imperative
  call chain (`.add_router(Entity()).add_router(Ontology())`) when it is
  really just a *list of router classes*. Reference-composition
  (`routers = (Entity, Ontology)` ClassVar) states the same fact
  declaratively, statically, and AI-legibly — and replaces `add_router`.
- **The class-body decorator impossibility.** Routers get a surface-
  native escape; the App's escape today is the live `app.api.get(...)`
  accessor, which **cannot exist in a class body** — there is no instance
  when the class body runs (`@app.api.get` is impossible by
  construction). Making `App` a class forces a resolution for the raw-
  native escape that does not depend on a live instance.

`App` also gains a typed-verb front door it never had: app-level
`@app.read/.write/.list` methods, auto-collected the same way Router
methods are, that project as **top-level BARE-named commands** (no slug
prefix — the app name is identity, not a prefix; ADR 0028 decision 5 /
§5 naming).

This is the app-root half of the Wave 2 breaking authoring surface and
**co-ships** with `surfaces-projection-axis`, `native-tree-homomorphism`,
and `router-class-auto-collect` (the rename + the new axis + the
authoring shape are one breaking surface). It **depends on** Wave 1
(`cli-as-surface`), which makes all three surfaces share one `bind(...)`
model.

## What Changes

`App` becomes a **class** authored the same way as a Router:

- **Config as class attributes** — `name`, `providers`, and per-surface
  config objects (`mcp = McpConfig(...)`, `cli = CliConfig(...)`),
  mirroring a Router's `slug` / `visibility` / `providers`.
- **App-level typed verbs as auto-collected methods.** `@a2kit.read`,
  `@a2kit.write`, `@a2kit.list_` on App methods are collected at class-
  definition time (same `__init_subclass__` mechanics as the Router
  authoring change). An app-level verb has **no slug**, so its canonical
  name is the **bare `leaf`** (`def health` → `health`, rendered `health`
  on MCP, `app health` on the CLI, `/api/health` on HTTP) — a top-level
  command with no prefix.
- **`routers = (Entity, Ontology)` ClassVar replaces `add_router`.**
  Reference-composition: routers are defined elsewhere and must be
  *named* somewhere; the tuple names them. This is NOT the co-located
  `tools=` duplication that `router-class-auto-collect` removes — it is
  legitimate reference-composition (auto-discovery would be the import-
  scan magic the project rejects).
- **Enrichers as `@a2kit.enricher` methods**, same as the Router.
- **The surface-native detour, resolved by the two-forms rule
  (ADR 0028 decision 3 / §4).** Form (a) — a class-body live accessor
  (`@app.api.get`) — stays **impossible by construction**. The PRIMARY
  in-class escape is the **configurer hook**:
  `def configure_api(self, api): ...` (and `configure_mcp` /
  `configure_cli`, shipped `api`-first), called at build with the native
  object so decorator ergonomics survive on the local `api` param
  (`@api.get("/x")`). The ESCAPE for genuine raw-native needs that want
  bootstrap-local runtime context is form (b), the live instance
  accessor at the composition root: `app = Kay(); app.api.get(...)`. The
  hook covers the same capability in-class, so (b) is a deliberate
  escape, not the default — and (b) is the *only* place the live-accessor
  form survives.
- Run by instantiating at the entry point: `Kay().serve()`.

## Capabilities

### Modified Capabilities

- `core-composition` — `App` is a class (config + verbs + enrichers as
  class members, auto-collected); `routers = (...)` ClassVar replaces
  `add_router`; the surface-native detour is the in-class
  `configure_<surface>` hook with the live `app.<surface>` accessor
  surviving only as a bootstrap (form "b") escape; the class-body live
  accessor stays impossible.
- `verb-decorators` — app-level `@app.read/.write/.list` verbs are
  auto-collected and produce **bare-named** (no-slug) top-level commands;
  the same auto-derived-from-`fn.__name__` rule applies, with bare `leaf`
  at the app level vs `slug_leaf` under a Router.

## Impact

- **BREAKING.** The imperative App authoring surface is replaced by the
  class shape. Specifically:
  - `App("svc").add_router(R())` → a class with `routers = (R,)`. The
    `add_router(...)` verb is **removed** (reference-composition supplants
    it). Migration: collect router classes into the `routers` tuple.
  - A class-body `@app.api.get(...)` usage (never possible as a literal
    class-body decorator, but expressed imperatively today against an App
    instance) migrates to the `configure_api(self, api)` hook for the
    in-class case, or to the bootstrap (b) escape
    (`app = Kay(); app.api.get(...)`) when bootstrap-local runtime context
    is genuinely needed.
  - App-level behaviour that previously had to live on a synthetic router
    can move to app-level `@app.read/.write/.list` methods (bare names).
- Co-ships with the other Wave 2 changes under one migration table; the
  rename, the projection axis, the Router authoring shape, and this App
  authoring shape land together.
- Affected consumers: a2kay, a2atlassian, a2db, a2web (each has an App
  composition root and `add_router` call chains).

## Non-goals

- **Not** the projection axis (`surfaces=`) — that is
  `surfaces-projection-axis`. This change keeps placement vocabulary as
  the co-shipping siblings define it.
- **Not** the flat `slug_leaf` rename / `canonical_name_override`
  mechanics — that is `native-tree-homomorphism`. This change only states
  that app-level verbs are bare (no-slug) by the same rule.
- **Not** the Router auto-collect machinery itself — that is
  `router-class-auto-collect`. This change reuses that mechanic for the
  App and does not redefine it.
- **Not** removing the live `app.api` / `app.mcp` / `app.cli` accessors:
  form (b) is **kept on purpose** as the bootstrap escape (per the
  explicit decision); only the *class-body* form (a) stays impossible.
- **Not** a nested-CLI layout (`CliConfig.layout`) — out of scope; the
  bare-name rule is the flat default.
