# Design: di-scoped-lifecycle

## Context

The a2kit framework currently ships a custom synchronous DI container (`a2kit.packages.di`) plus an `App` wrapper that exposes `singleton(T, factory)` (cached, eager-warmed at App start, supports async factories) and `provide(T, factory)` (fresh per dispatch, sync-only). Lifecycle cleanup is auto-detected via three protocols: `__aexit__`, `aclose`, `close`. There is no per-call scope distinct from per-dispatch `provide`, and there is no first-class way for a tool to declare a dependency it might or might not use within a single call.

Concrete pain points that motivate this redesign, from a long brainstorm + three research passes:

- **a2web case**: adding `__aenter__` to `BrowserPool` and `LlmExtractorResource` (to make them DI-friendly) forces eager warm at every App start, even for tools that never touch them. Today's workaround is the `_ensure()` pattern with per-method locks, which is explicitly tagged as an escape hatch in `lazy-init-resources` but in practice has become the default because the alternative (eager singleton) is worse for CLI/dev workflows.
- **No per-call scope**: there is no clean way to declare a `Transaction` that is fresh per tool call, auto-committed on success, auto-rolled-back on exception. `provide` resolves per dispatch but is sync-only; `singleton` is cached across calls.
- **Conditional resource use**: a tool that takes five resources but only uses one based on `mode` argument pays full resolution cost on every call.
- **AsyncExitStack footguns**: the cleanup machinery is at risk of cpython #137517 and MCP SDK #1213 if it adopts stdlib `AsyncExitStack`. Custom unwind is safer.
- **DI vocabulary alienates**: words like "singleton," "scope," "warm," "eager" repel FastAPI/FastMCP users who picked those frameworks for the lightweight feel.

Research validated three external truths that constrain the design:

- **dishka** is the closest off-the-shelf match (lazy + scoped + async-cm factories + type-keyed) but does not fit: its plugin model wants providers at `make_container()` time (a2kit's plugin model is `register(app)` at runtime); its error messages don't carry migration hints (CLAUDE.md principle #4); test overrides were explicitly rejected in dishka issue #275 with no orthogonal alternative.
- **Mark Seemann's strict service-locator stance** condemns `ctx.get(T)`-style APIs (hidden dependencies, runtime errors instead of compile-time). The pragmatic middle (Fowler, Hynek) carves out "framework boundary objects" as acceptable, but lands on **declared `Lazy[T]` / `Provider[T]` injection as the better default**.
- **In-place test override APIs** (FastAPI `dependency_overrides` dict, Spring `@MockBean`) are documented footguns (cache invalidation, async state leak between tests). The 2024-2026 consensus is **per-test composition via factory pattern** (`build_test_app(overrides=...)`) — ASP.NET `WebApplicationFactory`, Seemann, dishka all align.

The conversation that produced this design is summarized in the project memory at `~/Documents/Knowledge/Agents/Claude/project_a2kit_di_design.md`.

## Goals / Non-Goals

**Goals:**

- Two scope tiers, lazy by default: app-singleton (default) + per-call (`per_call=True`). No router scope, no operation-as-user-term, no transient.
- Single cleanup protocol convention: class implements `__aenter__`/`__aexit__`, OR factory is `@asynccontextmanager`. Drop `aclose`/`close` auto-detection.
- Per-call DI scope unblocks transactions, audit context, OTEL spans, per-call HTTP clients.
- `Lazy[T]` annotation enables conditional resource use without service-locator API.
- Cleanup stack isolated from cpython #137517 / MCP SDK #1213 class of `AsyncExitStack` bugs.
- a2kit framework internals decoupled from container via narrow `Resolver` protocol; framework does not register itself through user DI.
- DI package self-contained at `a2kit.packages.di`, shippable as a standalone library (no a2kit imports inside).
- Five user-facing concepts at first contact: `register(app)`, `app.provide(...)`, typed tool params, `BaseSettings`, `Lazy[T]`.
- Test overrides via composition-root re-registration; no new API.
- Migration crashes loudly with hints (CLAUDE.md principle #4).

**Non-Goals:**

- No FastAPI compat layer in this change. Deferred to `compat-fastapi` (separate proposal).
- No universal-server-SDK transport adapters. Deferred to `transport-adapters` (separate proposal).
- No `app.warm(...)` API. The two-line alternative (`await app._resolver.get(T)` between `async with app` and `serve_all`) is sufficient.
- No `app.override(T, factory)` API. Composition-root re-registration suffices.
- No `ctx.get(T)` service-locator escape hatch in v1. Reconsider if a real dynamic-type case emerges.
- No router scope, no transient scope, no `Scope.SCOPED`-but-not-per-call distinction in user-facing API. Standalone package may expose `TRANSIENT` for completeness but a2kit's wrapper does not surface it.
- No pluggable DI engine ("swap container library"). Frameworks own DI as integrated; we expose a `Resolver` protocol for internal decoupling, not as a replaceability contract.
- No standalone-package PyPI publish workflow in this change. Package structure is set up to allow it later.
- No `Lazy[T]` lint rule that *rewrites* code. Lint may *suggest* `Lazy[T]` for conditionally-used parameters but never mutates source.

## Decisions

### D1: Two scope tiers (app + per-call), kwarg-driven, not enum-string-driven

User-facing API: `app.provide(T, factory=None, *, per_call=False)`. Default scope is app-singleton. `per_call=True` opts into per-call.

**Rationale**: Three scopes (app/router/operation) was an over-decomposition. Router scope had no concrete use case that singleton + per-call did not already cover. The kwarg form (`per_call=True`) reads better than `scope="operation"`: it's literal English, drops DI vocabulary, matches the FastAPI `Depends(yield)` per-request idiom in spirit.

**Alternatives considered**:

- `scope="app" | "router" | "operation"` (three tiers, enum strings) — rejected: adds a concept (router scope) with no user need, and the string-enum surface reads more DI-flavored than the boolean kwarg.
- `app.per_call_provide(T, factory)` separate method — rejected: redundancy with `provide`; principle #2 violation.
- Drop per-call scope entirely, force users to `async with db.transaction()` in tool body — rejected: transactions are the canonical case the framework should support declaratively. Per-call scope also generalizes beyond transactions (audit context, request IDs, per-call HTTP clients).

**Underlying standalone DI library** exposes three scopes (`SINGLETON`, `SCOPED`, `TRANSIENT`) per .NET DI convention; a2kit's `App` wrapper maps `per_call=True` to `SCOPED` and never surfaces `TRANSIENT`.

### D2: Lazy first-resolution, no eager warmup

Resources enter on first use within their declared scope. App-scope resources enter at the first dispatch that resolves them; per-call resources enter at the first resolution within a given call.

**Rationale**: Eager-at-App-start (today's behavior) makes the BrowserPool/LlmExtractor case impossible to handle cleanly — the user pays full warm cost regardless of whether the tools that need them are ever invoked. Lazy default matches every modern DI ecosystem except Spring (which is the outlier and widely complained about). Cold-start improves materially for CLI single-shot invocations and dev iteration.

**Alternatives considered**:

- Eager-by-default with `lazy=True` opt-in — rejected: inverts the right default.
- Eager-by-default with `eager=False` per-resource opt-out — rejected: same problem.
- Lazy-by-default with `eager=True` opt-in (the earlier brainstorm shape) — rejected: module author imposes startup cost on consumers; the decision belongs to the operator at the composition root, not the module author. Operators who need start-time verification can call `await app._resolver.get(T)` between `async with app` and `serve_all`.

**Error-visibility tradeoff** (lazy hides connection errors until first use) is mitigated three ways: pydantic-settings validates env at App start regardless; an `a2kit check` CLI subcommand resolves the full graph for CI/health checks; operators may force-resolve specific types between `async with app:` and `serve_all` via two-line pattern.

### D3: Single lifecycle protocol convention

Resources express lifecycle by **either**:

1. Implementing `__aenter__` / `__aexit__` on the class itself (the resource is its own async context manager), **or**
2. A registered factory that is an `@asynccontextmanager` generator.

The framework SHALL NOT detect `aclose`, `close`, `shutdown`, or any other ad-hoc cleanup method.

**Rationale**: Three-protocol detection is a2kit-specific magic that an LLM (or new engineer) cannot predict by reading the class. `__aenter__` / `__aexit__` is the standard Python async context manager protocol; `@asynccontextmanager` is the stdlib factory shape that FastAPI `Depends(yield)` already trained Python users on. One convention, two surfaces, both stdlib.

**Alternatives considered**:

- Keep `aclose`/`close` detection — rejected: violates "no multiple ways" principle, hidden behavior.
- Require `@asynccontextmanager` only — rejected: forces an indirection through a factory function for resources that could just implement `async with` on themselves.
- Require `__aenter__`/`__aexit__` only — rejected: doesn't compose with wrapping foreign types (e.g., `httpx.AsyncClient`) that the user can't add `__aenter__` to. The factory route exists for this case.

The hand-rolled `_ensure()` pattern (sync `__init__`, internal `asyncio.Lock`, async `_ensure`, every method `await self._ensure()` first) is replaced by `__aenter__` doing the open with framework-managed lock-coalesce. A static lint rule flags `_ensure()` method patterns in resource classes.

### D4: `Lazy[T]` for conditional injection (no service locator)

`Lazy[T]` is a type alias: `Callable[[], Awaitable[T]]`. The dispatcher recognizes parameters annotated `Lazy[T]` (or the equivalent `Callable[[], Awaitable[T]]`) and injects a closure that resolves `T` in the current scope when called.

**Rationale**: Service locator (`ctx.get(T)`) hides dependencies in the function body. Tools declaring `Lazy[BrowserPool]` keep the dependency edge visible in the signature, type-checkable, and trivially fakeable in tests (pass `lambda: fake_browser`). Per research validation, this is the **canonical non-service-locator** answer in Guice (`Provider<T>`), .NET (`Lazy<T>`, `Func<T>`), and Seemann's own writing on "Lazy Components".

**Alternatives considered**:

- `ctx.get(T)` on injected Context — rejected: service locator, hidden deps. Even Hynek's `svcs` (which defends service locator philosophically) is positioned for app code, not for framework embedding.
- `Provider[T]` named after Guice — rejected: name reads as Java-flavored. `Lazy[T]` is Pythonic, reads as English.
- Lazy proxy magic (inject a fake `BrowserPool` that actually resolves on first method call) — rejected: type-checker hostile, debugging hostile.
- Refactor-only (split tools per mode) — rejected as universal answer: the a2web extract case is genuinely one operation with conditional resources. Splitting harms the API surface.

**Scope semantics**: `Lazy[T]` honors `T`'s registered scope. Calling the closure twice in the same call returns the same cached instance (app-scope or per-call cached). Calling it from two different calls returns the same app-scope instance, or fresh per-call instances respectively.

### D5: Custom per-scope cleanup stack, not stdlib AsyncExitStack

Each scope (app-scope on `App`, per-call scope on the child container) owns a `list[tuple[type, AsyncCallable]]` recording entered resources in insertion order. Scope close unwinds in LIFO order with per-resource `try/except` isolation: a failing `__aexit__` is logged at WARN+ and the unwind continues with sibling resources.

**Rationale**: Stdlib `AsyncExitStack` carries known bugs in MCP-adjacent code paths — cpython #137517 (background-task exception propagation delayed until program exit when combined with `gather`/`TaskGroup`), MCP SDK #1213 (close-fails-first-attempt), trio #1243 (silent break with nurseries). MCP is the primary transport a2kit ships. Owning the unwind path lets us isolate each cleanup, prevent one bad resource from poisoning siblings, and avoid the upstream bug surface.

**Alternatives considered**:

- Use `AsyncExitStack` directly — rejected: see above bug surface.
- Use `AsyncExitStack` with custom wrapping that catches per-resource — rejected: still inherits the background-task propagation issue.
- Topological-order teardown (current shape) — rejected: with one scope tier per container (`SINGLETON` per app, `SCOPED` per call), insertion order *is* topological order. The intra-scope dependency graph is implicit in resolution order.

### D6: No `app.warm()`, no `app.override()`, no `ctx.get()`

Three APIs the earlier brainstorm proposed are dropped before reaching the spec:

- **`app.warm(...)`** — operator-side eager warmup. Replaced by two-line pattern: `await app._resolver.get(T)` between `async with app:` and `serve_all`. Not worth a named API for a marginal optimization.
- **`app.override(T, factory)`** — test-time override context manager. Replaced by composition-root re-registration: tests call `build_test_app()` which calls override modules' `register(app)` after production modules. `provide(T, ...)` is last-write-wins; the second registration replaces the first. Matches Seemann / ASP.NET `WebApplicationFactory` / dishka philosophy.
- **`ctx.get(T)`** — service-locator escape hatch. Dropped per D4 reasoning. If a genuinely dynamic case emerges, add a typed `Resolver` injection later.

**Rationale**: Every concept on the surface carries documentation, learning curve, AI training-data, and support burden. Three concepts we don't ship is three concepts users don't have to learn. The dropped behaviors are all reachable through existing primitives in <5 lines of consumer code.

### D7: pydantic-settings auto-resolution

`BaseSettings` subclasses are auto-resolved without explicit `app.provide(...)` registration. When the container is asked to resolve `T: type[BaseSettings]` and no explicit provider exists, it constructs `T()` (zero-arg; pydantic-settings reads env at construction) and caches at app-scope.

**Rationale**: Settings classes are a special case: their constructor is the configuration system, not "code that runs." Forcing `app.provide(SmtpSettings)` for every settings class is boilerplate that adds nothing. The convention is narrow, predictable, and visible — any `BaseSettings` subclass triggers the auto-resolution; nothing else does. Matches .NET `IOptions<T>` / Spring `@ConfigurationProperties` / FastAPI's pydantic-settings integration.

**Alternatives considered**:

- Require explicit `app.provide(SmtpSettings, lambda: SmtpSettings())` — rejected: pure boilerplate.
- Add `app.settings(T)` sugar — rejected: a third name for the same concept.
- Auto-resolve any zero-arg-constructible class — rejected: too broad, surprising for non-settings classes.

### D8: `Resolver` protocol decouples framework from container

a2kit framework modules (dispatcher, LDD sinks, MCP transport, lifecycle manager) access the container only via a narrow `Resolver` protocol:

```python
class Resolver(Protocol):
    async def get[T](self, t: type[T]) -> T: ...
    def provide(self, t: type, factory: Any = None, *, scope: Scope = Scope.SINGLETON) -> None: ...
    def child(self) -> "Resolver": ...
    async def aclose(self) -> None: ...
```

The concrete implementation is `a2kit.packages.di.Container`. Framework modules import `Resolver` from `a2kit.packages.di`; they never import `Container` directly. The framework's own internals (dispatcher state, LDD sinks, etc.) are constructed plainly in `App.__init__` and **do not register themselves through user DI**.

**Rationale**: Per research, "pluggable DI engine" is YAGNI — Spring, NestJS, FastAPI all own DI as integrated. But protocol-based decoupling is cheap and gives us future flexibility: if dishka adds in-place overrides + migration-hint errors in a future release, swapping is bounded. More importantly, the discipline of "framework internals don't go through user DI" prevents user DI from accidentally controlling framework behavior.

### D9: Test overrides via composition-root re-registration

Tests build a separate App with override modules registered after production modules. `app.provide(T, ...)` follows last-write-wins semantics on the type key.

```python
def build_test_app(overrides_module=None) -> App:
    app = App("test")
    real_db_module.register(app)
    a2web.register(app)
    if overrides_module:
        overrides_module.register(app)   # last-write-wins
    return app
```

**Rationale**: Per Q3 research, in-place override APIs are footguns (FastAPI `dependency_overrides` cache leak; Spring `@MockBean` cache invalidation). ASP.NET `WebApplicationFactory.WithWebHostBuilder` and dishka both ship "build a different container for tests" as the recommended pattern. Composition-root re-registration is the simplest possible expression of this: same mechanism for prod and tests, different last-step.

The container is sealed after first `__aenter__`; further `provide(...)` calls raise. This prevents mid-life mutation, which is the failure mode that makes mutation APIs bug-prone.

### D10: Standalone-shippable DI package

`a2kit.packages.di` becomes a self-contained package with:

- Zero `a2kit.*` imports inside (validated by a static check in `make lint`).
- Its own `Container`, `Scope` enum, `Resolver` protocol, `UnresolvableType` exception, plus the cleanup-stack primitives.
- Pure stdlib + optional `pydantic_settings` integration via duck-typing (no hard dependency on `pydantic_settings` — the container checks `hasattr(cls, "model_config")` and behaves accordingly, but does not import pydantic).
- A `pyproject.toml` skeleton ready for separate PyPI publish later (out of scope for this change to actually publish).

**Rationale**: Forces the API to be self-contained, which improves the design. Provides reusable value to the broader Python community. Enables independent versioning later. Cross-language ports (TS/Rust) re-implement the standalone package, not a2kit's full surface.

## Risks / Trade-offs

- **Breaking change touching the most-used surface (`app.singleton` / `app.provide`)**. Every consumer pays the migration cost.
  → Mitigation: loud-crash `TypeError` with migration hint at first invocation (CLAUDE.md principle #4). Migration table in `CHANGELOG.md` `Unreleased`. The `a2web` migration is the canonical reference and is part of this change's task list.
- **Lazy default hides connection errors until first use**.
  → Mitigation: pydantic-settings validates env at App start (most config errors caught). Two-line operator pattern (`await app._resolver.get(T)`) for forced verification. Defer a named `a2kit check` CLI subcommand to a follow-up change.
- **Custom cleanup stack reinvents AsyncExitStack-shaped wheel**.
  → Mitigation: the difference is per-resource exception isolation + no background-task propagation entanglement. Test matrix explicitly covers: background-task-raises-during-shutdown, partially-entered-stack-on-startup-failure, lifespan-skipped-when-middleware-present. The reinvention is justified by the cpython #137517 / MCP SDK #1213 bug surface.
- **Per-call scope adds child-container construction cost per dispatch**.
  → Mitigation: child containers are dict-of-cached-instances + a cleanup list — both `O(1)` construction, no provider re-registration. Per-dispatch overhead is single-digit microseconds. Benchmark gate ships with the change.
- **`Lazy[T]` reads like a workaround at first**.
  → Mitigation: docs frame it as "the explicit way to declare conditional deps," with the a2web extract case as the canonical example. Lint suggests it for declared-but-unused-in-body parameters.
- **dishka's design lessons applied without dishka's testing**.
  → Mitigation: real-FastMCP-transport tests for the new dispatch path (already a2kit convention per CLAUDE.md). Track dishka's bug tracker for any class of issue we should pre-emptively cover.
- **Auto-resolved `BaseSettings` is a special-case rule that grows surface**.
  → Mitigation: the rule is one branch in `Container.get`, ~5 LOC, documented as the *only* special case. A class triggers it iff it inherits from `pydantic_settings.BaseSettings` — a single `issubclass` check.
- **Five user-facing concepts at first contact is one more than FastAPI**.
  → Mitigation: `Lazy[T]` is tier-2 (patterns guide, not quickstart). Quickstart shows four concepts (`register`, `provide`, typed params, `BaseSettings`). The fifth (`Lazy[T]`) appears when conditional deps come up.

## Migration Plan

- v0.36 ships the new surface with `app.singleton` / old `app.provide` raising `TypeError` immediately.
- Migration table in `CHANGELOG.md`:
  | Old | New |
  |---|---|
  | `app.singleton(T, factory)` | `app.provide(T, factory)` |
  | `app.singleton(T)` (class-as-factory) | `app.provide(T)` |
  | `app.provide(T, sync_factory)` (per-dispatch fresh) | `app.provide(T, factory, per_call=True)` |
  | `@on_shutdown` cleanup of DI'd resources | resource's own `__aexit__` or factory `finally` |
  | `_ensure()` lazy-init pattern | class `__aenter__` doing the open |
  | `_snapshot()`/`_restore()` test hooks | `build_test_app()` factory + override modules |
- The `a2web` migration is included in this change's tasks to validate the migration path on a real consumer.
- No deprecation period. Loud crash with hint per CLAUDE.md.

## Open Questions

- Standalone package name for the PyPI publish. Candidates: `kit-di`, `tinydi`, `lazydi`, `provide-py`, `containrr`. Decided at publish-time, not now.
- Whether `Container.child()` should accept a scope-tag for richer per-scope diagnostics (e.g., `container.child(tag="call:extract")`). Lean: yes, optional `tag=` for debug logging; defer to a follow-up if scope churn proves common.
- Whether to ship `a2kit check` CLI subcommand in this change or follow-up. Lean: follow-up. The two-line pattern works for operators who need it now.
- Should `Lazy[T]` accept a synchronous variant (`Callable[[], T]`) for non-async resources? Lean: no, keep one shape — `Callable[[], Awaitable[T]]`. All a2kit dispatchers are async. Reduces shape multiplication.
