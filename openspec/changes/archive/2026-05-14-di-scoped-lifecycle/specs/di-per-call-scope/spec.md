# di-per-call-scope delta

## ADDED Requirements

### Requirement: `app.provide(T, factory, per_call=True)` registers a per-call resource

The `App.provide(...)` method SHALL accept a keyword-only `per_call: bool = False` argument. When `per_call=True`, the registered type SHALL be resolved within a per-call scope opened by the dispatcher for each tool invocation. The factory SHALL be entered (constructed and `__aenter__`'d / generator-`yield`'d) on first resolution within a given call, cached for the rest of that call, and cleaned up when the call's scope closes. Across two different calls, the framework SHALL produce two distinct instances.

#### Scenario: per_call=True yields fresh instance per call

- **GIVEN** `app.provide(Transaction, tx_factory, per_call=True)` and a tool declaring `tx: Transaction`
- **WHEN** the tool is dispatched twice
- **THEN** `tx_factory` was invoked twice
- **AND** the `Transaction` instance from each dispatch is distinct (not the same object)

#### Scenario: per_call=True caches within a single call

- **GIVEN** `app.provide(Logger, logger_factory, per_call=True)` and a tool whose factory chain resolves `Logger` twice (e.g., a parent provider and a child provider both depend on `Logger`)
- **WHEN** the tool is dispatched once
- **THEN** `logger_factory` was invoked exactly once for this dispatch
- **AND** both consumers received the same `Logger` instance

#### Scenario: per_call default is False (app-scope)

- **GIVEN** `app.provide(SomeService)` (no per_call kwarg)
- **WHEN** the tool is dispatched twice and resolves `SomeService` each time
- **THEN** both dispatches receive the same `SomeService` instance
- **AND** the factory was invoked exactly once across the two dispatches

### Requirement: Dispatcher opens and closes a per-call scope around each tool invocation

For every tool dispatch, the framework SHALL create a fresh child container off the App's root container, resolve all tool parameters through the child container, invoke the tool body, and close the child container after the tool returns or raises. The child container SHALL contain its own cleanup stack for per-call resources. Closing the child container SHALL trigger LIFO cleanup of all per-call resources entered during the dispatch.

#### Scenario: Child container created per dispatch

- **WHEN** the dispatcher invokes a tool
- **THEN** a fresh child container is created via `app._resolver.child()`
- **AND** the tool's parameters are resolved through the child
- **AND** the child container is closed after the tool returns or raises

#### Scenario: Per-call cleanup runs after tool returns

- **GIVEN** `app.provide(Transaction, tx_factory, per_call=True)` where `tx_factory` is `@asynccontextmanager` and yields a transaction whose `finally` block commits
- **WHEN** a tool dispatches, the body runs to completion without raising
- **THEN** the transaction's `finally` block runs after the tool body completes and before the dispatch result is returned to the caller

#### Scenario: Per-call cleanup runs on tool exception

- **GIVEN** `app.provide(Transaction, tx_factory, per_call=True)` and a tool body that raises an exception
- **WHEN** the tool dispatches and raises
- **THEN** the transaction's `__aexit__` / generator `finally` runs with the exception in scope
- **AND** the exception is propagated to the caller after per-call cleanup completes

### Requirement: Per-call resource can depend on app-scope resource

A per-call factory's parameter annotations SHALL be resolved through the chain: first checking the per-call child container, then the App-scope root container. Per-call resources MAY depend on app-scope resources, but the reverse SHALL be rejected at App `__aenter__` (graph validation) with a `TypeError` naming the violating registration.

#### Scenario: Per-call Transaction depends on app-scope ConnectionPool

- **GIVEN** `app.provide(ConnectionPool)` (app-scope) and `app.provide(Transaction, tx_factory, per_call=True)` where `tx_factory(pool: ConnectionPool)` is declared
- **WHEN** a tool dispatches
- **THEN** the framework resolves `ConnectionPool` from the App-scope cache (entering it lazily on first dispatch)
- **AND** passes the resolved pool into `tx_factory` to construct the per-call `Transaction`

#### Scenario: App-scope cannot depend on per-call

- **GIVEN** `app.provide(Foo, foo_factory)` (app-scope, default) where `foo_factory(bar: Bar)` and `app.provide(Bar, bar_factory, per_call=True)`
- **WHEN** `async with app:` is entered
- **THEN** `TypeError` is raised
- **AND** the message names both `"Foo"` and `"Bar"` and the phrase `"app-scope depends on per-call"`

### Requirement: Per-call scope cleanup uses the cleanup stack contract

Per-call scope cleanup SHALL use the same per-resource exception-isolation rules as App-scope cleanup (see `di-scope-cleanup-stack`): individual `__aexit__` or generator `finally` failures are logged at WARN and unwinding continues; the original tool exception (if any) is preserved as the propagated exception.

#### Scenario: Bad per-call cleanup does not poison the dispatch

- **GIVEN** three per-call resources entered during a dispatch: `A` (well-behaved cleanup), `B` (raises in cleanup), `C` (well-behaved cleanup)
- **WHEN** the tool body returns normally and per-call scope closes
- **THEN** `C`'s cleanup runs, `B`'s cleanup raises and is logged at WARN, `A`'s cleanup runs
- **AND** the dispatch returns the tool's result without raising
