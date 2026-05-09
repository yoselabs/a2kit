## ADDED Requirements

### Requirement: `a2kit.Plugin` Protocol defines the contribution surface

The core SHALL expose a `Plugin` `Protocol` (`@runtime_checkable`) at
`a2kit.plugin` (re-exported from `a2kit`). The Protocol defines:

- `register(app: "App") -> None` — REQUIRED. Called once when
  `app.use(plugin)` runs. The plugin caches the App ref, registers
  internal state, etc.

The following are OPTIONAL — plugins implement what they contribute:

- `cli_commands() -> list[click.Command]` — top-level CLI subcommands.
- `mcp_middleware() -> list[Middleware]` — FastMCP middleware to add
  to the server (in registration order).
- `depends_resolvers() -> list[DependsResolver]` — see
  `class-based-dependency-injection`.
- `claim(thing: Any) -> bool` and `adopt(thing: Any, app: "App") -> None`
  — let plugins handle foreign types passed to `app.use(...)`.

#### Scenario: minimal plugin with only register
- **WHEN** a class implements only `register(app)` and is `app.use(...)`'d
- **THEN** it is recognized as a `Plugin` and `register` is called exactly once

#### Scenario: plugin contributes CLI commands
- **WHEN** a plugin returns `[my_cmd]` from `cli_commands()` and the CLI is built via `build_full_cli(app)`
- **THEN** the top-level Click group includes `my_cmd`

#### Scenario: plugin contributes MCP middleware
- **WHEN** a plugin returns `[m1, m2]` from `mcp_middleware()` and the server is built via `build_mcp_server(app)`
- **THEN** the FastMCP server has `m1` and `m2` registered (in that order, after the kit's built-in middleware)

### Requirement: `App.use(thing)` polymorphic dispatch

`App.use(thing)` SHALL dispatch in this order:

1. If `isinstance(thing, Plugin)` (Protocol check) → call
   `thing.register(self)` and append to `self._plugins`.
2. Else if `thing` is a `Router` instance → add to router registry
   (core-native, no plugin needed).
3. Else: walk `self._plugins`; for each plugin that has a `claim`
   method, if `plugin.claim(thing) is True`, call
   `plugin.adopt(thing, self)` and stop.
4. Else: raise `TypeError` with a list of registered plugin types and
   a hint to `app.use(SomePlugin())` first.

`App.use(...)` SHALL return `self` for chaining.

#### Scenario: Router instance handled by core
- **WHEN** `app.use(MyRouter())` runs and no plugin would claim it
- **THEN** the router is added to the registry; no plugin involvement

#### Scenario: Foreign type claimed by a plugin
- **WHEN** `app.use(Connections())` then `app.use(TrackerConn)` runs
- **THEN** `Connections.claim(TrackerConn)` returns True; `Connections.adopt(TrackerConn, app)` registers it on the plugin's internal state

#### Scenario: Foreign type with no plugin claim raises
- **WHEN** `app.use(SomeRandomClass)` is called and no plugin claims it
- **THEN** `TypeError` is raised, listing registered plugins

#### Scenario: chaining
- **WHEN** `app.use(Connections()).use(TrackerConn).use(MyRouter())` is invoked
- **THEN** all three are applied; the call returns the same App

### Requirement: `App` exposes flattened plugin contributions

`App` SHALL provide methods that aggregate contributions across
registered plugins:

- `cli_commands() -> list[click.Command]` — concatenated in plugin
  registration order.
- `mcp_middlewares() -> list[Middleware]` — concatenated.
- `depends_resolvers() -> list[DependsResolver]` — concatenated.

Builders (`build_full_cli`, `build_mcp_server`) SHALL read from these
accessors. They SHALL NOT import any specific plugin module by name.

#### Scenario: zero plugins registered
- **WHEN** an App with no plugins is queried
- **THEN** all three accessors return empty lists; the CLI builder produces a CLI with only the verb / router subcommands; the MCP server has only the kit's built-in middleware

#### Scenario: cli_commands aggregates from multiple plugins
- **WHEN** `app.use(P1())` and `app.use(P2())` where P1 contributes `[c1]` and P2 contributes `[c2, c3]`
- **THEN** `app.cli_commands() == [c1, c2, c3]`
