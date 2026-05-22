## MODIFIED Requirements

### Requirement: App composition uses three named verbs

The `a2kit.App` class SHALL expose exactly three composition verbs: `add_router(router)`, `add_cli(group_or_command)`, and `add_mcp_middleware(middleware)`. Each verb SHALL accept exactly one kind of thing and return the `App` for chaining. The `App` MUST NOT expose any polymorphic-dispatch verb, MUST NOT expose a class-claim shim (no `connect(C)`), and MUST NOT expose a factory-registration verb beyond `provide(...)`.

`a2kit.App` SHALL be a pure compose-phase builder with no sealed mode. Composition verbs SHALL remain callable at any time, including after the App has been handed to a finisher. A finisher's internal `build(app)` step snapshots the App's current composition into an `AppRuntime`; a composition verb called after `build()` SHALL affect only subsequent builds and SHALL NOT mutate any already-produced `AppRuntime`. There SHALL be no `_sealed` flag and no `TypeError` raised by a composition verb on the basis of App lifecycle state.

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

### Requirement: `App.container()` returns the active container

The compose-phase `App` class SHALL eager-initialize a `Container` instance during `App.__init__` and SHALL expose `container() -> Container` returning that instance. The return type is non-`Optional`. This compose-phase container accumulates `provide(...)` registrations and remains mutable for the App's whole lifetime — it is never sealed.

A finisher's internal `build(app)` step SHALL NOT seal or mutate the compose-phase container. It SHALL snapshot the App's provider registrations and wire-scopes into a separate, freshly constructed `Container` owned by the resulting `AppRuntime`. Each `build()` call SHALL produce an independent runtime container, so one `App` MAY be handed to more than one finisher.

#### Scenario: Container available immediately after App construction

- **WHEN** `app = App("name")` is constructed and `app.container()` is called
- **THEN** the return value is a `Container` instance
- **AND** the call site is not required to check for `None`

#### Scenario: Single compose-phase container across an App's lifetime

- **WHEN** `app.container()` is called twice on the same `App` instance
- **THEN** both calls return the same object

#### Scenario: Each build produces an independent runtime container

- **WHEN** the same `App` is handed to two finishers in turn
- **THEN** each `build()` constructs a fresh runtime `Container` from the App's registrations
- **AND** neither runtime container is the App's compose-phase container
