## ADDED Requirements

### Requirement: `CliSurface` is a `LOCAL`-kind Surface

`a2kit.packages.cli` SHALL define a `CliSurface` class that satisfies
the `Surface` Protocol (`name`, `reserved_types`,
`substrate_dep_markers`, `bind(runtime, descriptors)`,
`install_di_bridge(runtime, substrate_app)`) with `name = "cli"`. Its
`kind` ClassVar SHALL be `SurfaceKind.LOCAL`, distinguishing it from the
`NETWORK`-kind `McpSurface` / `ApiSurface`. The CLI SHALL no longer be a
special case built by a free `build_full_cli` function outside the
surface set; it joins the uniform surface protocol so all three
transports are assembled by one `bind(...)` shape.

#### Scenario: CliSurface satisfies the Surface protocol

- **WHEN** `isinstance(CliSurface(), Surface)` is evaluated
- **THEN** it returns `True`
- **AND** `CliSurface().name == "cli"`
- **AND** `CliSurface.kind == SurfaceKind.LOCAL`

#### Scenario: CLI is a peer of the network surfaces

- **GIVEN** the bundled surface set
- **WHEN** the `kind` of each surface is inspected
- **THEN** `McpSurface` and `ApiSurface` report `SurfaceKind.NETWORK`
- **AND** `CliSurface` reports `SurfaceKind.LOCAL`

### Requirement: `CliSurface.bind` owns the Typer build

`CliSurface.bind(runtime, descriptors)` SHALL build the top-level CLI
for the runtime and return the assembled command object (the Typer-backed
`click.Command`). All Typer composition that lived in the free
`build_full_cli` function — the per-router sub-Typers, the `schema` /
`list-tools` / `serve` / `code` / `health` subcommands, body-model UX,
format routing, and the `A2KIT_TOOLS` tool-selection seam — SHALL be
owned by `CliSurface.bind`. The behavior of the assembled CLI SHALL be
unchanged from the pre-Surface builder; this is a re-homing, not a
feature change.

#### Scenario: bind assembles the full CLI

- **GIVEN** an `App` with at least one router and one tool
- **WHEN** `CliSurface().bind(runtime)` runs
- **THEN** it returns a `click.Command` whose subcommands include the
  router slug, `schema`, `list-tools`, and `serve`
- **AND** invoking that command behaves identically to the command the
  former `build_full_cli` produced

#### Scenario: Tool-selection seam still honored

- **GIVEN** `A2KIT_TOOLS` is set to a subset selector
- **WHEN** `CliSurface().bind(runtime)` assembles the CLI
- **THEN** only the selected tools register as subcommands, exactly as
  the pre-Surface builder did

### Requirement: The vendored-click compatibility shim lives only in `CliSurface.bind`

The typer ≥ 0.26 vendored-click compatibility concern SHALL be contained
inside `CliSurface.bind` and SHALL NOT be smeared across the builder or
duplicated elsewhere. This folds Wave 0's structural `add_command`
capability guard into one place: when the assembled root command must
accept `cli_extras` subcommands, `bind` SHALL attach them via the
command's own `add_command` capability (a duck-typed `getattr`/`callable`
check) rather than an `isinstance` test against the standalone `click`
distribution, because at typer ≥ 0.26 the root command is an instance of
typer's *vendored* click `Group`, which is not identical to the
standalone `click.Group` type. If the root command exposes no callable
`add_command`, `bind` SHALL fail loud with a clear error rather than
silently dropping the extras.

#### Scenario: cli_extras attach across either click distribution

- **GIVEN** an `App` carrying one or more `add_cli(...)` Click commands
- **WHEN** `CliSurface().bind(runtime)` assembles the CLI under typer
  ≥ 0.26 (vendored click)
- **THEN** each extra command is attached via the root command's
  `add_command` capability
- **AND** the attachment succeeds regardless of whether typer vendors
  click or uses the standalone distribution

#### Scenario: Missing add_command fails loud

- **GIVEN** a root command object that exposes no callable `add_command`
- **AND** an `App` with at least one `cli_extras` command to attach
- **WHEN** `CliSurface().bind(runtime)` attempts to attach the extras
- **THEN** it raises a clear `TypeError` naming the missing
  `add_command` capability
- **AND** it does NOT silently discard the extras

### Requirement: `App.cli` accessor is symmetric with `App.api` and `App.mcp`

`App` SHALL expose an `App.cli` accessor that is the peer of the existing
`App.api` and `App.mcp` surface accessors, lazily constructing a
`CliSurface` on first touch via `importlib` so that touching it does NOT
eagerly import `typer` and so `import a2kit` stays cold. Subsequent
accesses SHALL be idempotent (return the same instance).

#### Scenario: app.cli returns a CliSurface

- **GIVEN** an `App` instance
- **WHEN** `app.cli` is accessed
- **THEN** it returns a `CliSurface` instance
- **AND** a second access returns the same instance (idempotent)

#### Scenario: Touching app.cli does not break cold-start

- **GIVEN** a fresh interpreter that has done `import a2kit`
- **WHEN** the `App.cli` property body is reached without invoking the CLI
- **THEN** the lazy `importlib` load is the only path that pulls `typer`
- **AND** the accessor mirrors the lazy shape of `App.api` / `App.mcp`
