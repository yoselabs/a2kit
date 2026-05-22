## ADDED Requirements

### Requirement: The package import graph is acyclic

The import graph of `src/a2kit/` MUST be a directed acyclic graph,
spanning core modules (`a2kit.*`) and plugin packages
(`a2kit.packages.*`) alike. Cycle detection MUST account for imports
guarded by `TYPE_CHECKING`, so a type-only cycle is not exempt.

#### Scenario: no cli/mcp cycle

- **WHEN** the static import graph of `src/a2kit/` is built
- **THEN** there is no cyclic path between `a2kit.packages.cli` and
  `a2kit.packages.mcp`

#### Scenario: no mcp/codemode cycle

- **WHEN** the static import graph of `src/a2kit/` is built
- **THEN** there is no cyclic path between `a2kit.packages.mcp` and
  `a2kit.packages.codemode`

#### Scenario: no app/health cycle, including type-only imports

- **WHEN** the static import graph of `src/a2kit/` is built, counting
  `TYPE_CHECKING`-guarded imports
- **THEN** there is no cyclic path between `a2kit.app` and
  `a2kit.packages.health`

#### Scenario: no testing-shim cycle

- **WHEN** the static import graph of `src/a2kit/` is built
- **THEN** there is no cyclic path between `a2kit.testing` and
  `a2kit.packages.testing`

### Requirement: Tool-context implementations live in a transport-neutral package

Concrete `ToolContext` implementations MUST be defined in the
`a2kit.packages.context` package (`StderrToolContext` and any sibling
implementations). That package MUST NOT import any transport package
(`cli`, `mcp`, `codemode`). Its only `a2kit.packages.*` dependency is a
lazy import of `a2kit.packages.ldd` (the `format_ldd_line` wire-format
primitive, inside `_emit`), so a bare `import a2kit.packages.context`
pulls no other a2kit package.

#### Scenario: mcp wrappers do not import cli

- **WHEN** `a2kit.packages.mcp._wrappers` is imported
- **THEN** no `a2kit.packages.cli` module is imported as a result

#### Scenario: context package imports no transport package

- **WHEN** `a2kit.packages.context` is imported
- **THEN** no `a2kit.packages.cli`, `a2kit.packages.mcp`, or
  `a2kit.packages.codemode` module is imported as a result

#### Scenario: old StderrToolContext path raises a migration hint

- **WHEN** code runs `from a2kit.packages.cli.context import StderrToolContext`
- **THEN** it raises with a message naming `a2kit.packages.context` as
  the new import home

### Requirement: run_code is owned by the CLI package

`run_code` MUST be defined in `a2kit.packages.cli` and MUST NOT be
defined in or re-exported from `a2kit.packages.codemode`. The
`codemode` package MUST NOT import `a2kit.packages.mcp.server`.

#### Scenario: codemode does not import the mcp server builder

- **WHEN** `a2kit.packages.codemode` is imported
- **THEN** `a2kit.packages.mcp.server` is not imported as a result

#### Scenario: old run_code path raises a migration hint

- **WHEN** code runs `from a2kit.packages.codemode import run_code`
- **THEN** it raises with a message naming `a2kit.packages.cli` as the
  new home

### Requirement: Health checks resolve dependencies via a Resolver

`run_checks` MUST accept a `Resolver` and MUST NOT accept an `App`.
The `packages/health` package MUST NOT import `a2kit.app` in any form,
including under `TYPE_CHECKING`.

#### Scenario: run_checks takes a Resolver

- **WHEN** `run_checks` is introspected
- **THEN** its dependency parameter is annotated `Resolver`, not `App`

#### Scenario: health does not import app

- **WHEN** `a2kit.packages.health` source is inspected
- **THEN** it contains no import of `a2kit.app`, runtime or
  `TYPE_CHECKING`-guarded

### Requirement: MCP dispatch wrappers are typed against framework types

The `_wrap_with_*` functions in `a2kit.packages.mcp._wrappers` MUST
annotate framework objects with their real types (`app: App`,
`router: Router | None`) rather than `Any`.

#### Scenario: router-lazy-enter wrapper is typed

- **WHEN** `_wrap_with_router_lazy_enter` is introspected
- **THEN** its `app` parameter is annotated `App` and its `router`
  parameter is annotated `Router | None`
