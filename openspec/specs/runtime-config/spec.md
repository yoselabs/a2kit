# runtime-config Specification

## Purpose
TBD - created by archiving change a2kit-config-surface. Update Purpose after archive.
## Requirements
### Requirement: A2kitConfig is the single typed config surface

a2kit SHALL expose a single typed configuration root, `a2kit.config.A2kitConfig`, defined as a `pydantic_settings.BaseSettings` model. The root SHALL contain sub-models for each subsystem (`mcp: McpConfig`, `http: HttpConfig`, `cli: CliConfig`) plus top-level scalar fields for cross-cutting concerns (currently: `debug: bool`). Sub-models SHALL be plain `pydantic.BaseModel` instances composed under the root. Additional sub-models MAY be added in future changes without breaking this requirement.

#### Scenario: A2kitConfig instantiates with defaults

- **WHEN** `A2kitConfig()` is constructed with no arguments and no `A2KIT_*` env vars set
- **THEN** `cfg.mcp.structured_output` is `False`
- **AND** `cfg.debug` is `False`

#### Scenario: Sub-model fields are accessible via dotted attribute paths

- **WHEN** code reads `cfg.mcp.structured_output`
- **THEN** the value is a `bool`

#### Scenario: Unknown env vars are ignored without raising

- **WHEN** `A2KIT_UNKNOWN__FIELD=value` is set and `A2kitConfig()` is constructed
- **THEN** construction succeeds and the unknown var is silently ignored

### Requirement: Env vars override kwargs (inverted source order)

`A2kitConfig` SHALL customize `pydantic_settings`' source ordering such that process env vars and `.env` file values rank ABOVE init kwargs and field defaults. The effective precedence chain SHALL be: process env > `.env` file > init kwargs > field defaults. This inverts the pydantic-settings library default (which puts init kwargs first) and is load-bearing per ADR 0022 — the consumer (env) beats the developer (code).

#### Scenario: Env overrides an explicit kwarg

- **GIVEN** the env var `A2KIT_MCP__STRUCTURED_OUTPUT=true` is set
- **WHEN** code constructs `A2kitConfig(mcp=McpConfig(structured_output=False))`
- **THEN** `cfg.mcp.structured_output` is `True`

#### Scenario: Env overrides a code-author default

- **GIVEN** the env var `A2KIT_DEBUG=true` is set
- **WHEN** code constructs `A2kitConfig()` with no kwargs
- **THEN** `cfg.debug` is `True`

#### Scenario: Kwarg wins when env is unset

- **GIVEN** no `A2KIT_*` env vars are set
- **WHEN** code constructs `A2kitConfig(debug=True)`
- **THEN** `cfg.debug` is `True`

#### Scenario: `.env` file ranks above kwargs

- **GIVEN** a `.env` file in the current working directory contains `A2KIT_DEBUG=true`
- **WHEN** code constructs `A2kitConfig(debug=False)`
- **THEN** `cfg.debug` is `True`

### Requirement: Env var convention uses A2KIT_ prefix with double-underscore nesting

Every `A2kitConfig` field SHALL be settable via an environment variable using the prefix `A2KIT_` and the double-underscore (`__`) delimiter for nested sub-model fields. Field names SHALL be uppercased; snake_case is preserved within sub-model field names (single `_` within a name MUST NOT be interpreted as nesting). Boolean parsing SHALL accept the pydantic-settings defaults (`1`, `true`, `yes`, `on`, case-insensitive, for true; `0`, `false`, `no`, `off` for false).

#### Scenario: Nested field set via env

- **GIVEN** `A2KIT_MCP__STRUCTURED_OUTPUT=true`
- **WHEN** `A2kitConfig()` is constructed
- **THEN** `cfg.mcp.structured_output` is `True`

#### Scenario: Top-level field set via env

- **GIVEN** `A2KIT_DEBUG=true`
- **WHEN** `A2kitConfig()` is constructed
- **THEN** `cfg.debug` is `True`

#### Scenario: Single underscore in field name is not nesting

- **GIVEN** `A2KIT_MCP__STRUCTURED_OUTPUT=true` (note: `STRUCTURED_OUTPUT` has single `_` between words)
- **WHEN** `A2kitConfig()` is constructed
- **THEN** `cfg.mcp.structured_output` is `True` (the `_` is part of the field name `structured_output`, not a nesting separator)

#### Scenario: Case-insensitive boolean values

- **GIVEN** `A2KIT_DEBUG=TRUE`
- **WHEN** `A2kitConfig()` is constructed
- **THEN** `cfg.debug` is `True`

### Requirement: No public freeze, lock, or env-bypass surface exists

a2kit SHALL NOT expose any documented public API that allows code to prevent env vars from overriding kwargs, freeze a field against future env changes, or otherwise lock a consumer-owned concern. This includes no `frozen=True` kwarg on `A2kitConfig`, no `bypass_env=True` mode, no "developer-pinned" sentinel. The recursive rule from ADR 0022 (consumer beats code at every link in the provider chain) is enforced by the absence of such an API, not by lint or runtime check.

#### Scenario: `frozen` kwarg has no lock effect

- **GIVEN** the env var `A2KIT_MCP__STRUCTURED_OUTPUT=true`
- **WHEN** code attempts `A2kitConfig(frozen=True, mcp=McpConfig(structured_output=False))`
- **THEN** the `frozen=True` kwarg is silently ignored (no `frozen` field exists on A2kitConfig)
- **AND** `cfg.mcp.structured_output` is `True` (env still wins)

#### Scenario: No bypass_env mode

- **WHEN** code searches the `a2kit.config` public surface for any symbol whose name contains "freeze", "lock", "bypass", or "pinned"
- **THEN** no such symbol exists

### Requirement: McpConfig.structured_output controls success-path wire shape

`A2kitConfig.mcp.structured_output: bool` SHALL default to `False`. When `False`, the MCP success path on a typed return SHALL emit BOTH `structuredContent` (full payload) AND `content[].text` (serialized JSON of the same payload), matching MCP 2025-06-18 backwards-compatibility guidance. When `True`, the MCP success path on a typed return SHALL emit `structuredContent` (full payload) AND `content[].text` set to a short, type-identifying marker only (no duplicate JSON payload).

The error path is unaffected by this setting and continues to emit prose in `content[].text` plus envelope in `structuredContent` per the typed-error contract (ADR 0021).

#### Scenario: Default (False) emits dual content on success

- **GIVEN** `App` constructed without explicit config and no `A2KIT_*` env vars set
- **WHEN** a tool returns a typed model successfully via MCP
- **THEN** `structuredContent` carries the full model dump
- **AND** `content[0].text` carries the serialized JSON of the same model dump

#### Scenario: Strict mode (True) emits marker content only on success

- **GIVEN** `A2KIT_MCP__STRUCTURED_OUTPUT=true` is set
- **WHEN** a tool returns a typed model successfully via MCP
- **THEN** `structuredContent` carries the full model dump
- **AND** `content[0].text` is a short marker (e.g., `"<ModelName>"`) and does NOT contain the serialized payload

#### Scenario: Error path is unchanged by this setting

- **GIVEN** `A2KIT_MCP__STRUCTURED_OUTPUT=true` is set
- **WHEN** a tool raises a declared `AppError`
- **THEN** `content[0].text` carries the prose error string per ADR 0021
- **AND** `structuredContent.error` carries the typed envelope per ADR 0021

### Requirement: App.user_config is an opaque developer-owned slot

`App` SHALL accept an optional `user_config` parameter of type `Any`, default `None`, and SHALL expose it as `app.user_config` and via the dispatch container as `container.app.user_config`. a2kit MUST NOT introspect, validate, merge, or env-override the contents of `user_config`. The slot is intended for the developer's own pydantic-settings instance, which the developer is expected to construct following the same env-beats-code pattern (ADR 0022 recursive rule).

#### Scenario: user_config passes through unchanged

- **GIVEN** a developer constructs `my_cfg = MyAppConfig(api_key="x")` and passes `App("name", user_config=my_cfg)`
- **WHEN** tool code reads `self.app.user_config`
- **THEN** the value is the same `my_cfg` instance

#### Scenario: user_config defaults to None

- **WHEN** `App("name")` is constructed with no `user_config`
- **THEN** `app.user_config` is `None`

#### Scenario: user_config is not merged into A2kitConfig

- **GIVEN** `App("name", user_config=MyAppConfig(api_key="x"))`
- **WHEN** code inspects `app.config` (A2kitConfig)
- **THEN** the user config fields are NOT present on `app.config`

### Requirement: A2kitConfig.debug is the canonical consumer-owned debug field

`A2kitConfig` SHALL expose a top-level `debug: bool = False` field. The field SHALL be settable via env var `A2KIT_DEBUG` (case-insensitive boolean parsing per pydantic-settings defaults), via `.env` file entry, or via `A2kitConfig(debug=True)` kwarg. Per ADR 0022's inverted source order, env wins over kwargs.

When `App` is constructed, `app.debug` SHALL reflect `app.config.debug`. External code that reads `app.debug` SHALL observe the consumer-resolved value, not whatever was passed to the (removed) `debug` kwarg.

#### Scenario: default debug is False

- **GIVEN** no `A2KIT_DEBUG` env var is set and no `.env` file with `A2KIT_DEBUG` exists
- **WHEN** `A2kitConfig()` is constructed
- **THEN** `cfg.debug` is `False`

#### Scenario: env sets debug

- **GIVEN** `A2KIT_DEBUG=true` in process env
- **WHEN** `A2kitConfig()` is constructed
- **THEN** `cfg.debug` is `True`

#### Scenario: env beats kwarg

- **GIVEN** `A2KIT_DEBUG=false` in process env
- **WHEN** `A2kitConfig(debug=True)` is constructed
- **THEN** `cfg.debug` is `False` (env wins per ADR 0022)

#### Scenario: app.debug attribute proxies app.config.debug

- **GIVEN** `A2KIT_DEBUG=true` in process env
- **WHEN** `a2kit.App("svc")` is constructed
- **THEN** `app.debug` is `True`
- **AND** `app.config.debug` is `True`

