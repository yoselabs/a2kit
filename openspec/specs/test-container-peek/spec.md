# test-container-peek Specification

## Purpose
TBD - created by archiving change tool-return-type-discipline. Update Purpose after archive.
## Requirements
### Requirement: `a2kit.testing.peek(app, T)` resolves a type synchronously from the App's container

The library SHALL expose `a2kit.testing.peek(app, type_) -> Any` as a thin wrapper over `app.container().resolve_sync(type_)`. The function SHALL be documented as test-only in its docstring and surrounding documentation.

#### Scenario: peek resolves a registered singleton

- **GIVEN** `app.singleton(AppState, lambda: AppState(...))` registered
- **WHEN** test code calls `state = a2kit.testing.peek(app, AppState)`
- **THEN** `state` is the cached `AppState` instance and the call returned synchronously

#### Scenario: peek raises on async chain

- **GIVEN** an async-only provider chain for type `T`
- **WHEN** test code calls `a2kit.testing.peek(app, T)`
- **THEN** `SyncResolveUnavailable` is raised with the offending async link named (the same exception `Container.resolve_sync` raises)

#### Scenario: peek with no registered provider raises

- **GIVEN** no provider or singleton registered for type `T`
- **WHEN** test code calls `a2kit.testing.peek(app, T)`
- **THEN** the same exception that `Container.resolve_sync` raises for unregistered types is propagated unchanged

