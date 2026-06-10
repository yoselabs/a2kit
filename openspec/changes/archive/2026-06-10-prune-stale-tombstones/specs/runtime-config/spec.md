## MODIFIED Requirements

### Requirement: A2kitConfig.debug is the canonical consumer-owned debug field

`A2kitConfig` SHALL expose a top-level `debug: bool = False` field. The field SHALL be settable via env var `A2KIT_DEBUG` (case-insensitive boolean parsing per pydantic-settings defaults), via `.env` file entry, or via `A2kitConfig(debug=True)` kwarg. Per ADR 0022's inverted source order, env wins over kwargs.

The `App.debug` shortcut attribute has been removed. Consumer-side code SHALL read `app.config.debug`. Subsystem-side code SHALL resolve `A2kitConfig` via DI (typed dependency). Access to `app.debug` SHALL raise the language-default `AttributeError`; the bespoke migration hint is swept under the tombstone sunset rule (`AGENTS.md` §1).

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

#### Scenario: app.debug access raises a plain AttributeError

- **GIVEN** `a2kit.App("svc")` is constructed
- **WHEN** code reads `app.debug`
- **THEN** the language-default `AttributeError` is raised
- **AND** no migration-hint message content is required (consumers read `app.config.debug`)
