## Context

v0.21 (de-magic-2) collapsed verb decorators to `(name, tags, annotations)`, removed `_slugify`, removed `WriteNotAllowed` and `ListViewSettings` from core, and introduced the staged-extra pattern (`A2KitMeta.extra: dict[str, Any]`) so feature decorators (`@enriches/@lists/@reports`) could stack outside of core. Two structural costs surfaced in real usage:

1. **Stack noise**: `@a2kit.list_()` + `@lists(...)` + `@enriches(...)` triple-stacks on list tools. `@enriches(tracker_404_enricher)` repeats on every method of a router. `@lists(...)` re-enumerates fields the return type already declares.
2. **Connection plumbing**: every router carries a `def __init__(self, get_store: GetStore)` factory closure, and every tool method calls `await self.get_store(connection)`. The factory is a workaround for connection-scoped state in a process-scoped router. It works but it's a pattern users keep re-implementing.

Constraints carried over from de-magic-1/-2 and not negotiable here:
- Core `src/a2kit/*.py` (excluding `packages/`) must not learn domain feature names. `A2K-CORE-CLEAN` enforces.
- No ContextVar + monkey-patch, no class-`__dict__` scanning, no central kwargs bag on the verb decorator.
- Cold-start `import a2kit` < 100ms, fastmcp confined to `packages/mcp` and only loaded by `serve`.
- Every architectural rule must be expressible as a lint check.

## Goals / Non-Goals

**Goals:**
- Eliminate stacked feature decorators where they were carrying class-level invariants (`enrichers`) or duplicating the verb (`@lists` + `@list_()`).
- Replace the `get_store` factory boilerplate with typed, per-call dependency injection at the tool method signature.
- Keep all DI machinery in `packages/connections`. Core exposes a small dispatch hook only.
- Keep tool method signatures grep-able: every kwarg has a real Python type; injectable types are real classes (not magic strings).
- Make `name = "..."` optional but keep it as the override path; auto-derivation is one documented rule, not a regex menagerie.

**Non-Goals:**
- A general-purpose IoC container managing singletons, lifecycle, scopes beyond per-call. Singletons stay constructed in plain Python at app build time.
- Reviving `WriteNotAllowed` in core, reviving `_slugify`, or expanding `A2KitMeta` beyond `extra: dict`.
- FastAPI-style `Annotated[T, Depends(...)]`. Annotation alone (`store: TrackerStore`) is enough — providers are keyed by type, not by `Depends` markers.
- Auto-magical singletons (no "everything is injectable"). Only types reachable from a registered provider chain are injectable.

## Decisions

### D1. `@a2kit.list_(...)` absorbs list-view settings; selectable derived from return type

**Choice**: `@a2kit.list_(*default_fields, page_size=None, selectable_fields=None)`. When `selectable_fields` is omitted, the framework reads the return-type annotation, walks `list[T]` to `T`, reads `T.__pydantic_fields__` (or `dataclasses.fields(T)`), and uses those keys. Explicit override remains for strict subsets.

**Why**: list-view settings are intrinsic to `list_()` — no other verb consumes them. The de-magic-2 antipattern was *kwargs accumulating on a central decorator* (read/write/list_ sharing one bag). Specialized kwargs on a specialized verb is not the same antipattern. Field enumeration is mechanical from the return type; redundancy was AI-slop carried in.

**Alternatives considered**:
- Keep `@lists(...)` as a separate stacked decorator. Rejected: doubles the verb on the same method.
- Move list-view to a class attribute (`list_view = ListViewSettings(...)`). Rejected: list-view is per-tool, not per-router.

### D2. Class-attribute `enrichers` + optional `def enrich(self, exc)` method

**Choice**: Routers declare a class attribute `enrichers: list[Callable[[Exception], str | None]] = [...]` and may define `def enrich(self, exc) -> str | None`. Resolution at exception time:
```
1. if hasattr(self, "enrich"): try self.enrich(exc) → if not None, return it
2. for fn in type(self).enrichers: try fn(exc) → if not None, return it
3. fall through to default
```

**Why**: the existing `@enriches` repeats on every method of a router because it's a *router-level invariant masquerading as per-method*. Class attribute mirrors how `name` works — declarative, grep-able, side-by-side. The optional method is the escape hatch when an enricher legitimately needs `self` (instance state, store reference). Two slots, no overlap, both standard Python.

**Alternatives considered**:
- Keep `@enriches` and add a class-level `@enriches(...)` decorator. Rejected: same kwarg accumulation pattern, just at class scope.
- Single shape (only method, or only list). Rejected: list covers stateless cases cleanly; the method covers stateful cases without a decorator. Both are needed.

### D3. Request-scoped DI container, registered via `App.provide(T, factory=None)`

**Choice**: Add `App.provide(type_: type[T], factory: Callable[..., T] | None = None) -> Self`. When `factory` is omitted, the class itself is the factory — the container introspects `type_.__init__` annotations and resolves each parameter through the chain. Factories (when explicit) are introspected the same way: their parameter annotations declare what they themselves depend on, recursively. Init/factory parameters with primitive types **and** a default value are skipped (use the default); parameters with primitive types and no default are an error at registration. The container resolves a typed graph per tool call, with results cached within the call.

```python
# Common case: class is the factory
app.provide(TrackerStore)              # equivalent to provide(TrackerStore, TrackerStore)

# Explicit factory: when construction is non-trivial
app.provide(SearchIndex, lambda store: SearchIndex.warm(store))
```

**Connection-config provider is auto-installed.** When `app.add_cli(connections_cli(ConfigT))` (or any `Connections[ConfigT]` plugin attachment) runs, it registers a provider for `ConfigT` whose factory takes `connection: str` and calls `connections.resolve(connection)`. Tool authors and app builders never write that lambda. Lint enforces that this is the *only* provider taking `connection: str`.

**Why**: the simplest provider call is `provide(T)` — no lambda, no boilerplate, just "container, you know how to build this." Class-as-factory mirrors how `dataclass` and `pydantic` already handle construction. Auto-installing the config provider via the Connections plugin removes the one piece of glue every app would otherwise duplicate. The chain still bottoms at `connection: str` through exactly one (auto-registered) provider.

**Alternatives considered**:
- Require explicit `factory=` always. Rejected: the class-as-factory case is the 90% case; making it explicit is ceremony.
- Auto-`provide` every class referenced by a tool kwarg, even without an explicit `provide()` call. Rejected: silent registration; the explicit `.provide(T)` list is the grep-able truth of "what does this app inject."
- FastAPI `Annotated[T, Depends(get_store)]`. Rejected: extra ceremony for no gain over type-keyed providers.
- Per-Router DI (build a fresh router per call, inject via `__init__`). Rejected previously after exploring; per-method is what the user converged on.

### D4. Tool method signature: injectable kwargs are stripped from wire schema

**Choice**: At collect time, the framework partitions a tool method's kwargs into:
- **Wire** — type is a primitive, BaseModel, or stdlib container. Goes on the MCP/CLI input schema.
- **Injectable** — type matches a registered provider in the App's container. Stripped from schema; resolved per-call.
- **Always-provided allowlist** — `ToolContext`, `App`. Never on schema; filled by dispatch.

Schema generation, CLI builder, and MCP server all consult the same partition.

**Why**: the agent should only see params it can supply. Hidden injectables aren't ContextVar-magic — they're typed kwargs whose source the reader can grep (the `provide()` call). The partition is mechanical and lint-checkable.

**Alternatives considered**:
- Keep all kwargs on the wire schema and let the framework ignore agent-supplied values for injectables. Rejected: leaks injection types to the agent's tool contract.
- Force users to use `Annotated[T, Inject()]` to mark injectables. Rejected: redundant with the provider registry.

### D5. Typed config entry; raw `connection: str` only inside the auto-installed bottom provider

**Choice**: Tools that need the connection config declare `cfg: TrackerConfig` (or whatever concrete type was passed to `connections_cli(...)` / `Connections(...)`) as a kwarg. The framework reads wire `connection: str`, resolves it through the auto-installed `TrackerConfig` provider, binds the result. Tools that don't need it don't see it. The wire schema includes `connection: str` whenever any tool's injectable graph transitively reaches the config provider.

**Why**: tool authors should never parse a connection string. The Connections package is the only thing that knows how to turn a name into a config — and since the user already declares the config type once via `connections_cli(ConfigT)`, the framework can install the resolver itself. No second declaration via `provide()`. Lint rule `A2K-DI-CHAIN` enforces that exactly one provider (the auto-installed config provider) takes `connection: str`.

**Alternatives considered**:
- Keep `connection: str` in tool signatures and let users call `connections.resolve(connection)` themselves. Rejected: re-introduces the boilerplate the DI is meant to remove.
- Hide `connection` from the wire entirely. Rejected: agents need to send it; the wire schema must declare it.

### D6. Singletons stay plain Python; container is request-scope only

**Choice**: Process-wide deps (loggers, clocks, the `App` itself) are constructed at app build time and passed via `Router.__init__`. The container does not register or resolve them.

```python
logger = make_logger()
app = a2kit.App("tracker").add_router(TasksRouter(logger=logger))
```

**Why**: scope-bounded containers stay reasoned-about. "Container handles request-scoped types only" is a one-line invariant. Singletons via plain Python are zero-magic and zero-cost; mixing scopes inside one container balloons complexity (lifecycle, eager vs lazy, override paths).

**Alternatives considered**:
- Two-scope container (singleton + request). Rejected: doubles the API surface for a use case that plain `__init__` already covers.

### D7. Hybrid name derivation; antipattern #20 retracted

**Choice**: When `name` is unset, derive: strip exactly one trailing `Router` suffix (case-sensitive), lowercase the rest. Collisions across routers in one app raise at build time. Explicit `name = "..."` always wins.

```
class TasksRouter        → "tasks"
class Tasks              → "tasks"
class ProjectsRouter     → "projects"
class MyTrackerRouter    → "mytracker"  (lowercased remainder)
class MyTracker          → "mytracker"
```

**Why**: one rule, documented, predictable. The de-magic-2 antipattern was *combinatorial slugify* (camelCase → kebab, multiple suffixes, collision-resolution heuristics). A single suffix-strip is a convention, not magic. Antipattern #20 is retracted with this reasoning.

**Alternatives considered**:
- Keep verbatim-only (status quo). Rejected: ceremonial line on every router for a mechanical transform.
- Multi-suffix or camelCase-aware. Rejected: that *is* the original antipattern.

### D8. Container lives in `packages/connections/container.py`; core gains one dispatch hook

**Choice**: `packages/connections/container.py` adds:
- `class Container` with `register(T, factory)`, `resolve(T, *, connection: str | None) -> T`, per-call cache.
- `partition_kwargs(fn, container) -> (wire_keys, injectable_keys)` for schema gen.
- `apply_kwargs(fn, wire_kwargs, container) -> dict[str, Any]` for dispatch.

Core `src/a2kit/tool.py` exposes a `dispatch_hook` protocol consumed by CLI builder + MCP server. The hook is a callable `(fn, wire_kwargs) -> resolved_kwargs`. Apps without a Connections plugin get a no-op hook (identity). `A2K-CORE-CLEAN` allows the hook protocol but disallows Container/ConnectionConfig token references in core.

**Why**: keeps core purity intact (no domain knowledge), keeps the DI shape pluggable (different connection plugins could ship different containers), and keeps the surface area honest (one protocol).

## Risks / Trade-offs

- **Hidden kwargs in tool signatures** → mitigated by: (a) injectable types are real Python classes that are grep-able to a `provide()` call; (b) lint rule `A2K-DI-PROVIDER` fails fast at app build time when an injectable has no provider; (c) docs and example code show the wire/injectable partition explicitly.
- **Per-call resolution overhead** → mitigated by: provider factories are simple lambdas, container caches within the call, no I/O at resolution time (resolution is just object construction). Benchmark the dispatch hot path; budget < 100µs per call.
- **Convention surprise on slug derivation** → mitigated by: lint rule warns on any `name = "..."` whose value differs from the derivation rule (catches accidental drift), one paragraph in README explains the rule.
- **Test ergonomics regression** → mitigated by: `app.provide(T, fake_factory)` overrides are first-class; tests build apps with fake providers exactly like prod, no monkey-patching.
- **Provider chain debugging** → mitigated by: `App.providers` is introspectable; on resolution failure the container raises `UnresolvableType(T, chain=[...])` showing the missing link.

## Migration Plan

1. Land container + `App.provide()` API + dispatch hook (no behavior change yet — empty container is a no-op).
2. Migrate `examples/tracker/` and `examples/streaming_logger/` to the new shape; tests follow.
3. Land `@a2kit.list_(*default_fields, page_size=…, selectable_fields=…)` and delete `packages/mcp/lists.py`.
4. Land class-attribute `enrichers` + `enrich` method; delete `packages/enrichers/`.
5. Land hybrid name derivation; retract antipattern #20.
6. Add `A2K-DI-PROVIDER` and `A2K-DI-CHAIN` lint rules; flip from disabled to enforced after migration.
7. Bump to v0.22.0 with single CHANGELOG entry.

Rollback: revert in reverse order; the container is additive until step 4, so steps 1–3 can stay and 4–7 reverted independently.

## Open Questions

- Should `App.provide(T, factory)` accept async factories? Default to sync; if a provider needs I/O, it can be made async — but per-call resolution then needs `await`. Likely yes (factories may be async); decide during implementation.
- Should we surface `App.override(T, factory)` distinct from `provide()` for tests, or is "last write wins" on `provide()` sufficient? Lean: last-write-wins is enough; no separate override API.
