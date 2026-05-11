## ADDED Requirements

### Requirement: `Surface` flag and `surfaces=` decorator kwarg

`a2kit.Surface` SHALL be a `Flag` enum with members `CLI`, `MCP`, and
the alias `ALL = CLI | MCP`. The tool decorators (`@read`, `@write`,
`@list_`, and any other tool-registering decorators) SHALL accept a
`surfaces: Surface` kwarg whose default is `Surface.ALL`. The value is
stored on the tool's metadata at `meta.extra["a2kit.surfaces"]`.

#### Scenario: Surface flag arithmetic composes
- **WHEN** a caller writes `Surface.CLI | Surface.MCP`
- **THEN** the result equals `Surface.ALL`, and `Surface.CLI in (Surface.CLI | Surface.MCP)` is True

#### Scenario: Default surfaces is ALL
- **WHEN** a tool is decorated with `@read()` (no explicit `surfaces=`)
- **THEN** `meta.extra["a2kit.surfaces"]` equals `Surface.ALL`

#### Scenario: Explicit surface narrowing is preserved
- **WHEN** a tool is decorated with `@read(surfaces=Surface.CLI)`
- **THEN** `meta.extra["a2kit.surfaces"]` equals `Surface.CLI` exactly

### Requirement: transport mounters filter tools by Surface

The MCP server tool-registration step SHALL skip any tool whose
declared surfaces do not include `Surface.MCP`. The CLI builder SHALL
skip any tool whose declared surfaces do not include `Surface.CLI`.
Both apply the filter at mount/build time, not at decoration time.

#### Scenario: CLI-only tool is invisible to MCP mount
- **WHEN** a tool with `surfaces=Surface.CLI` is registered on an App and an MCP server is built from that App
- **THEN** the MCP tool list does not contain the tool

#### Scenario: MCP-only tool is invisible to CLI build
- **WHEN** a tool with `surfaces=Surface.MCP` is registered on an App and a CLI is built from that App
- **THEN** the CLI command list does not contain the tool

#### Scenario: ALL-surface tool is visible everywhere
- **WHEN** a tool with `surfaces=Surface.ALL` (default) is registered
- **THEN** the tool appears on both the MCP tool list and the CLI command list

### Requirement: Router carries providers and lifecycle

`a2kit.Router` SHALL support three optional surface attributes beyond
its tools:

- `providers: tuple[type | Provider, ...]` — class attribute, defaults to `()`
- `on_startup` — method recognized by name; awaited during App startup
- `on_shutdown` — method recognized by name; awaited during App shutdown

`App.add_router(r)` SHALL install all three in addition to the tools.

#### Scenario: Router providers are installed by add_router
- **WHEN** a Router subclass declares `providers = (Foo,)` and is passed to `app.add_router(...)`
- **THEN** `Foo` is registered as a provider on the App's container

#### Scenario: Router lifecycle hooks fire
- **WHEN** a Router subclass defines `async def on_startup(self)` and is added to an App
- **THEN** the method is awaited during App startup, and the symmetric `on_shutdown` is awaited at shutdown

#### Scenario: Plain Router without extras is unchanged
- **WHEN** a Router subclass declares only tools (no `providers`, no lifecycle)
- **THEN** behavior matches the current Router contract — only tools are installed

### Requirement: `connections` factory returns an enriched Router

`a2kit.packages.connections.connections(conn_cls)` SHALL return a
`Router` instance carrying:

- A tool decorated with `surfaces=Surface.CLI` for each credential-management
  operation (login, logout, …)
- A tool with the default `Surface.ALL` for `list_connections`
- `providers = (conn_cls,)`
- Lifecycle hooks (`on_startup` / `on_shutdown`) for connection-pool warm/close

`app.add_router(connections(X))` is the canonical install path. The
prior `connections_cli(X)` factory SHALL emit a `DeprecationWarning`
with the migration hint and continue to work for one release.

#### Scenario: connections router installs provider via add_router
- **WHEN** `app.add_router(connections(TrackerConn))` is called
- **THEN** `TrackerConn` is registered as a provider on the App's container

#### Scenario: login tool is CLI-only by default
- **WHEN** a connections Router is built and the App's MCP server is started
- **THEN** the MCP tool list does not contain `login` or `logout`

#### Scenario: list_connections is on both surfaces
- **WHEN** a connections Router is built and both CLI and MCP surfaces are mounted
- **THEN** `list_connections` appears on both

#### Scenario: connections_cli emits deprecation warning
- **WHEN** `connections_cli(TrackerConn)` is called
- **THEN** exactly one `DeprecationWarning` is emitted, pointing at the new factory

### Requirement: `A2K-SURFACE-EXPLICIT` lint rule

The lint package SHALL ship an `A2K-SURFACE-EXPLICIT` rule that fires
when a tool decorator omits the `surfaces=` kwarg AND the tool's name
matches a credential heuristic dictionary (login, logout, signin,
signout, authenticate, auth_*, set_token, set_credential, rotate_key,
rotate_secret, issue_token, revoke_token).

#### Scenario: Credential-named tool without explicit surface fires
- **WHEN** a function `async def login(...)` is decorated `@read()`
- **THEN** the lint rule emits a finding pointing at the decorator with a hint to declare `surfaces=Surface.CLI` (or `Surface.ALL` to suppress)

#### Scenario: Explicit surface declaration suppresses the finding
- **WHEN** the same function is decorated `@read(surfaces=Surface.CLI)`
- **THEN** the rule does not fire

#### Scenario: Non-credential names do not fire
- **WHEN** a function `async def list_projects(...)` is decorated `@read()`
- **THEN** the rule does not fire
