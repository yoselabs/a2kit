## MODIFIED Requirements

### Requirement: App composition uses three named verbs

The `a2kit.App` class SHALL expose exactly three composition verbs: `add_router(router)`, `add_cli(group_or_command)`, and `add_mcp_middleware(middleware)`. Each verb SHALL accept exactly one kind of thing and return the `App` for chaining. The `App` MUST NOT expose any polymorphic-dispatch verb, MUST NOT expose a class-claim shim (no `connect(C)`), and MUST NOT expose a factory-registration verb beyond `provide(...)`.

`a2kit.App` SHALL be a pure compose-phase builder with no sealed mode. Composition verbs SHALL remain callable at any time, including after the App has been handed to a finisher. A finisher's internal `build(app)` step snapshots the App's current composition into an `AppRuntime`; a composition verb called after `build()` SHALL affect only subsequent builds and SHALL NOT mutate any already-produced `AppRuntime`. There SHALL be no `_sealed` flag and no `TypeError` raised by a composition verb on the basis of App lifecycle state.

`App.__init__` SHALL accept the following keyword-only parameters in addition to the positional `name`:
- `config: A2kitConfig | None = None` — optional a2kit-owned configuration instance. When `None`, `App.__init__` SHALL construct a fresh `A2kitConfig()`, which picks up env / `.env` / defaults per the inverted source order. The resolved instance SHALL be exposed as `app.config`.
- `user_config: Any = None` — opaque developer-owned configuration pass-through, exposed as `app.user_config`. a2kit MUST NOT introspect this value.

`App.__init__` SHALL NOT accept a `debug` kwarg. The previous `App(debug=...)` surface is removed; debug mode is now a consumer-owned concern set via `A2KIT_DEBUG` env var or `A2kitConfig(debug=True)` kwarg.

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

#### Scenario: App.debug kwarg is removed

- **WHEN** user attempts `App("name", debug=True)`
- **THEN** a `TypeError` is raised because `debug` is not a recognized parameter

#### Scenario: App.user_config slot accepts arbitrary objects

- **GIVEN** a developer-owned settings instance `my_cfg = MyAppConfig(...)`
- **WHEN** user constructs `App("name", user_config=my_cfg)`
- **THEN** `app.user_config is my_cfg`

#### Scenario: App.user_config defaults to None

- **WHEN** user constructs `App("name")` with no `user_config`
- **THEN** `app.user_config` is `None`
