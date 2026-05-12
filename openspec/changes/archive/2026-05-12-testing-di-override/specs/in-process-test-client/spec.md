## ADDED Requirements

### Requirement: TestClient.override swaps DI-resolved dependencies for the session

The test client SHALL expose `override(type_: type[T], fake: T) -> None` on the `TestClient` instance returned by `a2kit.testing.client(app)`. The method SHALL replace the App container's binding for `type_` with `fake` for the remainder of the `async with` block, restoring the prior binding on `__aexit__` (including exceptional exit).

The signature SHALL be type-parameterised by a `TypeVar` such that mypy / pyright / ty bind `fake` to the same `T` as `type_`. Callers SHALL NOT need `# type: ignore` to swap a fake that satisfies the registered type.

Overrides SHALL cover both DI registration paths:
- types registered via `app.singleton(T, ...)` (cached singletons),
- types registered via `app.provide(T, ...)` (per-call providers).

Overrides SHALL also apply when `type_` was not previously registered (the fake is registered fresh for the duration of the session).

Calling `override` more than once for the same `type_` within one session SHALL apply last-write-wins; only one restore happens at exit (to the pre-session state, not to intermediate values).

#### Scenario: Override replaces a singleton-registered dependency

- **GIVEN** an App with `app.singleton(LLMExtractor, lambda: RealLLM())` and a tool that takes `extractor: LLMExtractor`
- **WHEN** test code runs `async with a2kit.testing.client(app) as c:` then `c.override(LLMExtractor, FakeLLM())` then `await c.invoke("foo")`
- **THEN** the tool body receives the `FakeLLM` instance, and `a2kit.testing.peek(app, LLMExtractor)` inside the block also returns the same `FakeLLM`

#### Scenario: Override replaces a per-call provider-registered dependency

- **GIVEN** an App with `app.provide(Store, build_store)` and a tool that takes `store: Store`
- **WHEN** test code calls `c.override(Store, FakeStore())` inside the `async with` block and then `await c.invoke("foo")` multiple times
- **THEN** every invocation receives the same `FakeStore` instance the test passed in (the provider is shadowed by a constant-factory for the duration of the override)

#### Scenario: Override is restored on normal exit

- **GIVEN** `a2kit.testing.peek(app, LLMExtractor)` returns `RealLLM` before any `async with` block
- **WHEN** a test enters `async with a2kit.testing.client(app) as c:`, calls `c.override(LLMExtractor, FakeLLM())`, and the block exits normally
- **THEN** after the block, `a2kit.testing.peek(app, LLMExtractor)` returns the original `RealLLM` instance (or re-resolves the original singleton factory if it had not been materialised)

#### Scenario: Override is restored on exceptional exit

- **WHEN** a test enters the `async with` block, calls `c.override(T, fake)`, and the block exits due to an exception raised inside `c.invoke(...)`
- **THEN** the App's container is restored to its pre-session state, identical to a normal exit

#### Scenario: Override of an unregistered type registers the fake fresh for the session

- **GIVEN** no provider or singleton registered for type `T`
- **WHEN** test code calls `c.override(T, fake)` and then a tool depending on `T` is invoked
- **THEN** the tool receives `fake`, and on `__aexit__` the container no longer has any registration for `T` (returns to the pre-session state where `T` was unknown)

#### Scenario: Last-write-wins within a session

- **WHEN** test code calls `c.override(T, fake1)` then `c.override(T, fake2)` within one session
- **THEN** subsequent resolutions return `fake2`, and on exit the container is restored to its pre-session state (not to `fake1`)

#### Scenario: Type-safety at the call site

- **WHEN** a test author writes `c.override(LLMExtractor, "not an extractor")`
- **THEN** mypy / pyright / ty reports an argument-type error on the second argument without any `# type: ignore` being involved

#### Scenario: Concurrent override sessions on the same App are rejected

- **GIVEN** TestClient `c1` is inside an `async with` block on `app` and has called `c1.override(T, fake)`
- **WHEN** a second TestClient `c2` enters `async with a2kit.testing.client(app) as c2:` and calls `c2.override(T, other_fake)`
- **THEN** `c2.override(...)` raises `RuntimeError` indicating an override session is already active on this App
