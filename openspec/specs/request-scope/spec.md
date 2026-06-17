# request-scope Specification

## Purpose
Single typed substrate-to-dispatch bridge for per-request values
(Principal, per-request DI Container, log state, future TenantId /
TraceContext / RequestId). Replaces per-type ContextVar bridges with a
uniform shape and a typed `RequestScopeMissing(T)` failure surface.

## Requirements

### Requirement: `request_scope` is the single typed substrate↔dispatch bridge

a2kit SHALL provide a module `a2kit.packages.context.request_scope` (re-exported at `a2kit.packages.dispatch.request_scope`) exposing five callables: `publish`, `get`, `try_get`, `all_seeds`, `reset`, plus the exception class `RequestScopeMissing`. The module SHALL carry exactly one `ContextVar` (module-private, not re-exported through any `__all__`). All request-scoped values traveling from substrate boundary code to dispatch stages SHALL travel through this bridge — per-type `_<x>_bridge.py` modules and per-value ContextVars SHALL be retired (or kept only as deprecation shims for one release).

#### Scenario: Bridge module exposes exactly the documented surface

- **WHEN** code does `from a2kit.packages.context import request_scope`
- **THEN** `request_scope.__all__` contains `publish`, `get`, `try_get`, `all_seeds`, `reset`, and `RequestScopeMissing`
- **AND** no `ContextVar` instance is reachable through `request_scope.__dict__` except the module-private one (name starts with `_`, not in `__all__`)

### Requirement: `publish(*values)` writes typed seeds; `reset(token)` clears them atomically

`publish(*values: object) -> ScopeToken` SHALL accept one or more values and register each by its `type(value)` as a typed seed in the current request scope. The call returns one opaque token that `reset(token)` SHALL use to clear EVERY seed the call added. When two values of the same type are published in the same scope (across one or several `publish` calls), the most-recently-published value wins (matches `Container.provide` semantics).

#### Scenario: Variadic publish + atomic reset

- **GIVEN** an open request scope
- **WHEN** `token = publish(principal, call_scope, container)`
- **THEN** `get(Principal)`, `get(_CallScope)`, and `get(Container)` each return the corresponding value
- **WHEN** `reset(token)` runs
- **THEN** subsequent `get(...)` for each of those types raises `RequestScopeMissing`

#### Scenario: Last publish wins on type collision

- **GIVEN** `publish(Principal(name="a"))` then `publish(Principal(name="b"))`
- **WHEN** `get(Principal)` runs
- **THEN** the returned principal's name is `"b"`

### Requirement: `get(T)` raises a precise `RequestScopeMissing(T)` when the seed is absent

`get(t: type[T]) -> T` SHALL return the published value of type `t` from the current scope. When no value of type `t` is published in the current scope (or no scope is open), `get` SHALL raise `RequestScopeMissing(t)`. The exception SHALL carry `requested_type` as an attribute AND its message SHALL name `t.__name__` AND SHALL include a hint to check substrate middleware order. `try_get(t)` SHALL return `None` instead of raising.

#### Scenario: get with no scope raises with type info

- **GIVEN** no request scope active (e.g., test code outside any transport)
- **WHEN** `get(Principal)` runs
- **THEN** `RequestScopeMissing` is raised
- **AND** the exception's `requested_type` attribute is `Principal`
- **AND** the message contains `'Principal'` and a hint about substrate middleware

#### Scenario: try_get returns None instead of raising

- **GIVEN** no request scope active
- **WHEN** `try_get(Principal)` runs
- **THEN** the result is `None`
- **AND** no exception is raised

### Requirement: `all_seeds()` returns a snapshot for `Container.call_scope` integration

`all_seeds() -> dict[type, object]` SHALL return a copy of the current scope's published seeds. Mutating the returned dict SHALL NOT mutate the scope. `Container.call_scope` SHALL accept `framework_seeds=request_scope.all_seeds()` (the `framework_seeds` parameter renames the prior `scoped_seeds` and the old name becomes a deprecation shim).

#### Scenario: all_seeds is a defensive copy

- **GIVEN** `publish(principal, call_scope)`
- **WHEN** `seeds = all_seeds(); seeds.clear()`
- **THEN** subsequent `get(Principal)` and `get(_CallScope)` still succeed

### Requirement: Concurrent request scopes are isolated

Two concurrent tasks (or threads, where applicable) running their own request scopes SHALL see only their own published values. A value published in task A SHALL NOT be visible to task B's `get(T)`.

#### Scenario: Concurrent scope isolation

- **GIVEN** task A publishes `Principal(name="a")` and task B publishes `Principal(name="b")` in concurrent `asyncio.create_task` coroutines
- **WHEN** each task calls `get(Principal)`
- **THEN** task A sees `"a"`, task B sees `"b"`
- **AND** neither task observes the other's publish
