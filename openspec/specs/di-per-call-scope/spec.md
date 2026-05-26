# di-per-call-scope Specification

## Purpose
TBD - created by archiving change di-scoped-lifecycle. Update Purpose after archive.
## Requirements
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

The dispatcher SHALL open a per-call child container scope around
each tool invocation via `Container.call_scope` (or
`container.child()` directly). Inside that scope, per-call typed
instances are published via the explicit `seed_scoped(type_, value)`
API on the child. The previous implicit "values in `wire_kwargs`
become SCOPED providers by type" behaviour is removed.

`wire_kwargs` is, again, a literal dict of named values passed
into `pre_hook` and matched by name to the target function's
parameters. It SHALL NOT trigger any DI side effects.

#### Scenario: Tool body resolves a SCOPED dep seeded via the explicit API

- **GIVEN** a tool body declaring `principal: Principal`
- **AND** a child container with `seed_scoped(Principal, p)` called
  before `call_scope` resolution
- **WHEN** the body is dispatched through `call_scope`
- **THEN** the body receives `p` as its `principal` kwarg

#### Scenario: wire_kwargs does NOT auto-seed by value type

- **GIVEN** `await container.call_scope(fn, {"opaque": SomeInstance()})`
  where `fn` declares no parameter named `opaque` and no parameter
  typed `SomeInstance`
- **WHEN** the scope opens
- **THEN** `SomeInstance` is NOT registered as a SCOPED provider on
  the child
- **AND** `child.has_provider(SomeInstance)` is `False`

#### Scenario: wire_kwargs named values still flow by parameter name

- **GIVEN** `await container.call_scope(fn, {"name": "alice"})` and
  `fn(self, *, name: str) -> ...`
- **WHEN** the scope opens and `merged` is yielded
- **THEN** `merged["name"] == "alice"`
- **AND** no DI registration was created for `str`

#### Scenario: Per-call cleanup runs after tool returns

- **GIVEN** `app.provide(Transaction, tx_factory, per_call=True)` where `tx_factory` is `@asynccontextmanager` and yields a transaction whose `finally` block commits
- **WHEN** a tool dispatches, the body runs to completion without raising
- **THEN** the transaction's `finally` block runs after the tool body completes and before the dispatch result is returned to the caller

#### Scenario: Per-call cleanup runs on tool exception

- **GIVEN** `app.provide(Transaction, tx_factory, per_call=True)` and a tool body that raises an exception
- **WHEN** the tool dispatches and raises
- **THEN** the transaction's `__aexit__` / generator `finally` runs with the exception in scope
- **AND** the exception is propagated to the caller after per-call cleanup completes

### Requirement: pre_hook contract: hooks receive an explicit seed callable

`pre_hook` SHALL have the signature
`Callable[[fn, wire_kwargs, seed], dict | Awaitable[dict]]`.
The third argument `seed` is a callable
`(type_: type, value: Any) -> None` that publishes a typed instance
on the child container as a SCOPED provider for the per-call scope.

Hooks that need to publish a typed result (e.g., a connection
instance derived from a connection-string wire value) MUST call
`seed(T, instance)` before returning the merged dict. Hooks that
have nothing to publish ignore the `seed` parameter.

#### Scenario: pre_hook publishes a typed instance via seed

- **GIVEN** a `pre_hook` that resolves `"conn_name"` into a
  `TrackerConn` instance
- **WHEN** the hook calls `seed(TrackerConn, resolved_conn)` and
  returns `{"connection": resolved_conn}`
- **THEN** `child.has_provider(TrackerConn)` is `True`
- **AND** a downstream factory declaring `conn: TrackerConn`
  receives `resolved_conn` from the child container

#### Scenario: pre_hook signature is enforced

- **GIVEN** a `pre_hook` callable accepting only two positional
  arguments
- **WHEN** the dispatcher invokes the hook with the new three-arg
  signature
- **THEN** a clear `TypeError` is raised at the call site naming the
  required signature

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

