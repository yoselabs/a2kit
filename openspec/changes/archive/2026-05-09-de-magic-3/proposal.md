## Why

After de-magic-2 collapsed verb decorators to three kwargs and removed slug-derivation magic, four ergonomic pain points remain: (1) `@lists(...)` stacks redundantly on `@a2kit.list_()` and re-enumerates row fields the return type already declares; (2) `@enriches(tracker_404_enricher)` repeats on every method of a router; (3) per-call connection-scoped state flows through a `get_store: Callable[[str], Store]` factory closure that every router author has to write; (4) `name = "tasks"` ceremony on every router class for what is almost always a mechanical convention. v0.21 chose explicit-over-implicit on each, and the cost is now visible across the example app and any real downstream router.

This round trades small, *typed* affordances for the boilerplate, without re-introducing the AI-slop patterns de-magic-1 and de-magic-2 removed (no central kwargs bag, no ContextVar + monkey-patch, no class-dict scanning). The headline is a request-scoped DI container in `packages/connections` that resolves typed, request-bound dependencies (`ConnectionConfig`, `Store`, `UserRepository`, …) for tool methods — modeled on standard backend DI (FastAPI/NestJS), kept out of core, enforced by lint.

## What Changes

- **BREAKING** `@a2kit.list_(...)` accepts `*default_fields, page_size=None, selectable_fields=None` directly. The standalone `@lists(...)` decorator and `a2kit.packages.mcp.lists` module are removed.
- **BREAKING** `selectable_fields` is derived from the tool's return-type annotation (`list[T]` → fields of `T`) when not provided. Explicit override remains supported for strict subsets.
- **BREAKING** Stacked `@enriches(...)` decorator and `a2kit.packages.enrichers` module are removed. Routers declare enrichers via `enrichers: list[Callable[[Exception], str | None]]` class attribute and/or an optional `def enrich(self, exc) -> str | None` method. Resolution: instance method first, then class list.
- **NEW** Request-scoped DI container in `packages/connections`:
  - `App.provide(T, factory=None)` registers a typed provider. When `factory` is omitted, the class itself is the factory: the container reads `T.__init__` annotations and resolves each parameter through the chain. So `app.provide(TrackerStore)` is the common case — no lambda needed.
  - `add_cli(connections_cli(ConfigT))` auto-registers a provider for `ConfigT` that resolves from the wire `connection: str` via the `Connections` registry. Manual `provide(ConfigT, lambda connection: ...)` is not required.
  - Factories (when explicit) declare their own dependencies via parameter annotations; the container chains. The connection-config provider is the only one that may take a `connection: str` parameter — lint enforces.
  - Tool method kwargs whose type is a registered provider are resolved per-call, cached within the call, and stripped from the MCP/CLI wire schema.
  - The wire schema auto-includes `connection: str` whenever any tool method's injectable graph (transitively) reaches the connection-config provider.
- **BREAKING** Routers no longer require `get_store` factory closures. Tool methods declare `store: TrackerStore`, `connection: ConnectionConfig`, etc. directly as kwargs.
- **BREAKING** Singletons (process-wide deps like loggers) are passed via plain `Router.__init__(...)` arguments at app build time. The container does *not* manage singletons — this keeps the container scope-bounded and the registration story honest.
- **NEW** Hybrid Router slug derivation: `class FooRouter(a2kit.Router)` → `"foo"` by stripping a single trailing `Router` (case-sensitive) and lowercasing the rest. Explicit `name = "..."` overrides. Collisions error at app build time.
- **NEW** Two lint rules in `packages/lint`:
  - `A2K-DI-PROVIDER`: every non-wire kwarg type on a tool method must have a registered provider (or be in the always-provided allowlist: `ToolContext`, `App`).
  - `A2K-DI-CHAIN`: every provider's own parameters must resolve through providers or wire types; only the `ConnectionConfig` provider may consume `connection: str`.
- **REMOVED** `ANTIPATTERNS.md` entry #20 (slug auto-derivation) is retracted with new reasoning: the antipattern was *combinatorial slugify with edge cases*, not a single documented suffix-strip convention.

## Capabilities

### New Capabilities
- `request-scoped-di`: Typed, request-scoped dependency injection container in `packages/connections`, with App-side `.provide(T, factory)` registration, per-call caching, schema stripping, and `ConnectionConfig`-rooted provider chains.

### Modified Capabilities
- `core-purity`: Tighten the boundary — core `src/a2kit/*.py` learns one new contract (a `kwargs_filter` / `kwargs_resolver` callable hook used by tool dispatch) but gains no new feature names. The container itself lives in `packages/connections`.
- `verb-decorators`: `@a2kit.list_()` absorbs `default_fields` / `page_size` / `selectable_fields`; selectable derived from return-type annotation by default.
- `router-conventions`: Class-attribute `enrichers` + optional `enrich` method replace the stacked decorator. Hybrid `name` derivation with explicit override.

## Impact

- `examples/tracker/` and `examples/streaming_logger/` rewritten: routers lose `__init__(get_store=…)` and `@enriches(...)` stacks; tools declare `store: TrackerStore` (and optionally `connection: ConnectionConfig`) directly.
- `src/a2kit/routers.py` learns to read `enrichers` + `enrich` and exposes the kwarg filter/resolve hook to dispatch.
- `src/a2kit/packages/cli/builder.py` and `src/a2kit/packages/mcp/server.py` consult the container at dispatch time and strip injectable kwargs from synthesized schemas.
- `src/a2kit/packages/mcp/lists.py` is deleted; `ListViewSettings` returns to `src/a2kit/metadata.py` as the carrier shape for the (now consolidated) `list_()` decorator.
- `src/a2kit/packages/enrichers/` is deleted.
- `src/a2kit/packages/connections/container.py` is added (~150 LOC: provider registry, per-call resolver with cache, schema-strip helper).
- New tests for: provider chaining, per-call caching, schema stripping, `connection: ConnectionConfig` round-trip, lint rules, and slug derivation.
- `make lint` adds `A2K-DI-PROVIDER` and `A2K-DI-CHAIN`.
- Cold-start budget unchanged (container construction is lazy; providers are not invoked at import time).
