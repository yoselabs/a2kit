## MODIFIED Requirements

### Requirement: App composition uses three named verbs

The `a2kit.App` class SHALL expose exactly three composition verbs:
`add_router(router)`, `add_cli(group_or_command)`, and
`add_mcp_middleware(middleware)`. Each verb SHALL accept exactly one
kind of thing and return the `App` for chaining. The `App` MUST NOT
expose any polymorphic-dispatch verb (no `use(thing)`), MUST NOT expose
a class-claim shim (no `connect(C)`), and MUST NOT expose a
factory-registration verb beyond `provide(...)`.

Once a finisher (`a2kit.run`, `build_mcp_server`, `a2kit.testing.client`)
has sealed an `App`, calling any of these verbs on it SHALL raise
`TypeError`.

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

#### Scenario: Polymorphic use is removed

- **WHEN** user code calls `app.use(anything)`
- **THEN** Python raises `AttributeError` because the method does not
  exist on `App`

#### Scenario: Composition after sealing is rejected

- **WHEN** a finisher has sealed an `App` and user code then calls
  `app.add_router(anything)`
- **THEN** it raises `TypeError` explaining the App is sealed
