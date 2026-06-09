# surfaces-projection Specification

## Purpose
TBD - created by archiving change surfaces-projection-axis. Update Purpose after archive.
## Requirements
### Requirement: `surfaces` is the single projection axis with three states

A verb's surface placement SHALL be governed by **one** axis, `surfaces`,
which resolves to a matrix assigning each registered surface exactly one
of three states:

- `ABSENT` — the verb is not mounted on that surface at all (no route, no
  registration, no DI override).
- `LISTED` — the verb is mounted AND advertised on that surface (appears
  in MCP `list_tools`, the CLI `--help`, and the OpenAPI schema).
- `UNLISTED` — the verb is mounted and callable on that surface but hidden
  from its listing/help/schema (MCP hidden-meta, Typer `--help` hide,
  FastAPI `include_in_schema=False`).

This single matrix SHALL subsume and replace the former `expose` tuple
and `visibility` string, and SHALL be the only placement axis (the
once-proposed `@cli()` operator-command concept is retired — an operator
command is a normal verb with `surfaces=("cli",)`).

#### Scenario: Every surface gets exactly one resolved state

- **GIVEN** an app with registered surfaces `mcp`, `api`, `cli`
- **WHEN** a verb's `surfaces` matrix is resolved
- **THEN** the matrix has exactly one entry per registered surface
- **AND** each value is one of `"absent"`, `"listed"`, `"unlisted"`
- **AND** no entry is left as `None` or "inherit" (resolution is complete)

#### Scenario: State separates mount from advertise

- **GIVEN** a verb whose resolved state on `api` is `UNLISTED`
- **WHEN** the HTTP surface is built
- **THEN** the verb is callable as `POST /api/<name>` (mounted)
- **AND** the verb is absent from the OpenAPI schema (`include_in_schema=False`)
- **AND** a verb whose state is `ABSENT` is neither callable nor advertised

### Requirement: Tuple shorthand spelling means LISTED on named surfaces, ABSENT elsewhere

When `surfaces=` is a tuple of surface names, the verb SHALL resolve to
`LISTED` on each named surface and `ABSENT` on every registered surface
not named. This is the common-case shorthand for "appear and be
advertised here."

#### Scenario: Tuple lists named surfaces only

- **GIVEN** registered surfaces `mcp`, `api`, `cli`
- **WHEN** a verb is decorated `@a2kit.read(surfaces=("mcp", "cli"))`
- **THEN** its resolved state is `LISTED` on `mcp`
- **AND** `LISTED` on `cli`
- **AND** `ABSENT` on `api`

#### Scenario: Single-surface operator command

- **GIVEN** registered surfaces `mcp`, `api`, `cli`
- **WHEN** a verb is decorated `@a2kit.write(surfaces=("cli",))`
- **THEN** its resolved state is `LISTED` on `cli`
- **AND** `ABSENT` on both `mcp` and `api`
- **AND** the verb still carries its `write` semantics (destructiveHint)

### Requirement: Dict escape spelling assigns explicit per-surface state

When `surfaces=` is a dict, each key SHALL name a surface and each value
SHALL be one of `"listed"`, `"unlisted"`, or `"absent"`. Any registered
surface not present as a key SHALL resolve to `ABSENT`. The dict is the
escape for the rare present-but-hidden (`UNLISTED`) case.

#### Scenario: Dict marks one surface UNLISTED, rest ABSENT

- **GIVEN** registered surfaces `mcp`, `api`, `cli`
- **WHEN** a verb is decorated `@a2kit.read(surfaces={"cli": "unlisted"})`
- **THEN** its resolved state is `UNLISTED` on `cli`
- **AND** `ABSENT` on `mcp` and `api`

#### Scenario: Dict with mixed explicit states

- **GIVEN** registered surfaces `mcp`, `api`, `cli`
- **WHEN** a verb is decorated `@a2kit.read(surfaces={"mcp": "listed", "api": "unlisted"})`
- **THEN** its resolved state is `LISTED` on `mcp`
- **AND** `UNLISTED` on `api`
- **AND** `ABSENT` on `cli` (not a key)

#### Scenario: Unknown surface key is rejected

- **GIVEN** registered surfaces `mcp`, `api`, `cli`
- **WHEN** a verb is decorated `@a2kit.read(surfaces={"foo": "listed"})`
- **THEN** a `TypeError` is raised at decoration time naming `foo`
- **AND** the message enumerates the registered surface names

### Requirement: Omitting `surfaces=` defaults to LISTED on every registered surface

When `surfaces=` is not supplied, the verb SHALL resolve to `LISTED` on
every registered surface. This is the friendly default, equivalent to the
former `expose=("mcp","api")` + `visibility="all"` plus the CLI now being
a peer surface.

#### Scenario: Default is everywhere-listed

- **GIVEN** registered surfaces `mcp`, `api`, `cli`
- **WHEN** a verb is decorated `@a2kit.read()` with no `surfaces=` kwarg
- **THEN** its resolved state is `LISTED` on `mcp`, `api`, and `cli`

### Requirement: The old `(expose, visibility)` pair maps mechanically onto the matrix

The migration from the two retired axes to `surfaces=` SHALL follow a
mechanical mapping so downstream consumers can rewrite each decorated
verb deterministically:

- `expose=("mcp","api"), visibility="all"` → `surfaces=("mcp","api","cli")` (or omit `surfaces=`).
- `visibility="cli"` (any `expose`) → `surfaces=("cli",)`.
- `visibility="hidden"` (any `expose`) → `surfaces={<surface>: "unlisted"}`.
- `expose=("mcp",)` → `surfaces=("mcp",)`; `expose=("api",)` → `surfaces=("api",)`.

A transitional decoration-time shim MAY recognize a legacy pair, map it
to the new matrix, and emit a `DeprecationWarning`; the canonical surface
is `surfaces=` only.

#### Scenario: cli-only legacy verb maps to single-surface tuple

- **GIVEN** a legacy verb that was `@a2kit.write(visibility="cli")`
- **WHEN** it is migrated per the mapping
- **THEN** the new form is `@a2kit.write(surfaces=("cli",))`
- **AND** the resolved matrix is `LISTED` on `cli`, `ABSENT` on every network surface (no HTTP leak by construction)

#### Scenario: hidden legacy verb maps to dict UNLISTED

- **GIVEN** a legacy verb that was `@a2kit.read(expose=("mcp",), visibility="hidden")`
- **WHEN** it is migrated per the mapping
- **THEN** the new form is `@a2kit.read(surfaces={"mcp": "unlisted"})`
- **AND** the resolved matrix is `UNLISTED` on `mcp`, `ABSENT` elsewhere

#### Scenario: Transitional shim warns and maps

- **GIVEN** the transitional shim is enabled for one minor version
- **WHEN** a verb is decorated with a legacy `visibility="cli"` pair
- **THEN** the verb resolves to the `surfaces=("cli",)` matrix
- **AND** a `DeprecationWarning` is emitted naming the `surfaces=` rewrite

