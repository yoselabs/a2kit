# di-conditional-injection Specification

## Purpose
TBD - created by archiving change di-scoped-lifecycle. Update Purpose after archive.
## Requirements
### Requirement: `Lazy[T]` is a type alias for deferred resolution

The framework SHALL expose `a2kit.Lazy` as a generic type alias equivalent to `Callable[[], Awaitable[T]]`. Tool and factory parameters annotated `Lazy[T]` (or the unaliased `Callable[[], Awaitable[T]]` form) SHALL be recognized by the dispatcher as deferred-resolution requests for type `T`. The framework SHALL inject a closure that, when awaited, resolves `T` in the current scope and returns the resolved instance. The closure SHALL be a regular awaitable callable; consumers MAY call it zero, one, or many times within the same tool body.

#### Scenario: Lazy[T] alias is importable

- **WHEN** a consumer writes `from a2kit import Lazy`
- **THEN** the import succeeds
- **AND** `Lazy[BrowserPool]` is equivalent to `Callable[[], Awaitable[BrowserPool]]` for type-checker purposes

#### Scenario: Tool body declaring Lazy[T] receives a callable

- **GIVEN** `app.provide(BrowserPool)` is registered and a tool declares `browser: Lazy[BrowserPool]`
- **WHEN** the tool is dispatched
- **THEN** the value bound to `browser` is callable
- **AND** awaiting `browser()` returns a `BrowserPool` instance
- **AND** the value bound to `browser` is not itself a `BrowserPool` instance

#### Scenario: Lazy[T] closure never invoked — resource never resolved

- **GIVEN** `app.provide(BrowserPool)` is registered (app-scope, lazy) and a tool declares `browser: Lazy[BrowserPool]` but the tool body never calls `browser()`
- **WHEN** the tool is dispatched
- **THEN** `BrowserPool`'s factory or `__aenter__` is not invoked
- **AND** no cleanup is registered for the resource

### Requirement: `Lazy[T]` honors registered scope

The closure injected for a `Lazy[T]` parameter SHALL resolve `T` through the same container path as direct injection would. App-scope (`per_call=False`) resources resolved via `Lazy[T]` SHALL share the App-scope cache: the first invocation across all calls enters the resource, and subsequent invocations across all calls return the cached instance. Per-call (`per_call=True`) resources resolved via `Lazy[T]` SHALL share the per-call cache: the first invocation within a given dispatch enters the resource, subsequent invocations within the same dispatch return the same instance, and a fresh instance is created in a subsequent dispatch.

#### Scenario: Lazy[T] of app-scope returns cached instance across calls

- **GIVEN** `app.provide(BrowserPool)` (app-scope, lazy)
- **WHEN** tool A dispatches and calls `await browser()` (where `browser: Lazy[BrowserPool]`), and later tool B dispatches and calls `await browser()`
- **THEN** both calls return the same `BrowserPool` instance
- **AND** `BrowserPool.__aenter__` was invoked exactly once

#### Scenario: Lazy[T] called twice within one tool returns same instance

- **GIVEN** `app.provide(BrowserPool)` (app-scope) and a tool that does `bp1 = await browser(); bp2 = await browser()`
- **WHEN** the tool is dispatched
- **THEN** `bp1 is bp2`
- **AND** `BrowserPool.__aenter__` was invoked exactly once across the two calls

#### Scenario: Lazy[T] of per-call type returns same instance within call, fresh across calls

- **GIVEN** `app.provide(Transaction, tx_factory, per_call=True)` and a tool declaring `tx: Lazy[Transaction]` that calls `await tx()` twice
- **WHEN** the tool is dispatched twice
- **THEN** within each dispatch the two `await tx()` invocations return the same `Transaction` instance
- **AND** across the two dispatches the returned `Transaction` instances are not the same object
- **AND** `tx_factory` was invoked exactly twice (once per dispatch)

### Requirement: `Lazy[T]` participates in cleanup like direct injection

A resource resolved through a `Lazy[T]` closure SHALL be registered on the same scope's cleanup stack as if it had been resolved through a directly-injected parameter. App-scope resources resolved lazily SHALL be cleaned up at App `__aexit__`. Per-call resources resolved lazily SHALL be cleaned up at the per-call scope's exit (tool return or raise).

#### Scenario: Lazy-resolved app-scope resource cleaned up at App exit

- **GIVEN** `app.provide(BrowserPool)` (app-scope) where `BrowserPool` implements `__aenter__`/`__aexit__`, and a tool that resolves it via `await browser()` where `browser: Lazy[BrowserPool]`
- **WHEN** the tool dispatches once, then the App exits via `async with app:` block close
- **THEN** `BrowserPool.__aexit__` is invoked exactly once during App close

#### Scenario: Lazy-resolved per-call resource cleaned up at call exit

- **GIVEN** `app.provide(Transaction, tx_factory, per_call=True)` and a tool that resolves it via `await tx()` where `tx: Lazy[Transaction]`
- **WHEN** the tool is dispatched and returns normally
- **THEN** the per-call scope's cleanup stack runs the transaction's `__aexit__` / generator-yield `finally` before the dispatch result is returned to the caller

### Requirement: Unannotated lazy parameters raise at registration

When a tool or factory declares a parameter whose annotation cannot be resolved (e.g., `Callable[[], Awaitable[T]]` where `T` has no registered provider and is not auto-resolvable as a `BaseSettings` subclass), the framework SHALL raise `TypeError` at App `__aenter__` time (graph validation), naming the tool and the parameter and the unresolvable inner type.

#### Scenario: Lazy of unregistered type fails at graph validation

- **GIVEN** a tool declares `dep: Lazy[UnregisteredType]` and no provider for `UnregisteredType` is registered
- **WHEN** `async with app:` is entered
- **THEN** `TypeError` is raised
- **AND** the message names the tool name, the parameter `"dep"`, and the type `"UnregisteredType"`

