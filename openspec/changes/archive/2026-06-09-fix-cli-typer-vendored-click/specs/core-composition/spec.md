## MODIFIED Requirements

### Requirement: Connections package exposes plain classes and a CLI factory

The `a2kit.packages.connections` package SHALL export `ConnectionConfig` (Pydantic-settings base), `ConnectionStore` (load/save with `${VAR}` and `op://` substitution), and `connections_cli(store)` (a factory returning a Click group with `login`/`logout`/`list`/`show`/`delete` subcommands). The package MUST NOT export a `Connections` plugin class, a `Plugin` Protocol implementation, or any DI resolver classes.

`add_cli`-supplied commands SHALL attach to the assembled CLI regardless of which click distribution `typer` uses internally. `build_full_cli` MUST NOT gate the `cli_extras` attachment on an `isinstance` check against the top-level `click.Group` type, because at `typer >= 0.26` the root command produced by `typer.main.get_command` is an instance of typer's **vendored** click group, which is not identical to the standalone `click.Group` type. The attachment SHALL instead be guarded structurally (the assembled root command supports `add_command`), so that an app calling `app.add_cli(...)` builds successfully across the supported typer range.

#### Scenario: User wires connection management explicitly

- **WHEN** user writes `app.add_cli(connections_cli(conn_store))`
- **THEN** the `<app> connections {login,logout,list,show,delete}` subcommand is available

#### Scenario: add_cli commands attach under typer's vendored click

- **GIVEN** an environment where `typer >= 0.26` (typer vendors its own click)
- **AND** an `App` that has called `app.add_cli(some_click_command)`
- **WHEN** the CLI is assembled via `build_full_cli`
- **THEN** assembly completes without raising `TypeError`
- **AND** the `add_cli`-supplied command is reachable as a subcommand of the root CLI

#### Scenario: User omits connection wiring

- **WHEN** user constructs an App without calling `app.add_cli(connections_cli(...))`
- **THEN** `<app> --help` shows no `connections` subgroup
- **AND** `import a2kit` does not load the connections package into `sys.modules`

#### Scenario: ConnectionStore loads with substitution

- **WHEN** user calls `conn_store.load("default")` and the saved JSON contains `"token": "${MY_TOKEN}"`
- **THEN** the returned config has `token` resolved from the env at load time
- **AND** subsequent `conn_store.save(cfg)` writes the original `${MY_TOKEN}` placeholder, not the resolved value
