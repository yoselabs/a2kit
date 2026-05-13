# verb-decorators delta

## MODIFIED Requirements

### Requirement: Verb decorators accept MCP annotation kwargs

`@a2kit.read`, `@a2kit.write`, and `@a2kit.tool` SHALL accept the
MCP-annotation kwargs `idempotent: bool`, `open_world: bool`, and
`title: str | None` (and `destructive: bool` on `@write` and
`@tool`), forwarding them to the constructed `ToolAnnotations`. The
CLI-side implementation seam for `Surface.CLI`-mounted tools SHALL
resolve through a Typer-driven adapter; the decorator API and
metadata stamping SHALL remain unchanged.

#### Scenario: read with all annotation kwargs

- **WHEN** a tool is decorated `@a2kit.read(idempotent=True, open_world=True, title="Fetch")`
- **THEN** the stamped `A2KitMeta.annotations` carries `ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=True, title="Fetch")`

#### Scenario: write with destructive override

- **WHEN** a tool is decorated `@a2kit.write(destructive=False, idempotent=True, title="Mark Complete")`
- **THEN** the annotations carry `readOnlyHint=False, destructiveHint=False, idempotentHint=True, title="Mark Complete"`

#### Scenario: CLI surface resolves through the Typer adapter

- **GIVEN** a tool decorated `@a2kit.read(...)` with `surfaces=Surface.ALL` (default) or `Surface.CLI`
- **WHEN** the CLI is built via `build_full_cli(app)` and the user runs `<app> <router> <tool> --help`
- **THEN** the resolved command is constructed by the Typer-based
  builder (no hand-built `click.Command` for tool callbacks), and
  the help text, option flags, and exit codes are observably
  equivalent to the prior Click-only path except for body-model
  parameters (see the `tool-description-contract` delta) and Typer's
  default wording for usage errors
- **AND** the tool-author surface (the decorator call, the function
  signature, the docstring) is unchanged
