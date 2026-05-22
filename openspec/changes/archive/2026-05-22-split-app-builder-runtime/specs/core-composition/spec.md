## MODIFIED Requirements

### Requirement: App composition uses three named verbs

The `a2kit.AppBuilder` class SHALL expose exactly three composition
verbs: `add_router(router)`, `add_cli(group_or_command)`, and
`add_mcp_middleware(middleware)`. Each verb SHALL accept exactly one
kind of thing and return the `AppBuilder` for chaining. The builder
MUST NOT expose any polymorphic-dispatch verb (no `use(thing)`), MUST
NOT expose a class-claim shim (no `connect(C)`), and MUST NOT expose a
factory-registration verb beyond `provide(...)`.

The sealed `a2kit.App` produced by `AppBuilder.build()` SHALL expose
none of these composition verbs.

#### Scenario: Adding a Router

- **WHEN** user calls `builder.add_router(TasksRouter(get_store))`
- **THEN** the builder registers the router for tool collection and CLI
  subcommand mounting, and returns the builder

#### Scenario: Adding a CLI group

- **WHEN** user calls `builder.add_cli(connections_cli(store))`
- **THEN** the Click group is mounted as a subcommand on the root CLI
  built by `a2kit.run(builder.build())`

#### Scenario: Adding MCP middleware

- **WHEN** user calls `builder.add_mcp_middleware(my_middleware)`
- **THEN** the middleware is appended after kit-default middleware in
  `build_mcp_server(builder.build())`

#### Scenario: Polymorphic use is removed

- **WHEN** user code calls `builder.use(anything)`
- **THEN** Python raises `AttributeError` because the method does not
  exist on `AppBuilder`

#### Scenario: Composition verbs are absent from the sealed App

- **WHEN** user code calls `app.add_router(anything)` on a built `App`
- **THEN** it raises `TypeError` with a migration hint naming
  `AppBuilder`
