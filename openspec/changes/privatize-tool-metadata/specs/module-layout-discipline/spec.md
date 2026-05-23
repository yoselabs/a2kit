## ADDED Requirements

### Requirement: `A2K-METADATA-PRIVATE` lint rule

A new lint rule `A2K-METADATA-PRIVATE` SHALL AST-scan every file under `src/a2kit/packages/` and reject any import of `_get_meta` or `_set_meta` from `a2kit.metadata` unless the importing module is in the allowlist `{a2kit._verbs, a2kit.metadata, a2kit.runtime, a2kit.tool, a2kit.app, a2kit.routers, a2kit.schema}`.

The allowlist SHALL be a frozen constant at the top of the rule module. The rule SHALL additionally reject any access to the public-name shims (`get_meta`, `set_meta`) as a separate, lower-severity diagnostic that names the migration path (these would already raise at runtime, but lint catches them statically).

#### Scenario: substrate adapter importing `_get_meta` is rejected

- **GIVEN** a file `src/a2kit/packages/mcp/server.py` contains `from a2kit.metadata import _get_meta`
- **WHEN** `make lint` runs
- **THEN** `A2K-METADATA-PRIVATE` raises naming the offending file
- **AND** the message points to `runtime.descriptor_for(name)` as the replacement

#### Scenario: allowlisted module passes

- **GIVEN** `src/a2kit/app.py` imports `_get_meta` from `a2kit.metadata`
- **WHEN** `make lint` runs
- **THEN** `A2K-METADATA-PRIVATE` does not flag it
