## MODIFIED Requirements

### Requirement: Tool-context implementations live in a transport-neutral package

Concrete `ToolContext` implementations MUST be defined in the
`a2kit.packages.context` package (`StderrToolContext` and any sibling
implementations). That package MUST NOT import any transport package
(`cli`, `mcp`, `codemode`). Its only `a2kit.packages.*` dependency is a
lazy import of `a2kit.packages.log` (the `format_ldd_line` wire-format
primitive, inside `_emit`), so a bare `import a2kit.packages.context`
pulls no other a2kit package.

The `a2kit.packages.cli.context` tombstone module (which raised a
migration hint on the old import path) is swept under the tombstone
sunset rule (`AGENTS.md` §1): the module is deleted, so
`import a2kit.packages.cli.context` raises the language-default
`ModuleNotFoundError`. The new home is recorded in the CHANGELOG.

#### Scenario: mcp wrappers do not import cli

- **WHEN** `a2kit.packages.mcp._wrappers` is imported
- **THEN** no `a2kit.packages.cli` module is imported as a result

#### Scenario: context package imports no transport package

- **WHEN** `a2kit.packages.context` is imported
- **THEN** no `a2kit.packages.cli`, `a2kit.packages.mcp`, or
  `a2kit.packages.codemode` module is imported as a result
