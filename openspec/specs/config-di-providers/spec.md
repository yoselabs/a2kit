# config-di-providers Specification

## Purpose
TBD - created by archiving change di-for-sub-configs. Update Purpose after archive.
## Requirements
### Requirement: A2kitConfig is registered as a DI provider

`App.__init__` SHALL register `A2kitConfig` as a singleton provider in
the DI container so that any tool or subsystem can declare
`config: A2kitConfig` as a typed dependency and receive the App's
configuration instance. The provider SHALL return the same
`A2kitConfig` instance that is exposed via the public `App.config`
attribute.

#### Scenario: Subsystem resolves A2kitConfig via DI

- **GIVEN** an `App` constructed with `A2kitConfig(debug=True)`
- **WHEN** a tool body declares a parameter `cfg: A2kitConfig` and the
  tool is dispatched
- **THEN** `cfg.debug` is `True`
- **AND** `cfg is app.config` evaluates to `True`

### Requirement: Each A2kitConfig sub-model is registered as a DI provider

`App.__init__` SHALL register each sub-model of `A2kitConfig` (`McpConfig`,
`LogConfig`, `HttpConfig`, `CliConfig`, and any future sub-model) as a
singleton provider that resolves to the corresponding attribute on the
App's `A2kitConfig` instance. A subsystem MAY declare its narrowest
config type as a dependency and receive only that sub-model.

#### Scenario: CallScopeStage receives LogConfig

- **GIVEN** an `App` constructed with `A2kitConfig(log=LogConfig(level="debug"))`
- **WHEN** the dispatch pipeline resolves `LogConfig` from the container
- **THEN** the resolved instance is `app.config.log`
- **AND** the instance's `.level` field is `"debug"`

#### Scenario: McpConfig resolution returns the same instance as A2kitConfig.mcp

- **GIVEN** an `App` whose config has `mcp.structured_output=True`
- **WHEN** code resolves `McpConfig` from the container
- **AND** code reads `app.config.mcp`
- **THEN** both refer to the same object (identity, not just equality)

### Requirement: Test override is rebind on a fresh App

Per ADR 0006 (no override seam), config overrides for tests SHALL be
performed by constructing a fresh `App` with the desired `A2kitConfig`
or by calling `app.provide(LogConfig, fake_log_config)` before the App
is built into a runtime. Direct mutation of `app.config.*` after build
is unsupported and SHALL NOT be relied upon by tests.

#### Scenario: Test rebinds LogConfig before build

- **GIVEN** a fresh `App` instance and a fake `LogConfig`
- **WHEN** the test calls `app.provide(LogConfig, lambda: fake)` then
  builds the runtime
- **THEN** the dispatch pipeline resolves the fake `LogConfig` instead
  of the default

