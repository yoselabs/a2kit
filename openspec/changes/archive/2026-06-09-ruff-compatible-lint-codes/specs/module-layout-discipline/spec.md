## MODIFIED Requirements

### Requirement: `A2K-METADATA-PRIVATE` lint rule

The metadata-privacy lint rule (legacy code `A2K-METADATA-PRIVATE`, renamed to the ruff-`noqa`-grammar-safe code `AK210` matching `^[A-Z]+[0-9]+$`) SHALL AST-scan every file under `src/a2kit/` and reject any import of `_get_meta` or `_set_meta` from `a2kit.metadata` unless the importing module is in the allowlist `{a2kit._verbs, a2kit.metadata, a2kit.runtime, a2kit.tool, a2kit.app, a2kit.routers, a2kit.schema}`. The legacy `A2K-METADATA-PRIVATE` spelling resolves to `AK210` through `LEGACY_CODE_ALIASES` during the deprecation window.

The allowlist SHALL be a frozen constant at the top of the rule module (`packages/lint/rules/metadata_private.py`). Test files under `tests/` are exempt via the standard `is_fixture_path` filter — tests inspecting decorator-time stamping pre-`build()` may import `_get_meta` directly.

#### Scenario: substrate adapter importing `_get_meta` is rejected

- **GIVEN** a file `src/a2kit/packages/mcp/server.py` contains `from a2kit.metadata import _get_meta`
- **WHEN** `make lint` runs
- **THEN** the rule `AK210` raises naming the offending file
- **AND** the message points to `runtime.descriptor_for(name)` as the replacement

#### Scenario: allowlisted module passes

- **GIVEN** `src/a2kit/app.py` imports `_get_meta` from `a2kit.metadata`
- **WHEN** `make lint` runs
- **THEN** the rule `AK210` does not flag it

#### Scenario: legacy code spelling still suppresses the rule

- **GIVEN** an allowlist-exempt line carrying `# noqa: A2K-METADATA-PRIVATE -- legacy spelling`
- **AND** `A2K-METADATA-PRIVATE` aliases to `AK210`
- **WHEN** `make lint` runs
- **THEN** the `AK210` finding is suppressed on that line
