## ADDED Requirements

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
