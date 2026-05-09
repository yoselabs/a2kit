## 1. Container scaffolding (additive, no behavior change)

- [x] 1.1 Create `src/a2kit/packages/connections/container.py` with `Container` class: `register(T, factory)`, `resolve(T, *, connection)`, per-call cache, `UnresolvableType` exception with chain trace
- [x] 1.2 Add `partition_kwargs(fn, container) -> (wire_keys, injectable_keys, needs_connection)` helper in container module — reads tool method `inspect.signature` and looks up each kwarg type in the registry
- [x] 1.3 Add `apply_kwargs(fn, wire_kwargs, container, allowlist) -> dict` helper that resolves injectable kwargs and merges with wire kwargs; honors `ToolContext`/`App` allowlist
- [x] 1.4 Define `DispatchHook` protocol in `src/a2kit/tool.py`: `Callable[[ToolFn, dict], Awaitable[dict] | dict]`. No imports of container in core
- [x] 1.5 Wire `App.dispatch_hook` attribute (defaults to identity hook); CLI builder + MCP server consult it before calling the tool method
- [x] 1.6 Add `App.provide(T, factory=None) -> Self` and `App.providers: dict[type, Callable]` attribute. When `factory is None`, store the class itself; container introspects `T.__init__` at resolve time. When first `provide()` is called, lazily install a non-identity dispatch hook that delegates to a per-app `Container`. Validate at registration: any constructor param without a default must have an annotated type that the container can resolve (or be the wire `connection: str` allowed for the auto-config provider)
- [x] 1.7 Schema gen consults `partition_kwargs` to strip injectable kwargs from MCP/CLI input schemas; auto-include `connection: str` when needed

## 2. Lint rules

- [x] 2.1 Add `A2K-DI-PROVIDER` rule in `src/a2kit/packages/lint/rules/di.py`: scans router classes, partitions each tool method's kwargs, fails when an injectable type has no provider in the test app's graph (and is not on the allowlist)
- [x] 2.2 Add `A2K-DI-CHAIN` rule in same module: scans `App.provide(...)` registrations, fails when any provider other than `ConnectionConfig` takes a parameter named `connection` of type `str`
- [x] 2.3 Register both rules in `src/a2kit/packages/lint/static.py` `ALL_RULES`; keep disabled in `Makefile` until migration completes
- [x] 2.4 Update `A2K-CORE-CLEAN` forbidden-token list to include `Container`, `ConnectionConfig`, `partition_kwargs`, `apply_kwargs`, `UnresolvableType` for `src/a2kit/*.py` outside `packages/`

## 3. Verb decorator consolidation

- [x] 3.1 Update `src/a2kit/tool.py` `list_(...)` decorator to accept `*default_fields, page_size=None, selectable_fields=None` plus existing `name/tags/annotations`
- [x] 3.2 Move `ListViewSettings` dataclass back to `src/a2kit/metadata.py` (carrier shape only — no Connections/feature names)
- [x] 3.3 Implement selectable-fields derivation: read return-type annotation, walk `list[T]`, prefer `T.__pydantic_fields__` then `dataclasses.fields(T)`; cache on `meta.extra["a2kit.list_view"]`
- [x] 3.4 Add validation: `default_fields` must be a subset of resolved `selectable_fields`; raise at decorator time
- [x] 3.5 Delete `src/a2kit/packages/mcp/lists.py` and remove from `__init__.py` exports
- [x] 3.6 Update `src/a2kit/packages/mcp/listview.py` middleware to read settings from the consolidated location (no path change to `meta.extra["a2kit.list_view"]`)

## 4. Enricher consolidation

- [x] 4.1 Update `src/a2kit/routers.py` `_collect_methods` to read `cls.enrichers` (class attribute, default `[]`) and `getattr(self, "enrich", None)` once at collect time; stage the bound resolver into per-tool meta
- [x] 4.2 At dispatch error time, framework calls `self.enrich(exc)` if defined, then iterates `enrichers`; first non-None wins
- [x] 4.3 Delete `src/a2kit/packages/enrichers/` package; remove from imports/exports
- [x] 4.4 Add `A2K-ENRICHER-SHAPE` lint rule (under existing rules module) verifying `enrichers` is a list/tuple of callables and `enrich` (if present) has signature `(self, exc) -> str | None`

## 5. Router slug derivation

- [x] 5.1 Update `src/a2kit/routers.py` slug resolution: `cls.name` if set; else strip exactly one trailing `Router` from `cls.__name__` (case-sensitive) and lowercase the remainder
- [x] 5.2 Add collision detection in `App.add_router`: track slugs in a dict, raise `ValueError(f"slug {slug!r} already registered by {existing_cls!r}")` on duplicate
- [x] 5.3 Retract antipattern #20 in `ANTIPATTERNS.md` with the de-magic-3 reasoning ("convention without combinatorial slugify is fine")

## 6. Connection plugin updates

- [x] 6.1 Update `connections_cli(ConfigT)` (in `src/a2kit/packages/connections/cli.py`) to also auto-register a provider for `ConfigT` on the App when its returned subgroup is mounted via `add_cli`. Provider factory: `lambda connection: connections.resolve(connection)`. Idempotent: re-mounting does not duplicate
- [x] 6.2 Add an `App.has_provider(T) -> bool` helper used by the auto-registration to skip when a manual `provide(T, ...)` already ran (allowing user override)
- [x] 6.3 Document the simplified wiring in `src/a2kit/packages/connections/README.md`: `add_cli(connections_cli(TrackerConfig))` is the single entry; tools type kwargs as `cfg: TrackerConfig` or `store: TrackerStore` (where `TrackerStore` is `provide()`'d separately)
- [x] 6.4 Verify cold-start: `import a2kit` does not load `Container`; `import a2kit.packages.connections` does not invoke any factory; the auto-registration runs only when `add_cli(connections_cli(...))` is actually called

## 7. Example migrations

- [x] 7.1 Rewrite `examples/tracker/routers.py`: drop `__init__(get_store=…)`, drop all `@enriches(...)` decorators, drop `name = "..."` lines, declare `enrichers = [...]`, declare tool kwargs as `store: TrackerStore` (and `connection: ConnectionConfig` where used)
- [x] 7.2 Update `examples/tracker/server.py` wiring to the simplified shape: `provide(TrackerStore)` only (no lambda); the `TrackerConfig` provider is auto-installed by `add_cli(connections_cli(TrackerConfig))`
- [x] 7.3 Rewrite `examples/streaming_logger/routers.py` similarly: stacked decorator removed, kwargs typed
- [x] 7.4 Update `examples/tracker/README.md` and `examples/streaming_logger/README.md` to reflect new shape (consolidated `@a2kit.list_(...)`, `enrichers = [...]`, typed kwargs, `provide(...)` wiring)

## 8. Test migrations

- [x] 8.1 Update `tests/packages/cli/test_builder.py` Probe routers: drop `name = "probe"` lines (still works since auto-derives or keep explicit; check both shapes)
- [x] 8.2 Migrate `tests/test_decorator_v15.py` (or equivalent verb tests) to assert consolidated `@a2kit.list_(...)` API and selectable derivation
- [x] 8.3 Migrate enricher tests: assert class-attribute and method-form resolution, including method-takes-precedence and first-non-None
- [x] 8.4 Migrate `tests/test_runtime.py`, `tests/packages/mcp/test_listview*.py`, `tests/packages/mcp/test_server.py` to consolidated list_view path
- [x] 8.5 Add `tests/packages/connections/test_container.py`: explicit factory registration, class-as-factory shorthand `provide(T)`, two-link chain, per-call caching, `UnresolvableType` shape, async factory support, primitive-no-default raises at registration
- [x] 8.6 Add `tests/packages/connections/test_dispatch.py`: end-to-end dispatch through container, schema strips injectables, `cfg: TrackerConfig` round-trip via auto-installed provider, manual `provide(TrackerConfig, ...)` overrides auto-installed factory
- [x] 8.7 Add `tests/packages/lint/test_di_rules.py`: `A2K-DI-PROVIDER` and `A2K-DI-CHAIN` positive + negative cases (≥4 each)
- [x] 8.8a Add `tests/packages/connections/test_auto_provider.py`: `add_cli(connections_cli(TrackerConfig))` installs a `TrackerConfig` provider; not installing the CLI means no auto-provider; manual override path
- [x] 8.8 Add `tests/test_router_slug_derivation.py`: TasksRouter→tasks, Tasks→tasks, MyTrackerRouter→mytracker, explicit override, collision raises

## 9. Release

- [x] 9.1 Bump `pyproject.toml` to `0.22.0`
- [x] 9.2 Add CHANGELOG.md entry (collapsed format) summarizing the four-item ergonomic round
- [x] 9.3 Flip `A2K-DI-PROVIDER`, `A2K-DI-CHAIN`, `A2K-ENRICHER-SHAPE` from disabled to enforced in `Makefile`
- [x] 9.4 Run `make lint`, `make test`, verify cold-start under 100ms
- [x] 9.5 Update `README.md` API surface table: consolidated `list_(...)` signature; new `enrichers`/`enrich` Router contract; `App.provide(T, factory)` API; new lint rules; migration section for v0.21 → v0.22
- [x] 9.6 Add three new ANTIPATTERNS.md entries (or net delta vs #20 retraction): factory-closure-in-init for connection-scoped state, repeated `@enriches` on every method, redundant `selectable_fields` enumeration
- [x] 9.7 Tag `v0.22.0` and push to origin/main
