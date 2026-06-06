## MODIFIED Requirements

### Requirement: App composition uses three named verbs

The `a2kit.App` class SHALL expose exactly three composition verbs: `add_router(router)`, `add_cli(group_or_command)`, and `add_mcp_middleware(middleware)`. Each verb SHALL accept exactly one kind of thing and return the `App` for chaining. The `App` MUST NOT expose any polymorphic-dispatch verb, MUST NOT expose a class-claim shim (no `connect(C)`), and MUST NOT expose a factory-registration verb beyond `provide(...)`.

`a2kit.App` SHALL be a pure compose-phase builder with no sealed mode. Composition verbs SHALL remain callable at any time, including after the App has been handed to a finisher. A finisher's internal `build(app)` step snapshots the App's current composition into an `AppRuntime`; a composition verb called after `build()` SHALL affect only subsequent builds and SHALL NOT mutate any already-produced `AppRuntime`. There SHALL be no `_sealed` flag and no `TypeError` raised by a composition verb on the basis of App lifecycle state.

Composition SHALL produce a **two-level tree** — the `App` is the root and each added `Router` is a child node keyed by its `slug` — that is mounted **level-for-level onto each surface's native composition tree** (the homomorphism, ADR 0028 decision 3): the `App` maps to the native app (root FastMCP server / root FastAPI app / root Typer) and each `Router` maps to a native sub-node (`FastMCP.mount(namespace=slug)` / `FastAPI.include_router(prefix=…)` / `Typer.add_typer`). Composition MUST NOT flatten the tree into a single root-level node list; the parity contract is **ours↔native at each level**, NOT App↔Router. Each materialized verb descriptor SHALL retain enough identity (`router_slug` for router verbs, none for app-level verbs, plus the function leaf name) for every surface to render the canonical name from one shared resolver without re-deriving the slug.

`App.__init__` SHALL accept the following keyword-only parameters in addition to the positional `name`:
- `config: A2kitConfig | None = None` — optional a2kit-owned configuration instance. When `None`, `App.__init__` SHALL construct a fresh `A2kitConfig()`, which picks up env / `.env` / defaults per the inverted source order. The resolved instance SHALL be exposed as `app.config`.
- `user_config: Any = None` — opaque developer-owned configuration pass-through, exposed as `app.user_config`. a2kit MUST NOT introspect this value.

`App.__init__` SHALL NOT accept a `debug` kwarg. Debug mode is a consumer-owned concern (ADR 0022) and SHALL be set via env `A2KIT_DEBUG=true` or via `A2kitConfig(debug=True)`. An attempt to construct `App("name", debug=True)` SHALL raise `TypeError` carrying a migration hint pointing at the env var and the config kwarg.

`App` SHALL NOT expose a `debug` attribute. Consumer-side reads of debug mode SHALL use `app.config.debug`. Subsystem-side reads SHALL resolve `A2kitConfig` via DI (typed dependency). Access to `app.debug` SHALL raise `AttributeError` with a migration hint naming both replacement paths.

#### Scenario: Adding a Router

- **WHEN** user calls `app.add_router(TasksRouter(get_store))`
- **THEN** the `App` registers the router for tool collection and CLI
  subcommand mounting, and returns the `App`

#### Scenario: Adding a CLI group

- **WHEN** user calls `app.add_cli(connections_cli(store))`
- **THEN** the Click group is mounted as a subcommand on the root CLI
  built by `a2kit.run(app)`

#### Scenario: Adding MCP middleware

- **WHEN** user calls `app.add_mcp_middleware(my_middleware)`
- **THEN** the middleware is appended after kit-default middleware in
  `build_mcp_server(app)`

#### Scenario: Only three named verbs exist

- **WHEN** user inspects the `App` composition surface
- **THEN** exactly `add_router`, `add_cli`, and `add_mcp_middleware` are present, with no polymorphic-dispatch verb alongside them

#### Scenario: Router mounts as a native sub-node, not flat

- **GIVEN** `Entity(slug="entity")` with a verb `update` and `Ontology(slug="ontology")` with a verb `update`, both added to one App
- **WHEN** the App is materialized for any surface
- **THEN** the two routers are distinct child nodes mounted under their slugs (native `mount` / `include_router` / `add_typer`)
- **AND** the two `update` verbs do NOT collide on a single flat root-level namespace
- **AND** each descriptor retains `router_slug` so the canonical name resolves to `entity_update` and `ontology_update` respectively

#### Scenario: App-level verb mounts at the root, no slug prefix

- **GIVEN** an app-level verb `health` with no owning router
- **WHEN** the App is materialized for any surface
- **THEN** the verb mounts on the native root node (root server / root app / top-level command)
- **AND** its canonical name is the bare leaf `health` (the app name is identity, never a prefix)

#### Scenario: Composition after build affects only future builds

- **WHEN** a finisher has built an `AppRuntime` from an `App` and user code then calls `app.add_router(another)`
- **THEN** no `TypeError` is raised
- **AND** the already-built `AppRuntime` does not observe `another`
- **AND** a subsequent `build(app)` produces an `AppRuntime` that does include `another`

#### Scenario: App constructed without explicit config gets a fresh A2kitConfig

- **WHEN** user constructs `App("name")` with no `config` kwarg
- **THEN** `app.config` is a fresh `A2kitConfig()` instance reflecting current env / .env / defaults

#### Scenario: App accepts an explicit config instance

- **WHEN** user constructs `App("name", config=A2kitConfig(debug=True))`
- **AND** no `A2KIT_DEBUG` env var is set
- **THEN** `app.config.debug` is `True`

#### Scenario: App(debug=...) kwarg raises TypeError with migration hint

- **WHEN** user attempts `App("name", debug=True)`
- **THEN** `TypeError` is raised
- **AND** the error message names `A2KIT_DEBUG` and `A2kitConfig(debug=True)` as the migration targets

#### Scenario: env beats config kwarg for debug

- **GIVEN** `A2KIT_DEBUG=false` in process env
- **WHEN** user constructs `App("name", config=A2kitConfig(debug=True))`
- **THEN** `app.config.debug` is `False` (env wins per ADR 0022)

#### Scenario: app.debug attribute access raises AttributeError

- **WHEN** user constructs `App("name")` and reads `app.debug`
- **THEN** `AttributeError` is raised
- **AND** the message points at `app.config.debug` (consumer path) and `A2kitConfig` DI (subsystem path)

#### Scenario: App.user_config slot accepts arbitrary objects

- **GIVEN** a developer-owned settings instance `my_cfg = MyAppConfig(...)`
- **WHEN** user constructs `App("name", user_config=my_cfg)`
- **THEN** `app.user_config is my_cfg`

#### Scenario: App.user_config defaults to None

- **WHEN** user constructs `App("name")` with no `user_config`
- **THEN** `app.user_config` is `None`
