## MODIFIED Requirements

### Requirement: A2kitConfig is the single typed config surface

a2kit SHALL expose a single typed configuration root, `a2kit.config.A2kitConfig`, defined as a `pydantic_settings.BaseSettings` model. The root SHALL contain sub-models for each subsystem (`mcp: McpConfig`, `http: HttpConfig`, `cli: CliConfig`, `ldd: LddConfig`) plus top-level scalar fields for cross-cutting concerns (currently: `debug: bool`). Sub-models SHALL be plain `pydantic.BaseModel` instances composed under the root. Additional sub-models MAY be added in future changes without breaking this requirement.

#### Scenario: A2kitConfig instantiates with defaults

- **WHEN** `A2kitConfig()` is constructed with no arguments and no `A2KIT_*` env vars set
- **THEN** `cfg.mcp.structured_output` is `False`
- **AND** `cfg.debug` is `False`
- **AND** `cfg.ldd.level` is `"info"`

#### Scenario: Sub-model fields are accessible via dotted attribute paths

- **WHEN** code reads `cfg.mcp.structured_output`
- **THEN** the value is a `bool`

#### Scenario: Unknown env vars are ignored without raising

- **WHEN** `A2KIT_UNKNOWN__FIELD=value` is set and `A2kitConfig()` is constructed
- **THEN** construction succeeds and the unknown var is silently ignored

## ADDED Requirements

### Requirement: A2kitConfig.ldd.level is the consumer-owned LDD threshold

`A2kitConfig` SHALL expose a sub-model `ldd: LddConfig` with field `level: Literal["trace", "debug", "info", "warning", "error"]` defaulting to `"info"`. The field SHALL be settable via env var `A2KIT_LDD__LEVEL` (case-insensitive), via `.env` file entry, or via `A2kitConfig(ldd=LddConfig(level="debug"))` kwarg. Per ADR 0022's inverted source order, env wins over kwargs. Invalid string values SHALL raise `pydantic.ValidationError` at `A2kitConfig` construction time.

#### Scenario: default level is info

- **GIVEN** no `A2KIT_LDD__LEVEL` env var is set and no `.env` file with that key exists
- **WHEN** `A2kitConfig()` is constructed
- **THEN** `cfg.ldd.level` is `"info"`

#### Scenario: env sets level

- **GIVEN** `A2KIT_LDD__LEVEL=debug` in process env
- **WHEN** `A2kitConfig()` is constructed
- **THEN** `cfg.ldd.level` is `"debug"`

#### Scenario: env beats kwarg

- **GIVEN** `A2KIT_LDD__LEVEL=warning` in process env
- **WHEN** `A2kitConfig(ldd=LddConfig(level="trace"))` is constructed
- **THEN** `cfg.ldd.level` is `"warning"` (env wins per ADR 0022)

#### Scenario: invalid level raises at construction

- **GIVEN** `A2KIT_LDD__LEVEL=verbose` in process env (not in the allowed set)
- **WHEN** `A2kitConfig()` is constructed
- **THEN** a `pydantic.ValidationError` is raised

#### Scenario: kwarg wins when env unset

- **GIVEN** no `A2KIT_LDD__LEVEL` env var is set
- **WHEN** `A2kitConfig(ldd=LddConfig(level="trace"))` is constructed
- **THEN** `cfg.ldd.level` is `"trace"`

### Requirement: A2kitConfig.ldd.enabled is the hard kill-switch

`LddConfig` SHALL expose a field `enabled: bool` defaulting to `True`. The field SHALL be settable via env var `A2KIT_LDD__ENABLED`, via `.env` file entry, or via `A2kitConfig(ldd=LddConfig(enabled=False))` kwarg. When `enabled=False`, the App's runtime `ldd_reports` and `ldd_events` SHALL both be `False` regardless of any `level` setting — the kill-switch is orthogonal to and overrides the threshold. This replaces the v0.x bare `A2KIT_LDD=off` legacy env var, which is removed (it collided with the new `A2KIT_LDD__*` nested namespace where pydantic-settings parses `A2KIT_LDD` as JSON for the entire `ldd` sub-model).

#### Scenario: default enabled is True

- **GIVEN** no `A2KIT_LDD__ENABLED` env var is set
- **WHEN** `a2kit.App("svc")` is constructed
- **THEN** `app.ldd_reports` is `True`
- **AND** `app.ldd_events` is `True`

#### Scenario: env disables both channels

- **GIVEN** `A2KIT_LDD__ENABLED=false` in process env
- **WHEN** `a2kit.App("svc")` is constructed
- **THEN** `app.ldd_reports` is `False`
- **AND** `app.ldd_events` is `False`

#### Scenario: legacy A2KIT_LDD=off fails loudly

- **GIVEN** `A2KIT_LDD=off` in process env (the v0.x legacy kill-switch var)
- **WHEN** `a2kit.App("svc")` is constructed
- **THEN** a `pydantic_settings.SettingsError` is raised because pydantic-settings tries to parse "off" as JSON for the entire `ldd` sub-model
- **AND** consumers MUST migrate to `A2KIT_LDD__ENABLED=false`
