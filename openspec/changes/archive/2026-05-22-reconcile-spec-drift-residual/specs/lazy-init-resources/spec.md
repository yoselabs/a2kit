# lazy-init-resources Specification

## MODIFIED Requirements

### Requirement: No framework primitive for the pattern

Neither the class-as-async-context-manager path nor the `@asynccontextmanager` factory path SHALL be shipped as a framework-specific base class, mixin, or decorator inside `a2kit`. The framework SHALL NOT introduce a dedicated async-resource decorator, a lazy-resource decorator, or any base/mixin/decorator sibling for the pattern. The framework provides the surface (`app.provide(T, factory)`, scope-aware cleanup stacks, lock-coalesced first-touch); the lifecycle is expressed via standard Python protocols.

A provided resource is constructed on first resolution, not at registration time. The lazy-first-use behavior is built into `app.provide(T, factory)` — there is no separate decorator that opts a resource into laziness.

#### Scenario: No async-resource or lazy-resource decorator

- **WHEN** an app needs an async-opened resource
- **THEN** the only supported path is `app.provide(SqliteResource)` with `__aenter__` / `__aexit__` on the class, or `app.provide(SqliteResource, factory)` with an `@asynccontextmanager` factory
- **AND** `App` exposes no decorator that wraps a resource for async or lazy initialization

#### Scenario: Lazy first-use is built into app.provide

- **GIVEN** a resource registered via `app.provide(SqliteResource)`
- **WHEN** the App is composed but no tool has yet resolved `SqliteResource`
- **THEN** the resource is not constructed at registration time
- **AND** the first dispatch resolving `SqliteResource` constructs it and enters its `__aenter__` exactly once
