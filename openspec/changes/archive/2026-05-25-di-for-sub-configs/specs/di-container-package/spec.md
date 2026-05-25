## ADDED Requirements

### Requirement: Framework-owned providers are seeded at App construction

`App.__init__` SHALL seed the DI container with framework-owned
providers before any user `app.provide(...)` call is accepted. The
framework-owned providers SHALL include the full set of config types
(`A2kitConfig` plus each registered sub-config type). User
registrations made via `app.provide(...)` SHALL win over framework
defaults, per the standard last-write-wins semantics of the container
(ADR 0006).

#### Scenario: User override of LddConfig replaces framework default

- **GIVEN** a fresh `App`
- **WHEN** the user calls `app.provide(LddConfig, lambda: custom)`
- **AND** the runtime is built
- **THEN** resolving `LddConfig` from the container returns `custom`
- **AND** does NOT return the App's `config.ldd`

#### Scenario: Framework providers are present even without user calls

- **GIVEN** a fresh `App` with no user `.provide(...)` calls
- **WHEN** the runtime is built and `A2kitConfig` is resolved
- **THEN** the container returns the App's `config` instance
