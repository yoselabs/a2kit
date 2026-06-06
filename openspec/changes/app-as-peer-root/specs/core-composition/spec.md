## MODIFIED Requirements

### Requirement: App composition uses three named verbs

`a2kit.App` SHALL be authored as a **class**, the same way a `Router` is
authored (ADR 0028 decision 7). Composition is declared as class members,
not assembled imperatively. Specifically:

- **Config as class attributes.** An `App` subclass SHALL declare `name`
  and MAY declare `providers` and per-surface config objects (`mcp =
  McpConfig(...)`, `cli = CliConfig(...)`, `api = HttpConfig(...)`),
  mirroring a Router's `slug` / `visibility` / `providers` class
  attributes.
- **Router composition via `routers` ClassVar.** An `App` subclass SHALL
  compose routers through a `routers = (Entity, Ontology)` ClassVar of
  Router classes. This is **reference-composition** — routers are defined
  elsewhere and must be *named* somewhere; the tuple names them. The
  `routers` ClassVar SHALL be the only router-composition mechanism. The
  imperative `add_router(router)` verb SHALL be **removed**; accessing
  `App.add_router` SHALL raise `AttributeError` with a migration hint
  pointing at `routers = (...)`. Two routers resolving to the same `slug`
  across the `routers` tuple SHALL fail loud at composition.
- **App-level typed verbs as auto-collected methods.** App methods
  decorated `@a2kit.read` / `@a2kit.write` / `@a2kit.list_` SHALL be
  collected at class-definition time (the same `__init_subclass__`
  mechanic used for Router methods). An app-level verb has **no slug**, so
  its canonical name SHALL be the bare `leaf` (`fn.__name__`), with no
  app-name prefix (see `verb-decorators`).
- **Enrichers as `@a2kit.enricher` methods.** App-level enrichers SHALL be
  declared as `@a2kit.enricher`-marked methods on the class and SHALL run
  AFTER router-level enrichers, matching today's app-enricher ordering.
- **The surface-native detour is resolved by the two-forms rule**
  (ADR 0028 decision 3). The class-body live accessor form `@app.api.get(...)`
  SHALL remain impossible by construction (no instance exists when the
  class body runs). The PRIMARY in-class escape SHALL be the configurer
  hook: `def configure_api(self, api): ...` (and `configure_mcp` /
  `configure_cli` on demand, shipped `api`-first), called at build with
  the native object so decorator ergonomics survive on the local `api`
  parameter (`@api.get("/x")`). The live instance accessors `app.api` /
  `app.mcp` / `app.cli` SHALL be KEPT as the bootstrap escape (form "b")
  for genuine raw-native needs that require bootstrap-local runtime
  context: `app = Kay(); app.api.get(...)`. Form (b) is a deliberate
  escape, not the default — and the only surviving live-accessor form.
- **Run by instantiating at the entry point.** An `App` subclass SHALL be
  run by instantiating it and handing the instance to a finisher
  (`Kay().serve()`).

`a2kit.App` SHALL remain a pure compose-phase builder with no sealed mode.
A finisher's internal `build(app)` step snapshots the App's composition
into an `AppRuntime`; the App carries no lifecycle of its own. The
compose container accumulates `provide(...)` registrations and remains
mutable for the App's lifetime — it is never sealed; each `build()`
snapshots it into a fresh runtime container, so one App MAY be handed to
more than one finisher.

`App.__init__` SHALL NOT accept a `debug` kwarg. Debug mode is a
consumer-owned concern (ADR 0022) and SHALL be set via env `A2KIT_DEBUG=true`
or via `A2kitConfig(debug=True)`. `App` SHALL NOT expose a `debug`
attribute; access to `app.debug` SHALL raise `AttributeError` with a
migration hint naming both replacement paths (`app.config.debug` for
consumers, `A2kitConfig` DI for subsystems).

#### Scenario: App is authored as a class with class-attr config

- **GIVEN** `class Kay(a2kit.App): name = "kay"; providers = (ConnStore,)`
- **WHEN** the author constructs `Kay()`
- **THEN** the App exposes `name == "kay"` and the declared providers,
  read from the class attributes (mirroring a Router's class attrs)

#### Scenario: routers ClassVar composes routers (replacing add_router)

- **GIVEN** `class Kay(a2kit.App): routers = (Entity, Ontology)` with no
  `add_router(...)` call anywhere
- **WHEN** the author constructs `Kay()`
- **THEN** the tools of both `Entity` and `Ontology` appear in the App's
  descriptors

#### Scenario: add_router is removed with a migration hint

- **WHEN** consumer code references `App.add_router` or calls
  `app.add_router(...)`
- **THEN** `AttributeError` is raised
- **AND** the message points the author at the `routers = (...)` ClassVar

#### Scenario: Duplicate router slug fails loud at composition

- **GIVEN** an `App` subclass whose `routers` tuple names two routers that
  resolve to the same `slug`
- **WHEN** the App is composed
- **THEN** composition fails loud naming the conflicting slug

#### Scenario: App-level verb is collected from the class body

- **GIVEN** `class Kay(a2kit.App): @a2kit.read def health(self) -> Health: ...`
- **WHEN** `Kay()` is constructed
- **THEN** exactly one app-level descriptor for `health` is collected with
  `verb == "read"`

#### Scenario: configure_api hook is the primary in-class native escape

- **GIVEN** an `App` subclass defining `def configure_api(self, api): api.get("/raw")(handler)`
- **WHEN** a finisher builds the App and assembles the FastAPI app
- **THEN** the `/raw` route registered inside the hook is present on the
  built app
- **AND** the same shape is available via `configure_mcp` / `configure_cli`

#### Scenario: Bootstrap live accessor (form b) is kept as the escape

- **GIVEN** a composition root `app = Kay()`
- **WHEN** the author calls `app.api.get("/raw")(handler)` at the root
  (after instantiation)
- **THEN** the route is registered — the live accessor survives as the
  deliberate bootstrap escape for raw-native needs with bootstrap-local
  context

#### Scenario: Class-body live accessor (form a) is impossible by construction

- **WHEN** an author attempts `@app.api.get(...)` inside the `class` body
- **THEN** there is no `app` instance to reference (the class body has not
  produced one), so the form cannot be written — `NameError`, not a
  framework check

#### Scenario: App run by instantiating at the entry point

- **WHEN** the author writes `Kay().serve()`
- **THEN** the instance is built and handed to the finisher; construction
  itself triggers no async work

#### Scenario: app.debug attribute access raises AttributeError

- **WHEN** an `App` subclass is constructed and `app.debug` is read
- **THEN** `AttributeError` is raised
- **AND** the message points at `app.config.debug` (consumer path) and
  `A2kitConfig` DI (subsystem path)
