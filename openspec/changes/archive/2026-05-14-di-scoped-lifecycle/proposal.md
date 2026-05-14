# di-scoped-lifecycle

## Why

The current DI surface (`app.singleton(T, factory)` + `app.provide(T, factory)`) ships **eager singleton entry at App start**, **three-protocol cleanup auto-detection** (`__aexit__`/`aclose`/`close`), **no per-call scope** (blocks transactions and per-operation resources), and a **parameterized-lambda footgun** (lambdas with annotated params are unusable because Python lambda syntax forbids parameter annotations). Adding `__aenter__` to a resource forces it to warm at App start regardless of whether any tool uses it (concrete a2web case: BrowserPool + LlmExtractorResource warm Chromium and load an LLM client at every App start even when the invoked tool needs neither). A long brainstorm round plus three research passes (cross-language DI survey, HN/Reddit sentiment, dishka deep-dive, service-locator academic check) converged on a redesigned shape that is lazy, scoped, AsyncExitStack-bug-isolated, and decoupled from a2kit's framework code via a shippable standalone package.

## What Changes

- **BREAKING** Rename `app.singleton(...)` and `app.provide(...)` into a unified `app.provide(T, factory=None, *, per_call=False)`. App-scope (singleton) is the default; `per_call=True` opts into per-call scope. Old names raise `TypeError` with migration hints (per CLAUDE.md no-shims principle).
- **BREAKING** Replace eager-at-`App.__aenter__` singleton entry with **lazy first-use resolution**. Resources are entered when a dispatch first resolves them, cached per declared scope.
- **BREAKING** Collapse cleanup protocol detection from three (`__aexit__`/`aclose`/`close`) to one. Lifecycle is expressed via standard Python idioms: class implements `__aenter__`/`__aexit__`, OR factory is an `@asynccontextmanager` generator. The framework SHALL NOT detect `aclose`/`close` methods.
- **BREAKING** Remove the hand-rolled "lazy-init resource with internal `asyncio.Lock` and `_ensure()` accessor" pattern from supported surface. The pattern is replaced by class `__aenter__`/`__aexit__` with framework-managed lock-coalesce on first touch.
- Add **per-call scope** (`per_call=True` on `provide`). The dispatcher opens a fresh child container per tool invocation; per-call resources are constructed at first resolution within the call, cleaned up when the call returns or raises.
- Add **`Lazy[T]`** type alias (`Callable[[], Awaitable[T]]`) recognized by the dispatcher as a deferred-resolution annotation. Tools declare `dep: Lazy[BrowserPool]` to receive a resolver closure they invoke only when actually needed. Honors `T`'s registered scope (singleton stays singleton).
- Add **custom per-scope cleanup stack** that records `(resource, aclose-callable)` tuples and unwinds in reverse insertion order with per-resource `try/except WARN-log + continue` isolation. Does **not** use stdlib `AsyncExitStack` (cpython #137517 and MCP SDK #1213 background-task exception propagation bugs).
- Add **`Resolver` protocol** in `a2kit.packages.di`. a2kit framework modules access the container only via this protocol. Framework internals (dispatcher, LDD sinks, MCP transport) construct plainly and do not register themselves through user DI.
- Expand the `a2kit.packages.di` public surface for **standalone reuse**: `Container`, `Scope` enum (`SINGLETON`, `SCOPED`, `TRANSIENT`), `Resolver` protocol, async `Container.get(T)`, `Container.child()` for scoped sub-containers, `async with` lifecycle. Surface remains feature-agnostic (no a2kit concepts in container code).
- Auto-resolve `pydantic_settings.BaseSettings` subclasses without explicit registration. `BaseSettings.()` reads env at zero-arg construction; the container treats this as the canonical config injection path.
- **REMOVED** `app.singleton(...)` method on `App` (raises `TypeError` with migration hint to `app.provide(...)`).
- **REMOVED** `singleton` factory-shape async kwarg differentiation. All factories may be sync or async uniformly; container introspects at registration.
- **REMOVED** the `@on_shutdown` requirement for resource cleanup. Cleanup runs via the resource's `__aexit__` / generator-yield `finally` block on scope close.
- **REMOVED** per-method `_ensure()` calls inside resource classes. Lint rule SHALL flag them.
- No new `app.warm()`, no `app.override(T, factory)`, no `ctx.get(T)`. Test overrides happen via composition-root re-registration with last-write-wins semantics; the same `app.provide(...)` mechanism handles both production registration and test stubbing.

## Capabilities

### New Capabilities

- `di-conditional-injection`: `Lazy[T]` annotation convention for deferred dependency resolution honoring registered scope. Spec covers dispatcher recognition of `Callable[[], Awaitable[T]]` / `Lazy[T]` annotations, closure semantics (binding to current scope at call site), and scope-cache interaction (Lazy returns cached instance for app-scope, fresh instance for per-call).
- `di-per-call-scope`: Per-call (operation-scoped) DI tier. Spec covers dispatcher opening a fresh child container per tool invocation, `per_call=True` kwarg on `app.provide`, lifecycle (factory entered on first resolution within the call, cleaned up on call return/raise), and the canonical pattern for transactions (`app.provide(Transaction, tx_factory, per_call=True)`).
- `di-scope-cleanup-stack`: Custom per-scope async-resource cleanup stack. Spec covers recording `(resource, aclose)` tuples in insertion order, LIFO unwind on scope close, per-resource exception isolation (WARN-log + continue, no sibling poisoning), explicit non-use of stdlib `AsyncExitStack`, and the regression contract for cpython #137517 / MCP SDK #1213 class of failures.

### Modified Capabilities

- `app-singletons`: Rename `singleton(T, factory)` to `provide(T, factory, per_call=False)`. Remove eager-at-start entry. App-scope becomes the default scope of the unified `provide`; semantics shift from "cached on App, sync resolve" to "cached on App, lazy first-touch with lock-coalesce, async-or-sync factory". Old `singleton` raises `TypeError` with migration hint.
- `request-scoped-di`: Subsume the per-dispatch `provide(T, sync_factory)` shape into the unified `provide(T, factory, per_call=True)`. Remove the sync-only restriction (async factories now allowed on per-call). Container resolution remains type-keyed and parameter-annotation-driven. Add child-container creation per dispatch; per-call resources live in the child.
- `lazy-init-resources`: Replace the dual-pattern (async-factory primary, hand-rolled `_ensure` escape hatch) with a single convention: class `__aenter__`/`__aexit__` OR `@asynccontextmanager` factory. Remove the `_ensure` escape hatch entirely (lint rule flags). State fields stay non-Optional (carryover). Cleanup moves from `@on_shutdown` to the scope's cleanup stack via the resource's own protocol.
- `di-container-package`: Expand public surface to include `Scope` enum, `Resolver` protocol, async `get`/`child` methods, `async with` lifecycle. Container remains feature-agnostic. Package gains the explicit goal of being **shippable as a standalone library** with zero a2kit imports inside the package; a2kit depends on it like any other library.
- `app-lifecycle`: Remove eager-at-`__aenter__` singleton warmup. App start does container construction + settings auto-resolution only. Per-scope cleanup stacks unwind on App / per-call scope exit. Document scope hierarchy as `app > per-call` (two tiers; routers do not have an independent scope).

## Impact

- **`src/a2kit/app.py`**: `singleton` removed, `provide` reshaped with `per_call=` kwarg. `App.__aenter__` no longer warms singletons.
- **`src/a2kit/packages/di/`**: `Container` gains async `get`/`child` methods, `Scope` enum, `Resolver` protocol. Custom cleanup stack replaces topological-teardown machinery. Surface becomes standalone-shippable (separate `pyproject.toml` or namespace package later).
- **`src/a2kit/dispatch/`**: Dispatcher opens a per-call child container per tool invocation, resolves params (including `Lazy[T]`) from it, unwinds on return.
- **`src/a2kit/lint/`**: New static check for `_ensure()` method patterns and parameterized-lambda factories.
- **All consumers using `app.singleton(...)`**: rename to `app.provide(...)`. Loud-crash `TypeError` at first instantiation with migration hint.
- **All consumers using `@on_shutdown` for resource cleanup**: cleanup moves to the resource's `__aexit__` or factory `finally`.
- **All resources using the `_ensure()` lazy-init pattern**: refactor to `__aenter__`/`__aexit__` on the class, or wrap in `@asynccontextmanager` factory.
- **`a2web` (the canonical consumer)**: SqliteResource, BrowserPool, LlmExtractorResource migrate to class-as-async-context-manager. Tools using conditional resources (e.g., extract-with-mode) declare `Lazy[BrowserPool]` / `Lazy[LlmExtractor]`.
- **Test harnesses**: Move from `_snapshot()`/`_restore()` test-only container hooks to composition-root re-registration via override modules in `build_test_app()` factory.
- **Out of scope** (deferred to separate proposals): FastAPI compat shim (`compat-fastapi`), universal-server-SDK transport adapters (`transport-adapters`), standalone DI package name and PyPI publish workflow.
