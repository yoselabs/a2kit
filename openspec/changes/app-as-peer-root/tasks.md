# Tasks — app-as-peer-root

BDD-first / TDD red → green. Each behavioural change gets a failing test
that proves the new authoring shape (or the impossibility of form (a))
before the implementation lands. Co-ships with the other Wave 2 changes;
depends on Wave 1 (`cli-as-surface`).

## 1. App is a class — config + verbs + enrichers (RED)

- [ ] 1.1 Write a test: define `class Kay(a2kit.App): name = "kay"` with an
      `@a2kit.read def health(self) -> Health: ...` method, instantiate
      `Kay()`, assert the app-level verb is collected into the App's
      descriptors (one descriptor, `verb == "read"`). Confirm RED — today
      the App is an instance with no class-collected verbs.
- [ ] 1.2 Write a test: an App class with `providers = (ConnStore, (Database,
      make_db))` and per-surface config attrs (`mcp = McpConfig(...)`,
      `cli = CliConfig(...)`) exposes those providers / configs after
      `Kay()` construction (same shape as a Router's class attrs). RED.
- [ ] 1.3 Write a test: `@a2kit.enricher def on_timeout(self, exc:
      TimeoutError)` on the App class is collected as an app-level enricher
      (runs AFTER router-level enrichers). RED.

## 2. App-level verbs render BARE (no slug prefix) (RED)

- [ ] 2.1 Write a test: `@app.read def health` resolves to canonical name
      `"health"` (bare leaf, no app-name prefix — no `kay_health`),
      rendered `health` on MCP, `app health` on CLI, `/api/health` on
      HTTP. Contrast a Router verb under `slug="entity"` resolving to
      `entity_update`. RED.
- [ ] 2.2 Write a test: the auto-derive-from-`fn.__name__` rule is the same
      for App and Router; only the prefix differs (none vs `slug_`). RED.

## 3. `routers = (...)` ClassVar replaces `add_router` (RED)

- [ ] 3.1 Write a test: `class Kay(a2kit.App): routers = (Entity, Ontology)`
      composes both routers (their tools appear in the App descriptors)
      with NO `add_router(...)` call. RED.
- [ ] 3.2 Write a test: `add_router` is removed — `App.add_router` raises
      `AttributeError` (or is absent), with a migration hint pointing at
      `routers = (...)`. RED.
- [ ] 3.3 Write a test: a duplicate router slug across the `routers` tuple
      fails loud at composition (parity with today's add_router dup-slug
      guard). RED.

## 4. The detour two-forms (RED)

- [ ] 4.1 Write a test: `def configure_api(self, api): ...` on the App class
      is called at build with the native object, and a `@api.get("/x")`
      route registered inside it is present on the built FastAPI app
      (primary form (c)). Add the symmetric `configure_mcp` / `configure_cli`
      coverage. RED.
- [ ] 4.2 Write a test: the bootstrap escape (form (b)) still works —
      `app = Kay(); app.api.get("/raw")(handler)` registers the route
      (the live accessor survives only at the composition root). This
      asserts (b) is **kept**, not removed.
- [ ] 4.3 Document/guard form (a): a class-body `@app.api.get(...)` is
      impossible by construction (no instance in the class body). A test
      that attempts to reference `app` in the class body raises
      `NameError` — encoding the impossibility, not a framework check.

## 5. Implement (GREEN)

- [ ] 5.1 Make `App` collect class-body `@a2kit`-marked verbs + enrichers via
      `__init_subclass__` (reuse the `router-class-auto-collect` mechanic).
      App-level verbs carry no slug → bare-leaf canonical name.
- [ ] 5.2 Read `name` / `providers` / per-surface config from class attrs;
      install `providers` the way Router providers are installed.
- [ ] 5.3 Add `routers` ClassVar handling (reference-composition); compose
      the listed router classes; keep the dup-slug guard. Remove
      `add_router` (and the obsolete imperative verbs that this replaces),
      raising a migration-hint `AttributeError` for `add_router`.
- [ ] 5.4 Add the `configure_api` / `configure_mcp` / `configure_cli` hooks
      (api-first), invoked at build with the native object. Keep the live
      `app.api` / `app.mcp` / `app.cli` accessors for the bootstrap (b)
      escape; do NOT add any class-body live-accessor form.
- [ ] 5.5 `Kay().serve()` entry-point path (instantiate then run).

## 6. Verify (GREEN)

- [ ] 6.1 All §1–§4 tests pass.
- [ ] 6.2 Symmetry check: an App and a Router authored side by side share
      the same authoring members (verbs, enrichers, configure_* hooks,
      class-attr config) per the roots-side-by-side table.
- [ ] 6.3 Full suite green, output pristine; coverage holds.
- [ ] 6.4 Co-ship check: the migration table for Wave 2 includes the
      `add_router → routers=` and `app.api.get class-body → configure_api
      / (b) escape` rows.

## 7. Close out

- [ ] 7.1 lint / `ty check src/` / a2kit-static / ruff gates green on all
      touched files.
- [ ] 7.2 Confirm Wave-1 dependency satisfied (`cli-as-surface` landed: the
      `app.cli` accessor + uniform `bind` exist) before merge.

## Implementation sequence (resolved — ready to execute)

Design fully resolved (see design.md "Implementation findings"; the two
Constitution-touching forks human-confirmed 2026-06-08). Build
transition-tolerant → migrate → flip so each step is a green checkpoint
(the big-bang end-state is reached via green steps, not a single red leap).

**Step A — transition-tolerant core (additive, keeps instance form working):**
1. `_verbs.py`: add an `enricher` class-body marker (sets a marker attr;
   lazy `_resolve_enricher_filter` validation); export `a2kit.enricher`.
2. `app.py`:
   - `App.__init_subclass__`: collect `@a2kit`-marked verb methods (reuse
     `_collect_marked_tool_names`) into `_a2kit_app_tool_names` + collect
     `enricher`-marked methods.
   - Add a module-private `_AppRootRouter` (slug=None, holds the app-verb
     bound methods, does NOT stamp `router_slug` → bare-leaf names via
     `resolve_canonical_name`).
   - `App.__init__(self, name=None, ...)`: if `name is None`, read
     `type(self).name` (new ClassVar, base default None; error if both
     None). After existing setup, when authored as a subclass: instantiate
     each class in the `routers` ClassVar + register (internal
     `_register_router`, the renamed body of today's `add_router`); install
     `providers` ClassVar; build app-verb descriptors via `_AppRootRouter`;
     collect class-body enrichers.
   - Rename the `routers()` method → `router_instances()`; `routers`
     becomes the ClassVar (default `()`). Update the 4 src callers
     (`runtime.py:269,320`, `mcp/server.py:60`, `cli/builder.py:558`).
   - Add `App.serve(self, argv=None)` → `a2kit.run(self, argv)`.
   - Keep `add_router` (delegates to `_register_router`) during transition.
3. TasksRouter (examples/tracker): refactor store from constructor arg to a
   DI provider; `packages/testing/fixtures.py` overrides the fake via
   `app.provide(Store, fake)`.
4. Surface builders: app-verb (slug=None) rendering — MCP root server (bare
   name), HTTP root `/api/<leaf>`, CLI top-level command (no panel). Add the
   `configure_api/_mcp/_cli` hook calls at build.
5. New `tests/test_app_as_peer_root.py` covering §1–§4 with the resolved
   decisions (config via `config=`; `routers=` classes-only). Green.
6. `a2kit.testing.app_of(name, *router_classes, **kw)` helper (test-namespace
   only) returning an instantiated anonymous App subclass.

**Step B — migrate (~300 sites, parallel subagents per directory):**
`a2kit.App("n").add_router(R())` → `app_of("n", R)` for fixtures/throwaway
apps; authoring-focused tests use the real `class _App(a2kit.App)` form.
Migrate the 14 `.routers()` test callers → `.router_instances()`.

**Step C — flip breaking (one commit):** remove the positional `App(name)`
instance constructor + public `add_router` (raise `AttributeError` with a
`routers = (...)` migration hint). Full suite green; gates green; land.
