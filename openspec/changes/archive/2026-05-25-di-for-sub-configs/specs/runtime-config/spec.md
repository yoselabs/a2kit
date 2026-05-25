## ADDED Requirements

### Requirement: A2kitConfig is exposed via DI in addition to App.config

The framework SHALL make `A2kitConfig` available both as the public
`App.config` attribute (for consumer introspection) and as a DI-resolved
dependency (for subsystem consumption). Subsystems and tool bodies SHALL
NOT walk `app.config.<sub>` attribute paths to obtain a sub-config;
they SHALL declare the typed dependency and let the container resolve
it.

#### Scenario: Subsystem prefers DI over attribute walk

- **GIVEN** the framework needs `LddConfig` inside `LddStateStage`
- **WHEN** the stage is constructed
- **THEN** `LddConfig` is supplied as a constructor argument resolved
  from the container
- **AND** the stage body MUST NOT read `app.config.ldd.<field>` at
  dispatch time

## MODIFIED Requirements

### Requirement: A2kitConfig.debug is the canonical consumer-owned debug field

`A2kitConfig` SHALL expose a top-level `debug: bool = False` field. The field SHALL be settable via env var `A2KIT_DEBUG` (case-insensitive boolean parsing per pydantic-settings defaults), via `.env` file entry, or via `A2kitConfig(debug=True)` kwarg. Per ADR 0022's inverted source order, env wins over kwargs.

The `App.debug` shortcut attribute has been removed. Consumer-side code SHALL read `app.config.debug`. Subsystem-side code SHALL resolve `A2kitConfig` via DI (typed dependency). Access to `app.debug` SHALL raise `AttributeError` with a migration hint naming both paths.

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

#### Scenario: App.debug access raises with migration hint

- **GIVEN** `a2kit.App("svc")` is constructed
- **WHEN** code reads `app.debug`
- **THEN** `AttributeError` is raised
- **AND** the message names `app.config.debug` as the consumer-side replacement
- **AND** the message names `A2kitConfig` DI as the subsystem-side replacement
