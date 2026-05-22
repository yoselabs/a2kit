## MODIFIED Requirements

### Requirement: `a2kit.testing.peek(app, T)` resolves a type synchronously from the App's container

The library SHALL expose `a2kit.testing.peek(app, type_) -> Any` as a synchronous test seam over `app.container().get(type_)`. When called outside an event loop, `peek` SHALL drive `Container.get` via `asyncio.run`. When called inside a running loop, `peek` SHALL return the already-cached app-scope instance and SHALL raise `LookupError` if none is cached. The function SHALL be documented as test-only in its docstring and surrounding documentation.

#### Scenario: peek resolves a registered singleton

- **GIVEN** `app.provide(AppState, lambda: AppState(...))` registered
- **WHEN** test code calls `state = a2kit.testing.peek(app, AppState)` from a synchronous test body
- **THEN** `state` is the resolved `AppState` instance and the call returned synchronously

#### Scenario: peek inside an event loop with no cached instance raises

- **GIVEN** a type `T` that no tool dispatch has resolved yet
- **WHEN** test code calls `a2kit.testing.peek(app, T)` from inside a running event loop
- **THEN** `LookupError` is raised, directing the caller to `await app.container().get(T)` instead

#### Scenario: peek with no registered provider raises

- **GIVEN** no provider registered for type `T`
- **WHEN** test code calls `a2kit.testing.peek(app, T)`
- **THEN** the same exception that `Container.get` raises for unregistered types is propagated unchanged
