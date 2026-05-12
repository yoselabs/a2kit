# Changelog

## 0.31.0 — bundled breaking minor — 2026-05-13

A single release bundles four coordinated changes so consumers migrate
once, not four times. Coordinated proposals
`align-with-pydantic-and-stdlib`, `loud-degrade-everywhere`,
`explicit-router-surface`, and `lifespan-over-lifecycle-hooks` all ship
here.

### Changed (observability only) — WARN_ONCE on five swallowed sites

Five framework-internal introspection sites that previously swallowed
`Exception` silently now emit one WARN-level log line per offender per
process on first failure and proceed with the documented fallback.
Extends the `_WARN_ONCE` recipe shipped in
`src/a2kit/signature.py:resolve_hints` (round 5/6).

- **L1** `src/a2kit/packages/mcp/server.py:_wrap_with_dispatch_hook` —
  return-annotation copy onto the wrapper now WARNs once per
  `fn.__qualname__` on `get_type_hints` failure instead of using
  `contextlib.suppress(Exception)`. Fallback unchanged: the wrapped fn
  keeps its current annotation-less state, FastMCP's output schema for
  that tool is absent.
- **L2** `src/a2kit/tool.py:_resolve_return_annotation` — WARNs once
  per `fn.__qualname__` on `get_type_hints` failure instead of
  silently returning `None`. Fallback unchanged: returns `None`.
- **L3** `src/a2kit/tool.py:_derive_selectable_fields` — outer
  `get_type_hints` failure WARNs once per `fn.__qualname__` instead of
  silently returning `()`. The inner
  `with contextlib.suppress(Exception):` around the dataclass branch
  was verified dead by running the full test suite after removal
  (788 tests green, including the dataclass-fields regression test);
  the suppress is gone, the branch is unguarded.
- **L4** `src/a2kit/packages/mcp/listview.py:ListViewMiddleware` —
  both `except Exception: return result` sites now WARN once per
  composite key (`f"{tool_name}::get_tool"` for the registry lookup,
  `f"{tool_name}::project"` for the result-reconstruction site) via a
  single module-local `_WARN_ONCE: set[str]`. Fallback unchanged: the
  unprojected `result` is returned.
- **L5** `src/a2kit/packages/otel/middleware.py:_meta_a2kit` — WARNs
  once per `tool_name` on `server.get_tool` failure instead of
  silently returning `{}`. Fallback unchanged: span construction
  proceeds with only `a2kit.tool_name` set; `a2kit.verb`,
  `a2kit.router`, `a2kit.tags` are absent.

### Documentation

- `OPERATIONAL_CONTRACTS.md` gains a new Q9 section codifying the
  "fail-observable, not silent" policy for framework-internal
  introspection failures and indexing the six sites the policy covers
  today.

### Breaking — Param/MetaExtras/Container cache (`align-with-pydantic-and-stdlib`)

- **`a2kit.Param` removed.** The wrapper was a one-line forwarder to
  `pydantic.Field`. Use `Annotated[T, pydantic.Field(description="...")]`
  directly. Migration regex (positional form):
  `s/a2kit\.Param\(("[^"]+")\)/pydantic.Field(description=\1)/`.
  Keyword callers (`a2kit.Param(description="...", examples=[...])`)
  rewrite to `pydantic.Field(description=..., examples=[...])` —
  identity at the kwargs level. `description_of` (internal helper)
  moves to `a2kit._field_introspect`.
- **`A2KitMeta.extra: dict[str, Any]` → `A2KitMeta.extras: A2KitMetaExtras`.**
  The open-dict extension slot becomes a typed pydantic `BaseModel`
  with named fields (`report_type`, `report_schema`, `router_slug`,
  `surfaces`, `list_view`). Read and write through attribute access;
  the legacy `a2kit.<key>` string-key namespace is gone.
  Migration:
  `meta.extra.get("a2kit.report_type")` → `meta.extras.report_type`,
  `meta.extra["a2kit.router_slug"] = slug` → `meta.extras.router_slug = slug`,
  `meta.extra.get("a2kit.surfaces", Surface.ALL)` → `meta.extras.surfaces or Surface.ALL`.
  The wire-projection on `tool.meta["a2kit"]["extras"]` carries the
  same attribute names without the `a2kit.` prefix. The
  `_EXTRA_DROP_FROM_WIRE` constant and the `_ROUTER_SLUG_KEY` /
  `SURFACE_META_KEY` / `EXTRA_TYPE_KEY` / `EXTRA_SCHEMA_KEY` exports
  delete with the dict shape.

### Fixed

- **`Container._param_cache` keyed by `id(factory)` was a latent
  stale-cache bug** under CPython id recycling across nested test
  scopes (same hazard documented for tool-signature caching in
  `a2kit/signature.py`). Replaced with
  `weakref.WeakKeyDictionary[Factory, list[_ParamSpec]]` keyed on the
  live factory object. Internal-only; no migration.

### Breaking — explicit Router surface (`explicit-router-surface`)

The four contracts a Router exposes — `slug`, `tools`, `providers`,
`lifespan` — are now the closed discovery surface. The framework
reads what you wrote; it never invents what's missing.

- **`slug: ClassVar[str]` is required.** The auto-derivation rule
  (strip `Router` suffix, lowercase) is removed; `_derive_slug` is
  gone from `src/a2kit/routers.py`. Missing slug raises `TypeError`
  at `Router.__init__` time naming the subclass. The legacy `name`
  constructor arg / `name` class attribute no longer drives the
  slug; leave `name` off or treat it as a plain attribute.
  Migration: add `slug = "<derived>"` to every Router subclass.
- **`tools: ClassVar[tuple[Callable, ...]]` is required.** The
  `dir(self)` walk in `Router._collect_methods` is gone. Each
  Router lists every `@a2kit.read/write/list_/tool`-decorated
  method in a tuple placed AFTER the method definitions in the
  class body. `Router.__init__` iterates the tuple, binds each
  entry via `getattr(self, fn.__name__)`, and stamps router-slug
  on the bound method's `_a2kit` meta. Missing meta on a listed
  entry raises `TypeError`; a decorated-but-unlisted method
  silently does NOT register (a follow-up lint rule will flag this
  drift statically). The instance-method `Router.tools()` is
  renamed to `Router.bound_tools()`; `RouterRegistry.tools()` →
  `RouterRegistry.bound_tools()`. `App.tools()` is unchanged.
- **`@reports(T)` folded into verb kwargs.** The standalone
  `@a2kit.packages.mcp.reports.reports(T)` decorator is gone;
  `a2kit/packages/mcp/reports.py` is deleted. Use the
  `reports=T` kwarg on `@a2kit.read/write/list_/tool` directly.
  `stage_extra` and `PENDING_EXTRA_ATTR` are removed from
  `a2kit.metadata`; verb decorators write the typed extras
  (`report_type`, `report_schema`, `list_view`) directly on
  `A2KitMetaExtras`.
- **`Router.install(self, app)` hook removed.** The
  `getattr(router, "install", None)` call site in
  `App.add_router` is deleted. Routers expose contracts via
  `slug` / `tools` / `providers` / `lifespan` only; anything the
  hook did belongs in `providers` or `lifespan`.
- **`Router.on_startup` / `Router.on_shutdown` auto-bridge removed.**
  The `App.add_router` loop that scanned `cls.__dict__` for these
  method names and registered them as App lifecycle handlers is
  gone. Routers expose lifecycle via a single
  `@contextlib.asynccontextmanager async def lifespan(self):`
  method. `App.add_router(r)` composes `r.lifespan` into the App's
  top-level lifecycle so the pre-`yield` body runs at startup (in
  `add_router` order) and the post-`yield` body runs at shutdown
  (LIFO). Composition uses a small in-App `AsyncExitStack` bridge
  that the sibling `lifespan-over-lifecycle-hooks` proposal will
  replace with `a2kit.lifespan.compose`.

Migration (per Router subclass):

```python
class TasksRouter(a2kit.Router):
    slug = "tasks"
    providers = (TrackerStore,)
    enrichers = (tracker_404_enricher,)

    @a2kit.read()
    async def get_task(self, *, store: TrackerStore, task_id: str) -> Task: ...

    @a2kit.write(reports=BatchReport)
    async def bulk_import(self, *, ctx: a2kit.ToolContext, ...) -> dict: ...

    @asynccontextmanager
    async def lifespan(self, *, store: TrackerStore):
        await store.open()
        try:
            yield
        finally:
            await store.close()

    tools = (get_task, bulk_import)
```

### Breaking — lifespan over lifecycle hooks (`lifespan-over-lifecycle-hooks`)

`@app.on_startup` / `@app.on_shutdown` are gone. The App accepts a
single `lifespan=` async-context-manager callable. FastMCP's `lifespan=`
slot is the canonical hook for this work; a2kit no longer maintains a
parallel handler registry.

- **`App(name, ..., lifespan=lifespan)`** accepts a callable returning
  an async context manager. Signature is fixed at exactly one
  positional parameter, the App instance:
  `async def lifespan(app: a2kit.App)`. The framework does NOT
  introspect the signature and does NOT auto-resolve typed kwargs.
  Resolve singletons inside the body via
  `await app.container().aresolve(T)`.
- **Sync `def` lifespans rejected at construction** with `TypeError`.
  Sync setup work goes inside the async body as plain statements.
- **`@app.on_startup` / `@app.on_shutdown` removed.** No shim.
- **`App.warm_async_singletons()`** is the explicit replacement for the
  implicit `@on_startup` warm-up of async-factory singletons. Call it
  from inside the lifespan body before `yield` when you want sync
  `container.resolve(T)` to see resolved values later.
- **`a2kit.lifespan.compose(*lifespans)`** composes multiple lifespans
  into one via `contextlib.AsyncExitStack`. Startup runs in declared
  order; shutdown unwinds LIFO. Each shutdown leg is shielded — an
  exception is logged at ERROR under `a2kit.lifecycle` with traceback
  and sibling legs continue to unwind.
- **`App.add_router(r)`** composes `r.lifespan` into the App's final
  lifespan via the same compose helper. The previous in-App
  `AsyncExitStack` bridge that the sibling `explicit-router-surface`
  shipped is now routed through `a2kit.lifespan.compose`.
- **FastMCP integration** — `build_mcp_server(app)` wraps
  `app.lifespan_cm()` in an adapter matching FastMCP's
  `lifespan(server)` slot. The adapter sets `server._a2kit_app = app`
  as a back-reference so middleware and other power-user code can
  recover the App from the FastMCP server.
- **Test client** — `a2kit.testing.client(app).__aenter__` enters
  `app.lifespan_cm()`; `__aexit__` exits it. Observable behaviour
  matches today; the underlying mechanism replaces `dispatch_startup` /
  `dispatch_shutdown`.
- **`dispatch_startup` / `dispatch_shutdown` removed** from
  `a2kit.app`. Public test harnesses that called them directly switch
  to `async with app.lifespan_cm():`.
- **Error message update** — `container.resolve(T)` on an unresolved
  async-factory singleton now directs callers to
  `await app.warm_async_singletons()` from the App's lifespan body
  (the message no longer mentions `@on_startup`).

Migration recipe (per call site):

```python
# Before
@app.on_startup
async def _open(state: AppState):
    await state.open()

@app.on_shutdown
async def _close(state: AppState):
    await state.close()

# After
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    state = await app.container().aresolve(AppState)
    await state.open()
    try:
        yield
    finally:
        await state.close()

app = a2kit.App("name", lifespan=lifespan)
```

For multi-component apps (App + several Router.lifespan
contributions), compose via:

```python
app_lifespan = a2kit.lifespan.compose(
    my_app_lifespan,
    router_a.lifespan,
    router_b.lifespan,
)
app = a2kit.App("name", lifespan=app_lifespan)
```

## 0.30.0 — drop docstring → param description auto-pull — 2026-05-12

### Removed

- **Google-style docstring → param description auto-pull** (shipped
  v0.29.0, refined v0.29.1). The regex-based `Args:` parser in
  `src/a2kit/_docstring.py` is deleted along with
  `_augment_annotations_from_docstring` in `src/a2kit/tool.py`.
  `_stamp` no longer mutates `fn.__annotations__` at decoration time.
- **`A2KitMeta.param_descriptions`** field (added v0.29.1) — was only
  populated from the now-removed parser.

### Migration

Tools that relied on docstring `Args:` blocks for parameter
descriptions must add explicit
`Annotated[T, a2kit.Param(description="...")]` or
`pydantic.Field(description="...")`. The v0.28 surface returns: those
two annotations are the only ways to attach parameter descriptions to
the MCP schema and CLI option help.

Tool-level descriptions (first docstring line + full body → MCP
description + CLI long-help) are unchanged.

## 0.29.1 — round-5/6 cleanup bundle — 2026-05-12

Two paired cleanups against round-5/6 contracts (no new features).

### Added

- `Container._override(type_, instance)` — test-seam method owning the
  three-attribute mutation (`_providers`, `_singletons`,
  `_async_factories`). `TestClient.override` delegates here, closing
  three `# noqa: SLF001` leaks.
- `A2KitMeta.param_descriptions: Mapping[str, str]` — Google-style
  `Args:` resolution is now stored on meta in addition to the existing
  `fn.__annotations__` mutation. Authoritative source for downstream
  middleware / introspection tooling.

### Changed

- LDD ctx binding is uniform across MCP / CLI / TestClient: none of
  them synthesize a fake context when a tool omits `ctx`. A no-ctx
  tool that calls `await a2kit.ldd.event(...)` raises
  `AmbientContextMissing` identically on every dispatcher (previously
  worked silently on CLI and TestClient).
- LDD shorthands (`a2kit.ldd.info/warning/error/debug`) surface their
  own name in `AmbientContextMissing` instead of the delegated-to
  `a2kit.ldd.log`.
- `_docstring.extract_param_descriptions` and the `get_type_hints`
  call in `_augment_annotations_from_docstring` log one WARN per
  qualname on parse / resolution failure (was silent
  `contextlib.suppress(Exception)`). Decoration still never raises.
- OPERATIONAL_CONTRACTS Q8 reworded: "active dispatch" is the
  conjunction of an `ldd_state_for_call` scope **and** a declared ctx
  param. Lazy singleton factories instantiated during dispatch may
  call LDD primitives (new paragraph + example).
- README testing section updated: `TestClient.override`,
  `call_wire`, async-singleton factories, ambient-LDD section,
  docstring-pull note. Migration bullet points at `TestClient.override`
  as the preferred test path.

## 0.29.0 — a2web round-5 + round-6 ergonomics — 2026-05-12

Five changes closing every open ergonomic gap from a2web feedback
rounds 5 and 6. Two are breaking; the rest are additive.

### Added

- **`app.singleton(T, async_factory)`** — singleton factories may now
  be `async def`. First resolution awaits via the new
  `container.aresolve` path; subsequent resolves return the cached
  instance synchronously. Concurrent first resolutions coalesce on a
  per-type `asyncio.Lock`. Replaces the hand-rolled double-checked-
  locking resource pattern (~80 LOC of boilerplate per a2web
  resource).
- **`TestClient.override(type_: type[T], fake: T)`** — type-safe DI
  override on the in-process test client. Snapshot/restore on the
  App's container; auto-cleans on `__aexit__` (normal or
  exceptional). Replaces ad-hoc `monkeypatch.setattr` patterns.
  Overlapping TestClient sessions on the same App raise
  `RuntimeError`.
- **`TestClient.call_wire(tool, **kwargs)`** — returns the
  formatter-encoded wire payload (JSON / TSV / page-tsv) instead of
  the Python value `invoke` returns. Reads the cached
  `descriptor.format_hint` so test-observed format and production
  wire format flip in lockstep when a tool's return annotation
  changes.
- **Docstring → param description auto-pull** — Google-style
  docstring `Args:` / `Arguments:` / `Parameters:` sections feed
  per-parameter descriptions into the tool's annotations at
  decoration time. Explicit `Annotated[T, a2kit.Param(...)]` /
  `pydantic.Field(...)` always wins. Numpy and Sphinx/reST formats
  are explicit non-goals.
- **`a2kit.exceptions.AmbientContextMissing`** — raised when an LDD
  primitive is called outside an active tool dispatch.

### Changed (breaking)

- **LDD primitives drop the `ctx` argument.** `a2kit.ldd.event`,
  `report`, `log`, `info`, `warning`, `error`, `debug`, and
  `EventRegistry.emit_typed` no longer accept `ctx`. They read it
  from the ambient `_LDD_STATE` ContextVar bound by the dispatcher
  for the lifetime of one tool invocation. Migration: drop the
  first positional argument at every call site. Calling outside
  an active dispatch raises `AmbientContextMissing` — fail loud,
  no silent no-op fallback.
- **`ldd_state_for_call(...)`** now takes a required keyword
  `ctx=...` argument. Tests that exercise LDD primitives directly
  (without a full tool dispatch) wrap with this — same seam the
  framework uses internally.

### Documentation

- `OPERATIONAL_CONTRACTS.md` Q8: LDD primitives require an active
  tool dispatch.

## 0.28.1 — FastMCP 3 `_meta` disable fix — 2026-05-12

### Fixed

- **`build_mcp_server` no longer crashes on FastMCP ≥ 3.0.** The
  per-tool `tool.disable()` call site was removed in FastMCP 3 and
  raised `NotImplementedError` on every `App(health_tool=True)`
  serve. Replaced with a single post-loop
  `server.disable(tags={"_meta"})` using FastMCP 3's visibility
  transform API; the `_meta` tag is already stamped on every
  `_meta.*` tool, so future additions inherit the rule.

### Changed

- `_meta.*` tools are now also rejected at `build_mcp_server`
  time (not just at decoration), closing the metadata-mutation
  bypass.

### Documentation

- `OPERATIONAL_CONTRACTS.md` Q7: the `_meta.*` tool namespace
  contract (closed namespace, MCP-hidden / CLI-visible split,
  rejection rule).

## 0.28.0 — a2kit.ldd.log primitive (Context-shape divergence repair) — 2026-05-12

`ctx.info("msg", k=v)` — the kwargs-emit pattern shown in
`examples/streaming_logger` and `examples/tracker` — crashed under real
MCP transport with TypeError, masked as "Error calling tool 'X'" under
`App(debug=False)`. `fastmcp.Context.info` has a narrow signature
(`message, logger_name=None, extra=None`); `StderrToolContext` had silently
widened it to `(msg, **fields)`, and the in-process test client hid the
divergence from every test path.

Repairs the contract by finishing the LDD free-function pattern that
`event` / `report` already used:

### Added

- **`a2kit.ldd.log(ctx, level, msg_or_instance, **fields)`** — plus
  `info` / `warning` / `error` / `debug` aliases. Both forms (string +
  typed instance) share the `_typed_event_to_payload` helper with
  `event`, so coercion rules can't drift.

### Changed (breaking)

- **`StderrToolContext.info/warning/error/debug` narrowed** to fastmcp's
  exact signature — kwargs form removed. Migrate to `a2kit.ldd.log(...)`
  or wrap kwargs in `extra=`.

### Test gate

- Two-axis contract test (`tests/test_context_surface.py`): name
  coverage (legacy) + signature-binding registry `CTX_CALL_SHAPES` (new,
  load-bearing). Every call shape in `tests/` + `examples/` binds
  against both Context impls.
- End-to-end repro (`tests/test_field_logging_mcp_path.py`) using real
  `fastmcp.Client(transport=server)` — today's bug fails this; new code
  passes.
- `ty check examples/` joins `make lint` (0 errors after migration, was 14).
- 723 → 728 tests (+2 MCP-path probes, +1 ldd kwarg render, +2
  architectural invariants).

Tier 2/3/4 of the Context-shape divergence (13 more drifting methods)
captured as follow-ups in `openspec/changes/align-context-method-signatures/`
and `openspec/changes/rebuild-test-client-on-real-context/`.

## 0.27.2 — CLI cold-start: schema gen no longer triggers mcp.types — 2026-05-12

The previous release deferred `mcp.types` from module-load time but `--schema`
still triggered it via `meta.annotations.model_dump(...)`. Schema generation
now uses the stored kwargs dict directly, skipping the pydantic build entirely.

### Added

- **`A2KitMeta.annotations_as_dict()`** — returns the annotation kwargs in
  `ToolAnnotations` wire shape without constructing the pydantic object.
  Used by CLI schema gen (`packages/cli/schemas.py`) and MCP wire projection
  (`packages/mcp/server.py:_meta_to_dict`). The lazy `meta.annotations`
  property is unchanged for consumers that genuinely need the typed object.

### Performance

CLI cold-start (median over 15 runs, M1 Mac):

| Scenario | v0.27.1 | v0.27.2 | Δ |
|---|---:|---:|---:|
| `<app> --help` | 138ms | 139ms | flat |
| `<app> tool ping` | 138ms | 137ms | flat |
| `<app> tool hello` (DI) | 139ms | 140ms | flat |
| `<app> tool ping --schema` | 612ms | 137ms | **-78%** |

All CLI paths now run in the 127-146ms band. The `mcp.types` import is
fully off the cold-start path; only `<app> serve` (MCP transport) pulls it.

## 0.27.1 — CLI cold-start: defer mcp.types import — 2026-05-11

CLI tool invocations (`<app> --help`, `<app> <router> <tool>`) now skip the `mcp.types` / fastmcp / anyio / httpx imports entirely. Cold-start drops ~75% on the common case.

### Changed

- **`A2KitMeta.annotations` is now a lazy property.** The verb decorators (`@a2kit.read/write/list_/tool`) store annotation kwargs in `_annotations_kwargs` / `_annotations_explicit` at decoration time; `meta.annotations` constructs the `ToolAnnotations` instance on first read. Behavior is unchanged from the consumer's view; the field is still readable as `meta.annotations`.
- **`a2kit.tool` no longer imports `mcp.types` at module load.** `ToolAnnotations` lives under `TYPE_CHECKING`; only consumers that read `meta.annotations` (MCP schema gen, `--schema` flag) pay the import cost.

### Performance

CLI cold-start (median over 25 runs, M1 Mac):

| Scenario | v0.27.0 | v0.27.1 | Δ |
|---|---:|---:|---:|
| `<app> --help` | 544ms | 138ms | -75% |
| `<app> tool ping` (no DI) | 510ms | 138ms | -73% |
| `<app> tool hello` (DI singleton) | 610ms | 139ms | -77% |
| `<app> tool ping --schema` | 669ms | 761ms | +14% (materializes annotations) |

`<app> serve` (MCP transport) is unaffected — it needs the full mcp stack.

### Notes

- No API breakage. `meta.annotations.readOnlyHint` still works exactly as before; first access lazily imports `mcp.types`.
- The MCP wire-output projection (`packages/mcp/server.py:_meta_to_dict`) updated to materialize the lazy annotations into the wire dict (transparent to consumers).

## 0.27.0 — DI sync + container relocation + DI-aware lifecycle (breaking) — 2026-05-11

This release shrinks the DI substrate, removes the `connection` magic name from core, and makes lifecycle hooks DI-aware. The container is now a small synchronous library that knows nothing about specific features. Async resource initialization moves out of DI factories into resource classes (lazy-init pattern, documented in README "Resource pattern" section).

### Breaking

- **`packages/connections/container.py` is gone.** The DI container lives at `a2kit.packages.di.Container`. All imports update: `from a2kit.packages.connections.container import Container` → `from a2kit.packages.di.container import Container`.
- **DI factories MUST be synchronous.** `app.singleton(T, async_factory)` and `app.provide(T, async_factory)` raise `ValueError` at registration. Move async opens into resource classes (see README "Resource pattern").
- **`Container.resolve` is synchronous.** The async `resolve` method and `resolve_sync` are both deleted; `SyncResolveUnavailable` is gone. There is one resolve method, sync.
- **`Container.resolve` no longer accepts `connection=`.** Connection-string resolution moves to a dispatch hook in `packages/connections/dispatch.py`. The container has no notion of "connection".
- **`Container.partition_kwargs` returns `(wire, injectable)` — two-tuple, not three.** `needs_connection` is gone; use the generic `Container.wire_scopes_used_by(fn)` instead.
- **Lifecycle handler signature changed.** Old `(app: App)` is removed. Handlers take typed DI kwargs (`async def _open(state: AppState)`); resolution happens through the container the same way `@health_check` does it. The legacy `_app` parameter is no longer supplied.
- **`App.container()` returns `Container` (non-Optional).** Drops the `is None` guards at every consumer site. Container is eager-initialized in `App.__init__`.
- **`App._reject_singleton_connection_dep` is gone.** The sync-only rule transitively rejects connection-dependent factories.

### Added

- **`a2kit.packages.di`** — new home for the DI container. Module is feature-agnostic; no `"connection"` or other feature names appear anywhere in its code (enforced by `test_container_source_has_no_feature_names`).
- **`Container.register_wire_scope(name, *types)` and `Container.wire_scopes_used_by(fn)`** — generic primitive for "wire-routed string parameters". Consumer packages register a scope by name; schema gen consults the container generically. `connections` registers `"connection"` as one such scope.
- **`Container.apply_kwargs(fn, wire, *, pre_resolved=None)`** — pre_resolved cache lets consumer dispatch hooks seed values that the container should treat as already-resolved (instead of calling the factory).
- **`a2kit.packages.connections.dispatch`** — async dispatch hook factory that awaits `store.load(connection)` and substitutes typed configs into the container's per-call cache before sync resolution runs.

### Migration

A2kit consumers (a2web etc.) migrate by:
1. Removing the `_app: a2kit.App` parameter from `@on_startup`/`@on_shutdown`; replace with the typed kwargs the hook actually needs (e.g. `state: AppState`).
2. Converting async singleton/provide factories to sync. Move the async resource open into the resource class itself (lazy-init pattern from README).
3. Removing `Optional` from resource handles on AppState; locks move inside resources.
4. Removing any `_app.container().resolve(AppState, connection=None)` dance from hooks; the DI is automatic.

### Notes

- ~600 LOC deleted across the container, app.py, and consumer surfaces.
- Container: 540 → ~200 LOC (still has chain resolution; was further deleted).
- Test count went from 716 (v0.26) → 719 with broader behavior coverage of the new dispatch path.

## 0.26.1 — a2web feedback round 4 (additive ergonomics) — 2026-05-11

### Added

- **Typed `a2kit.ldd.event(ctx, instance)`** — the free function now accepts
  a class instance as its second positional argument. Name defaults to
  `type(instance).__name__`; payload derives via `model_dump(mode="json")`
  (pydantic), `dataclasses.asdict` (dataclass), or `vars(instance)` fallback.
  `Enum` field values are coerced via `.value`. Optional `name=` kwarg
  overrides the default class-name on the typed path. The legacy
  `event(ctx, "name.string", **kwargs)` form is unchanged.
- **`a2kit.testing.null_context()`** — a no-op `ToolContext`-shaped shim for
  unit-testing internal phase functions that bypass
  `a2kit.testing.client(app)`. Every wire method (logging, progress, event
  emit, report, sample, list_*) is a silent no-op. Production code can take
  `ctx: a2kit.ToolContext` (non-Optional) and tests construct the shim instead
  of passing `None`.
- **`a2kit.Param("description")` positional shorthand** — equivalent to
  `a2kit.Param(description="description")`. Cosmetically shorter at the
  `Annotated[T, Param(...)]` call site for one-line descriptions. Passing
  both the positional and the `description=` kwarg raises `TypeError`.

### Notes

- Pure additive. No breaking changes. Consumers writing the typed-event
  flattener shim (a2web's `_event_payload`, ~25 LOC) can delete it.
- README sections "Per-parameter descriptions" and "Logging + progress +
  events + reports" updated to document the new shapes. New "Null context
  for internal phase tests" subsection under Testing.

## 0.26.0 — a2web feedback round 3 (router-as-plugin + Surface + LDD sinks) — 2026-05-11

### Added

- **`Router` is now the unit of installation.** Optional class attributes
  on a Router subclass — `providers = (...)`, `on_startup`/`on_shutdown`
  methods, and a custom `install(self, app)` hook — are honored by
  `app.add_router(r)`. There is no separate "plugin" type; one verb
  installs everything the Router declares. Plain Routers (tools only)
  behave exactly as before.
- **`a2kit.Surface`** — `Flag` enum (`CLI`, `MCP`, `ALL`). Pass to any
  verb decorator (`@a2kit.read(surfaces=Surface.CLI)`) to constrain
  which transports the tool mounts on. CLI builder and MCP server
  filter by `Surface` membership at mount time. Default `Surface.ALL`.
- **`a2kit.packages.connections.connections(*conn_types)`** — Router
  factory that installs typed providers honestly via `Router.install`.
  Use alongside the existing `connections_cli(...)` for the full
  surface: `app.add_router(connections(X)); app.add_cli(connections_cli(X))`.
- **`A2K-SURFACE-EXPLICIT` lint rule** — fires when a credential-named
  tool (`login`, `logout`, `auth_*`, `rotate_key`, `issue_token`, etc.)
  defaults to `Surface.ALL`. Suppress with explicit `surfaces=` kwarg.
- **`app.ldd.add_sink(sink)`** — register an in-process observer for
  every LDD emission (events and reports), on every transport. Sinks
  are async callables receiving an `LddEmission` payload (kind, name,
  payload dict, elapsed_ms, tool_name, ctx). Fan-out is sequential and
  best-effort; sink exceptions are caught and logged on `a2kit.ldd.sinks`.
  Replaces the double-emit pattern OTel/Datadog/audit-log integrations
  needed before.
- **`a2kit.ldd.LddEmission`** + **`a2kit.ldd.LddSink`** — public types
  for sink implementers.
- **OPERATIONAL_CONTRACTS Q2** rewritten with four prescribed
  `anyio.fail_after` patterns (single-budget, nested multi-stage,
  silent degrade with `move_on_after`, cleanup-on-timeout).
- **OPERATIONAL_CONTRACTS Q6** rewritten: heartbeat pattern for
  visibility during long phases, `add_sink` API documentation,
  cancellation contract for sinks. Cross-linked from
  `docs/SPIKE_LDD_CANCELLATION.md`.

### Changed

- **README leading example** switched to imperative composition; the
  fluent chain is now documented as a "shorthand for compact composition
  in tests and small scripts." Subsystem-crossing installs (router,
  CLI, providers, lifecycle) are visible line-by-line.
- **`examples/tracker/server.py`** ported to the canonical two-call form
  (`add_router(connections(X))` + `add_cli(connections_cli(X))`).

### Deprecated

- **Hidden auto-install of connection providers via
  `add_cli(connections_cli(X))`.** Emits `DeprecationWarning` pointing at
  the new two-call form. The auto-install path will be removed in v0.27.

## 0.25.0 — a2web feedback round 2 (test client + annotations + health + descriptions + ops contracts) — 2026-05-10

### BREAKING

- **Antipattern #1 lint broadened.** `_check_return` previously rejected only
  `-> str` returns; now also rejects `int`, `float`, `bool`, `bytes`, and
  `None` (both `type(None)` and the literal `None` annotation form). Tools
  must return a Pydantic model, dict, or list/Page of either. Pre-1.0
  latitude — fail-at-import is the loudest signal possible. Migration: wrap
  primitive returns in a typed shape (`-> dict[str, int]` instead of `-> int`).

### Added

- **`a2kit.testing.client(app)`** — async-context-manager test client that
  runs the **full dispatcher** in-process. Captures events, progress,
  logs, and reports for assertions. Lifecycle hooks fire. `render_as(fmt, val)`
  for wire-format checks. `tools()` for descriptor introspection.
  `connection=` passthrough through the same DI chain CLI/MCP transports use.
- **MCP `ToolAnnotations` kwargs on verb decorators** — `@a2kit.read` /
  `@a2kit.write` / `@a2kit.tool` accept `idempotent`, `open_world`,
  `destructive`, `title`. Conservative defaults (idempotent=False,
  open_world=False, destructive=False on read / True on write).
  `@a2kit.read(destructive=...)` raises `TypeError` — read tools are
  non-destructive by spec. Explicit `annotations=ToolAnnotations(...)` is
  the escape hatch.
- **`App(name, health_tool=False, debug=False)` constructor flags.**
  When `health_tool=True`, a built-in `_meta.health` tool is registered.
  `debug=True` enables tracebacks in error envelopes (currently flag-only).
- **`@app.health_check` decorator** — register sync or async readiness
  probes. Probes can take DI kwargs (resolved through the App's dispatch
  hook). Aggregates into `{status: "ok"|"degraded", version, checks: [...]}`.
- **`a2kit.HealthResult`** — `status: Literal["ok", "fail"]` + optional
  `reason`. Classmethods `ok()` / `fail(reason)`.
- **`_meta.*` reserved namespace.** User tools cannot claim names starting
  with `_meta.` — built-in protocol-meta tools (currently just `_meta.health`)
  own that namespace. Decoration-time `ValueError`.
- **`a2kit.Param(description=..., **extras)`** — annotation marker for tool
  kwargs. Returns a `pydantic.Field` info object so the description flows
  through `Annotated[T, Param(...)]` to both the MCP input schema (via
  pydantic) and click `--option HELP` text (via the CLI builder's
  `description_of` helper).
- **Docstring → tool description contract.** First non-empty line of the
  docstring becomes the tool's short description; the full PEP-257-dedented
  body becomes the long help. CLI strips markdown for terminal rendering
  (`_strip_md` handles `**bold**`, `*italic*`, `` `code` ``,
  `[text](url)` → `text (url)`). MCP forwards the body verbatim
  (markdown intact).
- **`OPERATIONAL_CONTRACTS.md`** — documented contracts for cancellation
  propagation (Q1), per-tool timeouts (Q2 — recommended `anyio.fail_after`
  pattern), multi-App isolation (Q3 — production-supported), dev auto-reload
  (Q4 — out of scope), error envelope (Q5 — MCP `-32603` / CLI traceback;
  `App(debug=True)` toggles wire traceback), streaming output (Q6 —
  deferred).

### Changed

- **`_build_descriptors` uses `meta.tool_name`** instead of raw
  `fn.__name__` — honors the decorator's `name=` override so tools with
  explicit names (like the built-in `_meta.health`) register under the
  intended descriptor name.

## 0.24.0 — fastmcp.Context passthrough + app lifecycle + DI ergonomics + return-type discipline (a2web feedback round 1) — 2026-05-10

### BREAKING

- **`a2kit.ToolContext` is now `fastmcp.Context`.** The narrow `ToolContext`
  Protocol that ran on a wrapper adapter is gone — tools that annotate
  `ctx: a2kit.ToolContext` now receive the live `fastmcp.Context` on the MCP
  transport, and a Context-shaped CLI stub on the CLI transport. The lazy
  `__getattr__` on `a2kit` resolves `ToolContext` to `fastmcp.Context` on
  first access (cold-start invariant preserved: bare `import a2kit` still
  doesn't pull fastmcp).
- **All Context logging methods are async.** `ctx.info` / `ctx.warning` /
  `ctx.error` / `ctx.debug` / `ctx.log` / `ctx.report_progress` are async on
  both transports (matching `fastmcp.Context`). Sync callers will silently
  produce a coroutine and log nothing — always `await` them.
- **`ctx.event(...)` and `ctx.report(...)` removed from the Context API.**
  These moved off the Context class and live as free functions in
  `a2kit.ldd`: `await event(ctx, "name", **payload)` /
  `await report(ctx, payload)`. Per-call state (kill-switches, declared
  report type) flows through a `contextvars.ContextVar` set by the runtime
  dispatch site, so the free functions Just Work on either transport.
- **`FastMCPContextAdapter` and `bind_context` deleted.** No public consumers
  in-tree; both were private wiring for the now-defunct adapter pattern.
- **`a2kit.runtime` module deleted** (it held the narrow Protocol).

### Migration

```python
# --- ctx logging methods are async now ---
async def my_tool(*, ctx: a2kit.ToolContext) -> dict:
    ctx.info("hello", count=3)            # before  (silent on MCP, sync on CLI stub)
    await ctx.info("hello", count=3)      # after   (works on both transports)

# --- ctx.event / ctx.report → free functions ---
from a2kit.ldd import event, report
async def my_tool(*, ctx: a2kit.ToolContext) -> dict:
    await ctx.event("import.started", n=10)         # before
    await event(ctx, "import.started", n=10)        # after

    await ctx.report(BatchReport(...))              # before
    await report(ctx, BatchReport(...))             # after

# --- typed event registry (new) ---
class StepStarted(BaseModel):
    step: int; total: int
app.ldd.events.register(StepStarted, progress=lambda e: (e.step, e.total))
async def run(*, ctx: a2kit.ToolContext):
    await app.ldd.events.emit_typed(ctx, StepStarted(step=1, total=3))

# --- a2web pattern (singletons + lifecycle) ---
def register_state(app, *, settings=None):
    state = AppState(settings=settings or get_settings(), ...)
    atexit.register(_atexit_close, state)
    app.provide(AppState, lambda: state)

# After
@app.singleton(AppState)
def _build_state():
    return AppState(settings=get_settings(), ...)

@app.on_startup
async def _open_resources(app):
    state = app.container().resolve_sync(AppState)
    state.sqlite = await open_sqlite(state.settings)

@app.on_shutdown
async def _close_resources(app):
    state = app.container().resolve_sync(AppState)
    if state.sqlite is not None:
        await state.sqlite.close()
```

### Cold-start budget note

- Bare `import a2kit` invariant unchanged: stays under 100ms with no fastmcp
  in `sys.modules` (the `Context` re-export is lazy via `__getattr__`).
- User-app `<app> --help` triggers fastmcp import on first access to
  `a2kit.ToolContext` from a tool annotation. Fastmcp's own import cost
  (~1s on a typical machine) dominates total wall-clock; the a2kit + click
  + builder overhead on top stays under 200ms (parametrized in
  `tests/test_cold_start.py::test_user_app_help_a2kit_overhead_under_200ms`
  across the streaming_logger, elicitation, and sampling examples).

### Added

- **`a2kit.ldd.event` / `a2kit.ldd.report`** — protocol-neutral free functions
  replacing the deleted `ctx.event` / `ctx.report` methods. Take any
  `fastmcp.Context`-shaped object as the first arg; route via the per-call
  `ldd_state_for_call` contextvar set by the dispatch site.
- **`a2kit.ldd.EventRegistry`** + **`app.ldd.events`** — typed event registry.
  Register Pydantic event models once (optionally with a progress callback);
  emit instances via `await app.ldd.events.emit_typed(ctx, evt)`. Handles
  `model_dump(mode="json")` (datetime → ISO etc.), routes through `event()`,
  forwards to `ctx.report_progress(...)` when a callback is registered.
  Re-registration is last-write-wins.
- **`a2kit.ldd.format_ldd_line(level, msg, fields, elapsed_ms)`** — single
  canonical LDD-line renderer used by both the CLI stub and any future
  transport. `TEXT_CAP=60` with `…` elision applied to `msg` on both CLI
  and the MCP `message` field.
- **`a2kit.signature.resolve_hints(fn)`** — single fallback for
  `get_type_hints` failures across the six core sites that previously rolled
  their own try/except. Logs WARN once per `__qualname__` on failure,
  returns `{}`. Cold-start preserving (no eager fastmcp import).
- **`StderrToolContext` full `fastmcp.Context` surface**: per-instance state
  (`set_state`/`get_state`/`delete_state`), `read_resource` (file:// only,
  text + binary), primitive `elicit` loop (str/int/float/bool/enum), and
  `MCPOnlyError` for `sample`/`list_resources`/`list_prompts`/`get_prompt`/
  `list_roots`/`send_notification`. `send_log_message` mirrors the MCP-side
  structured-log primitive.
- **`a2kit.packages.cli.context.MCPOnlyError`** — raised by the CLI stub for
  methods that have no client-side facility. Constructor: `(method, hint=None)`.
- **`examples/elicitation/`**, **`examples/sampling/`**, **`examples/typed_events/`** — three new examples + tests covering elicit on stdin, sample raising on CLI, and typed-event registry usage.
- **`A2K-LOCAL-RETURN-MODEL` lint rule** — static AST check that fires when a
  tool's return annotation references a `pydantic.BaseModel` subclass defined
  inside a function, classmethod, or closure (including generic carriers like
  `Page[Result]`, `list[Result]`). Skips `if TYPE_CHECKING:` blocks. Closes
  the gap where the rule was documented in `ANTIPATTERNS.md` but not actually
  shipped.
- **Decoration-time return-type-scope check** — `_check_return_scope` in
  `src/a2kit/tool.py` raises `InvalidToolReturnTypeError` at import time when
  a tool's return-type class has `<locals>` in `__qualname__` (the CPython
  signal for "defined in a function body"). Pairs with the lint rule for
  belt-and-suspenders coverage.
- **`a2kit.testing.peek(app, T)`** — one-line wrapper over
  `Container.resolve_sync(T)` for tests. Re-exported from `a2kit.testing` and
  `a2kit.packages.testing`.


- **`App.on_startup(handler)` / `App.on_shutdown(handler)`** — register async or
  sync lifecycle handlers invoked exactly once before the first tool dispatch
  / after the last. Both methods double as decorators (`@app.on_startup`).
  Startup runs in registration order; shutdown in reverse (LIFO unwind).
  Startup failures abort cleanly with no shutdown handlers run; shutdown
  failures are logged via `a2kit.lifecycle` (ERROR) and swallowed so the
  original exit reason is preserved.
- **`App.singleton(type_, factory=None)`** — register a factory whose result is
  cached on the App for its lifetime. Method form (`app.singleton(T, fn)`) and
  decorator form (`@app.singleton(T)`) both supported. Factories must NOT
  depend on `connection` (directly or transitively) — `singleton` raises
  `ValueError` at registration, naming the offending parameter or chain.
  Async factories are coalesced under a lazy `asyncio.Lock` so concurrent
  first-resolves await exactly once.
- **`App.has_singleton(type_)` / `App.singletons()`** — introspection mirrors
  parallel to `has_provider` / `container().providers()`. Unresolved entries
  carry the public sentinel `a2kit.UNRESOLVED`.
- **`Container.resolve_sync(type_, *, connection=None)`** — synchronous resolve
  for chains where every factory is sync. Raises `SyncResolveUnavailable`
  (with `async_link` naming the first async factory) if the chain hits async.
  Singleton-cached values short-circuit as sync regardless of original
  factory.
- **CLI lifecycle integration** — `a2kit.run(app)` invokes registered handlers
  inside the same `asyncio.run` that wraps the tool body, so resources opened
  in startup are bound to the loop the tool runs in (no fresh-loop dance).
- **MCP lifespan integration** — `build_mcp_server(app)` derives a `lifespan=`
  context manager from the App's handlers and merges with any user-provided
  `lifespan=` kwarg (a2kit-startup → user-enter → body → user-exit →
  a2kit-shutdown).

### Changed

- **`Container.resolve(connection=...)` is now optional** (was required
  keyword) — connection-less apps no longer have to pass `connection=None`
  everywhere. No behavior change for connection-using apps.
- **`a2kit.ldd.event` and `a2kit.ldd.report` first args are positional-only**
  (`async def event(__ctx, __name, /, **payload)`). Lets typed event payloads
  include keys like `name` / `ctx` without colliding. All existing callers
  pass these positionally already.
- **A2K-IMPORT-DISCIPLINE allowlist** extended to include
  `src/a2kit/packages/cli/context.py` (lazy fastmcp import inside `elicit()`).

### Removed

- **`a2kit.runtime` module** (held the narrow `ToolContext` Protocol).
- **`a2kit.packages.mcp.context`** module (`FastMCPContextAdapter`,
  `bind_context`).
- **`ctx.event(...)` and `ctx.report(...)`** methods on the Context API. Use
  `await event(ctx, ...)` / `await report(ctx, ...)` from `a2kit.ldd`.

## 0.23.0 — type-driven format routing: TSV / JSON / page-tsv (TOON dropped) — 2026-05-09

### Changed (BREAKING)

- **Type-driven format routing.** `format_hint="auto"` (the default) now
  consults the tool's pre-computed `ToolDescriptor.format_hint`, derived once
  at `app.add_router()` from the resolved return-type annotation. Tools
  declared `-> list[ScalarOnlyModel]` route to **TSV** (~30% fewer tokens than
  JSON for the dominant tracker shape — see K research R122). Tools declared
  `-> Page[T]` (where `T` is scalar-only) route to a hybrid **`page-tsv`**
  format: JSON envelope, embedded TSV string for `items`, with an
  `_items_format: "tsv"` discriminator. All other shapes (single models,
  dicts, scalars, untyped, `Union`, deep nesting) route to JSON.
- **TOON removed.** `format_hint="toon"` raises `ValueError`. The `toon`
  module, `encode_toon`, `toon_or_json`, the `toon-format` dependency, and
  the `TOONSnapshotExtension` syrupy helper are gone. Empirical R122 token
  benchmark (cl100k_base / o200k_base) showed TOON has no win zone — TSV beats
  it by 4-36% on tabular shapes; JSON beats it by 16-20% on shapes with list
  or nested-dict columns.
- `Page` is now `class Page(BaseModel, Generic[T])` (was `@dataclass`). Bare
  `Page(items=[...], next_cursor="x")` construction stays compatible.
  Subclasses can add fields naturally: `class SearchPage(Page[Task]): total: int`.
- `App.tool_descriptors() -> list[ToolDescriptor]` is the typed introspection
  surface. `App.tools()` continues to return bound callables for back-compat.

### Migration

- Tools already typed (`-> list[Task]`, `-> Page[Task]`) get the new behavior
  with no source change. Token counts drop on tabular outputs.
- Untyped tools route to JSON (no behavior change vs. the legacy `auto`
  fallback to JSON).
- If you depended on TOON output, switch to JSON. The benchmark shows JSON is
  cheaper on every shape where TOON was previously chosen.

### Fixed

- **CLI formatter renders pydantic `BaseModel` returns** in both JSON and TOON
  paths. Previously TOON emitted `null` (with an `Unsupported type` warning) and
  JSON fell back to `default=str` producing a quoted model repr; the MCP path
  worked because FastMCP normalizes pydantic itself. `format_response` now
  normalizes `BaseModel` (including models nested in lists/dicts) via
  `model_dump(mode="json")` at the formatter boundary before either encoder
  runs. Auto-format selection (`toon_or_json`) sees the normalized payload, so a
  model whose dumped form has list/dict fields correctly picks TOON. No-op for
  non-pydantic inputs (byte-identical output).

## 0.22.0 — ergonomic round: typed DI, consolidated list_, class-attr enrichers — 2026-05-09

Round three on top of v0.21's de-magic posture, focused on developer ergonomics
without re-introducing magic. Four wins, all expressible as plain Python:

- **`@a2kit.list_(*default_fields, page_size=None, selectable_fields=None)`** absorbs
  list-view projection settings. The standalone `@lists(...)` decorator and the
  `a2kit.packages.mcp.lists` module are removed. When `selectable_fields` is omitted,
  the framework derives it from the tool's `list[T]` return type — no redundant
  enumeration of fields the Pydantic model already declares.
- **Class-attribute `enrichers` + optional `def enrich(self, exc)` method** replace
  the per-method `@enriches(...)` decorator. The `a2kit.packages.enrichers` module
  is removed. Resolution: instance method first, then class list, first non-None
  return wins. Enricher functions now return `str | None` (the framework rebuilds
  the exception with the enriched message); the old `(exc, tool_name) -> Exception`
  shape is gone.
- **Request-scoped DI via `App.provide(T, factory=None)`**. A typed container in
  `packages/connections` resolves tool-method kwargs annotated with provider types
  (`store: TrackerStore`, etc.) per call. When `factory` is omitted, the class
  itself is the factory and the container introspects `__init__`. Tool authors stop
  writing `__init__(self, get_store: GetStore)` factories; routers can be parameterless.
  `add_cli(connections_cli(ConfigT))` auto-installs a typed provider for `ConfigT` —
  no second `provide(ConfigT, ...)` call required.
- **Hybrid Router slug derivation**. `class TasksRouter(a2kit.Router)` derives slug
  `"tasks"` automatically (strip a single trailing `Router`, lowercase). Explicit
  `name = "..."` still wins. Collisions across routers in one App raise at build
  time. The de-magic-2 antipattern entry on slug auto-derivation is retracted with
  new reasoning: a single documented suffix-strip rule is convention, not magic.

The agent-facing wire schema strips injectable kwargs (`store: TrackerStore` is not
in the MCP/CLI input schema) and auto-includes `connection: str` whenever the
injectable graph reaches the connection-config provider. Cold-start budget unchanged.

### Migration

```python
# Before (v0.21):
class TasksRouter(a2kit.Router):
    name = "tasks"

    def __init__(self, get_store: GetStore) -> None:
        super().__init__()
        self.get_store = get_store

    @a2kit.list_()
    @lists(default_fields=("id", "title"), page_size=20, selectable_fields=(...))
    @enriches(tracker_404_enricher)
    async def list_tasks(self, *, connection: str) -> list[Task]:
        store = await self.get_store(connection)
        ...

# After (v0.22):
class TasksRouter(a2kit.Router):
    enrichers = [tracker_404_enricher]
    # name auto-derived → "tasks"

    @a2kit.list_("id", "title", page_size=20)
    async def list_tasks(self, *, store: TrackerStore) -> list[Task]:
        ...

app = (
    a2kit.App("tracker")
    .add_router(TasksRouter())
    .provide(TrackerStore)                       # class-as-factory
    .add_cli(connections_cli(TrackerConfig))     # auto-installs TrackerConfig provider
)
```

## 0.21.0 — de-magic round 2: stacked decorators, lint-enforced core purity — 2026-05-09

Second pass at trimming framework magic from the v0.20 surface. The verb decorators
(`@a2kit.read/write/list_/tool`) drop their feature kwargs (`enricher=`, `list_view=`,
`report=`, `router_slug=`); each feature now lives in its own package and attaches
via a stacked decorator that writes into `A2KitMeta.extra`. The Router class no
longer derives slugs by string surgery, and the CLI builder no longer monkey-patches
`click.Group.main` or relies on a module-level `ContextVar`.

A senior-Python read of `src/a2kit/*.py` now finds no references to "connection",
"enricher", "list_view", "report_type", "report_schema", or "router_slug" — verified
by a new lint rule (`A2K-CORE-CLEAN`) that runs in CI as a hard gate.

### Decorator surface

- **`@a2kit.read/write/list_/tool`** accept only `(name, tags, annotations)`. The
  four feature kwargs are removed.
- **Stacked feature decorators** replace them. Order: verb decorator outermost,
  feature decorators below.
  - `from a2kit.packages.enrichers import enriches` — `@enriches(my_enricher)`
  - `from a2kit.packages.mcp.lists import lists, ListViewSettings` — `@lists(default_fields=..., page_size=...)`
  - `from a2kit.packages.mcp.reports import reports` — `@reports(BatchReport)`
- **`A2KitMeta.extra: dict[str, Any]`** is the single extension point. Feature
  decorators write namespaced keys (`a2kit.enricher`, `a2kit.list_view`,
  `a2kit.report_type`, `a2kit.report_schema`, `a2kit.router_slug`).

### Router naming

- `Router.slug` resolves to `name=` constructor arg → `cls.name` class attribute →
  `type(self).__name__` **verbatim**. No suffix stripping, no camelCase split, no
  case conversion.
- Routers without `name` set get an unsightly slug — that's the forcing function.
  The tracker example sets `name = "projects"` / `name = "tasks"` explicitly.

### Router internals

- `Router._collect_methods` walks bound members instead of `type(self).__dict__`.
  Tools register as bound methods; `_bind_if_method` and the consequential manual
  rebind are gone from the CLI builder.

### CLI builder

- `_wrap_main_with_app_ctx` deleted. `_APP_CTX` ContextVar deleted. The schema
  command and the lazy `serve` command are factories that close over the active
  `App` directly. `LazyGroup` now stores `Callable[[], click.Command]` factories
  instead of `module:attr` import strings.

### Connections

- `WriteNotAllowed` moves to `a2kit.packages.connections.exceptions` — it was the
  last connection-aware identifier in core. Core now grep-clean.

### Lint

- **`A2K-CORE-CLEAN`** (new, hard gate) — rejects feature identifiers in
  `src/a2kit/*.py` outside `packages/`.
- **`A2K-EXTRA-NAMESPACE`** (new, hard gate) — rejects `meta.extra[<key>] = ...`
  writes whose key isn't `a2kit.*` or a `<package>.*` prefix.
- **`A2K-LDD-REPORT-TYPE`** rewritten to look for stacked `@reports(ReportT)`
  rather than the dropped `report=` kwarg.

### Migration from 0.20

```python
# 0.20
@a2kit.read(enricher=my_enricher, report=BatchReport)
async def import_csv(self, *, ctx, file: str) -> dict: ...

# 0.21
@a2kit.read()
@enriches(my_enricher)
@reports(BatchReport)
async def import_csv(self, *, ctx, file: str) -> dict: ...
```

```python
# 0.20: from a2kit.exceptions import WriteNotAllowed
# 0.21: from a2kit.packages.connections.exceptions import WriteNotAllowed
```

```python
# 0.20: class TasksRouter(a2kit.Router): pass            # slug = "tasks" (auto)
# 0.21: class TasksRouter(a2kit.Router): name = "tasks"  # slug = "tasks" (explicit)
```

### Numbers

- Tests: 441 passing (was 428)
- Coverage: 93.52% (gate ≥92%)
- Cold-start: ~13ms (unchanged)

## 0.20.0 — protocol-agnostic core, plain-Python composition — 2026-05-09

Clean break from the v0.19 architecture. Core a2kit is a fat decorator on top of
FastMCP — `App`, `Router`, `@a2kit.read/write/list_`, `ToolContext` — and nothing
else. Connections, formatter, select grammar, lint, MCP/CLI adapters, testing
helpers, and OTel middleware live under `a2kit.packages.*` and load only when
imported. `import a2kit` measured at ~13 ms; FastMCP is confined to
`a2kit.packages.mcp`.

The release shipped through several intermediate spikes on `v1-thin-core`
(protocol-agnostic core, LDD streaming reports, class-based DI, pluggable plugin
architecture). The final shape collapses those experiments into the simplest
form that works: **constructor injection, three named composition verbs, no
sentinels, no plugin protocol, no class-as-key DI**.

### Composition

- **`a2kit.App(name)`** with three named verbs: `add_router(router)`,
  `add_cli(group)`, `add_mcp_middleware(middleware)`. No polymorphic dispatch.
- **`a2kit.Router`** is a plain Python class — pass factories via `__init__`,
  store on `self`, call from each tool method. The framework introspects
  nothing.
- **`a2kit.run(app, argv=None)`** — single console-script entry. Delegates to
  the lazy CLI builder; non-`serve` paths never load `fastmcp`.

### Verbs and metadata

- **`@a2kit.tool / read / write / list_`** stamp `A2KitMeta` (frozen
  dataclass) onto the function. Verb maps to `mcp.types.ToolAnnotations` +
  tags. Optional `enricher=fn` per-tool wraps the call in
  `try / except → enricher(exc, tool_name)`.
- **`@a2kit.read(report=ReportT)`** declares the typed mid-flight chunk type.
  `ctx.report(...)` validates against it; the schema dump exposes
  `reportSchema`.
- **`-> str` return** is rejected at decoration time
  (`InvalidToolReturnTypeError`) — return `dict` or a Pydantic model.

### `ToolContext` — four channels for mid-flight communication

- `ctx.info / warning / error / debug(msg, **kw)` — process telemetry.
- `await ctx.report_progress(i, n)` — numeric progress.
- `await ctx.event(name, **payload)` — typed narrative events.
- `await ctx.report(payload)` — typed result chunks (requires
  `report=ReportT` on the decorator).

All emissions carry an elapsed `+s.mmm` timestamp. CLI: `[ +s.mmm LEVEL] msg
key=val` on stderr. MCP: `notifications/message` with `data.elapsed_ms: int`
and a `data.a2kit_kind` discriminator.

**Kill-switch.** `--no-reports` / `--no-events` flags per invocation;
`app.set_ldd(reports=False, events=False)` programmatic; env `A2KIT_LDD=off`
process-wide. Most-specific layer wins.

### Connections

- **`a2kit.packages.connections`** exports `ConnectionConfig` (pydantic-settings
  base), `ConnectionStore` (load/save with eager `${VAR}` / `op://`
  substitution), and `connections_cli(*types)` — a Click-group factory you wire
  via `app.add_cli(connections_cli(TrackerConn))`.
- Eager substitution: `${VAR}` and `op://...` resolve at `store.load(...)`,
  not at first tool call. Round-trip preserves placeholders — `store.save(cfg)`
  writes the original `${MY_TOKEN}`, never the resolved value.
- No `Connections` plugin class. No `Store[ConnT]` Generic. No DI sentinel.
  Stores are plain classes; users wire factories explicitly.

### Adapters

- **`a2kit.packages.mcp`** — `build_mcp_server(app, **fastmcp_kwargs) -> FastMCP`.
  The ONE place fastmcp imports.
- **`a2kit.packages.cli`** — `build_full_cli(app)` returns the
  progressive-disclosure CLI (one entry per Router; `schema`, `serve`, plus
  any `add_cli(...)`-attached subcommands).
- Cold-start contract: after `import a2kit`, `'fastmcp' not in sys.modules`.
  Verified by `tests/test_cold_start.py`.

### Listview kit

- **`@a2kit.list_(list_view=ListViewSettings(default_fields=..., page_size=...,
  selectable_fields=...))`** declares the projection contract. Middleware
  applies projection / pagination / CEL-based filtering on the in-memory
  result post-hoc. `--fields=`, `--page-size=`, `--cursor=`, `--filter=`
  available at the call site.

### Filter syntax — real CEL

- **`a2kit.packages.select`** wraps `cel-python` for filter compilation. Users
  pass real CEL: `--filter='priority=="high" && !done'`. `&&`, `||`, `!`,
  comparisons, member access, ternary — all supported by the underlying CEL
  engine. Legacy atom syntax is gone.

### Output formatter

- **`a2kit.packages.formatter`** — TOON / JSON normalization via `toon-format`.
  Default is TOON (token-efficient for agent contexts); pass `--format=json`
  to opt in. `--format=auto` heuristically picks JSON for flat dicts, TOON
  otherwise.

### Lint

- **`a2kit lint static <path>`** — AST-only rules, no imports of user code.
  Active rules: `A2K002`, `A2K003`, `A2K006`, `A2K008`, `A2K009`, `A2K011`,
  `A2K012`, `A2K013`, `A2K014`, `A2K-CONN-LIST-PLACEHOLDER`,
  `A2K-IMPORT-DISCIPLINE`, `A2K-LDD-REPORT-TYPE`.
- **`a2kit lint runtime --import pkg:server`** — duck-typed checks on a built
  server (snapshot presence, per-tool budgets, similar-name detection).
- **`make lint` is a hard gate** for `ruff check`, `ruff format --check`,
  `ty check src/`, and `a2kit lint static`. The repo carries zero
  `# ty: ignore` comments — verified by `tests/test_type_correctness_gate.py`.

### Testing

- **`a2kit.packages.testing`** ships an `app` fixture (returns
  `a2kit.App("test")`), a `cassette` fixture (vcrpy wrapper),
  `TOONSnapshotExtension` (syrupy single-file extension), and
  `compute_schema(fn)`. There is no `make_test_app` helper — tests construct
  an `App` and call `add_router(...)` directly.

### Optional OTel adapter

- **`a2kit.packages.otel`** (install with `pip install 'a2kit[otel]'`) —
  middleware that wraps every tool call in a `mcp.tool.{name}` span and
  increments an `a2kit.tool.calls{tool, verb, status}` counter. Wire via
  `from a2kit.packages.otel import install; install(server)`. Lazy: a2kit
  core does not import `opentelemetry` at any point.

### Migration from v0.19

The v0.19 architecture is gone. Notable shape changes:

| v0.19 | v0.20 |
|---|---|
| `from a2kit.di import Depends` / `from uncalled_for import Depends` | constructor injection on `Router.__init__` |
| `Annotated[T, Depends(g)]` parameter | factory passed to router constructor |
| `*, conn: T = Depends(g)` parameter default | factory passed to router constructor |
| `app.run()` | `a2kit.run(app)` |
| `app.dependency_overrides[fn] = fake` | `App() + add_router(R(fake_factory))` |
| `make_test_app(routers, overrides=...)` | `App() + add_router(...)` directly |
| `from a2kit.contrib.connections import ...` | `from a2kit.packages.connections import ...` |
| `from a2kit.scaffold import Router` | `from a2kit import Router` |
| `from a2kit.testing import ...` | `from a2kit.packages.testing import ...` |
| `from a2kit.formatter import ...` | `from a2kit.packages.formatter import ...` |
| Lazy `${VAR}` / `op://` | Eager (resolves at `store.load(...)`) |
| Legacy filter atom syntax | Real CEL (`&&` / `\|\|` / `!`) |

### Install note

`toon-format` 1.0 has not yet shipped; v0.20 pins the working pre-release
exactly. Pass `--pre` if a fresh resolve bypasses the pin:

```bash
uv pip install --pre 'a2kit'
```

## 0.19.0.dev0 — 2026-05-08

**Fix-forward review pass on the v0.15 architecture.** No surface
changes; addresses two latent bugs and sweeps documentation drift.

### Latent bugs fixed

- **Multi-`ConnectionConfig` Depends params are now rejected at
  decoration time.** A tool declaring two `Annotated[T, Depends(...)]`
  params resolving to `ConnectionConfig` subclasses previously
  silent-picked the first one for `WriteEnforce` / OTel correlation.
  Raises `TypeError` with a clear message.
- **`connection=` shape now normalized through OTel / structlog.** A
  caller passing `connection=("p","e","d")` or
  `connection=["p","e","d"]` put the raw shape onto
  `ctx.state[STATE_CONNECTION_KEY]`, which then serialised
  inconsistently. Routed through `_resolve_connection_key` before
  stash so the span / log record always sees the canonical tuple form.

### Surface vestiges removed

- **`store=` parameter dropped end-to-end** from
  `Router.register_read` / `register_write`, the
  `_RegisterableRouter` Protocol, `Router._apply_bindings`, and
  `RouterRegistry.apply`. Routers stopped owning per-router stores in
  v0.15; this kept threading `store` through dead code paths.
  *Migration:* anyone with a hand-rolled Router implementing the
  structural `_RegisterableRouter` Protocol must drop the `store`
  parameter from `register_read` / `register_write` / `register_list`
  signatures. The framework no longer passes it.
- **`RouterRegistry.routers_with_stores(fallback_store=...)` →
  `ephemeral_store_pairs(store)`.** Renamed to spell out the actual
  purpose (the only consumer is the `--register` CLI path; nothing
  Router-owned).
- **`_CURRENT_RUNNER` ContextVar deleted** — only ever written, never
  read.

### Public API hardening

- **`App.get_store(conn_type) -> ConnectionStore[T]`** is the public
  store-lookup hook. Replaces `app._stores` private-attribute poking
  from `contrib/connections/_factory.get_conn_factory`. Match is
  exact-class identity, not `isinstance`.
  *Migration:* third-party contrib factories should replace
  ``next(s for s in app._stores if s.connection_class is T)`` with
  ``app.get_store(T)``. Subclasses of a registered conn type don't
  resolve to the parent's store — each class owns one store.

### Documentation drift

- Module docstrings rewritten for the v0.15+ surface
  (`a2kit/__init__.py`, `contrib/connections/__init__.py`,
  `contrib/connections/_helpers.py`, `tools/_connection.py`).
- **`a2kit.contrib.connections.make()` placeholder deleted** — it
  returned an unconsumed tuple and only existed as a syntax stub for
  an unbuilt SubApp surface. Migration note in `todo.md`.

### Tests

- Coverage stays at 100% (cov-fail-under=100 enforced).
- `tests/test_v19_latent_bugs.py` covers the two latent fixes.
- `tests/test_decorator_v15.py` listview / Passthrough assertions
  tightened (typed exception + Response shape).

## 0.18.0.dev0 — 2026-05-08

**Structured tool logging.** Adds `a2kit.get_tool_logger(name)` — a
structlog `BoundLogger` that shares the same `tool.name` /
`tool.connection` labels the OTel span carries, by reading them from
`structlog.contextvars`. A new logging middleware binds those keys for
the duration of each tool call (both async-chain and sync `@tool`
paths), so any log emitted from the tool body, plugin code, or
downstream middleware inherits the labels. Concurrent tool calls stay
isolated (per-task contextvars).

What's *not* in scope: trace_id/span_id injection into log records.
The kit binds labels only — for full trace correlation, hosts bridge
structlog→stdlib logging and enable OTel `LoggingInstrumentor`
themselves. The kit ships **no** structlog *configuration*
(processors, formatter, handler) for the same reason. structlog
imports are lazy.

(Plan-vs-impl note: the v0.17 ledger called the type a "structlog
`LoggerAdapter`" — that was a stdlib/structlog conflation. structlog's
`BoundLogger` is the actual contextvar-aware shape and is what shipped.)

`structlog>=24` added to runtime dependencies.

### FastMCP request-id spike — closed

Investigation: `Context.request_id` exists on FastMCP's Context but is
only injected when the tool declares a `Context`-typed kwarg.
Stamping it as `mcp.request_id` on the span would force a2kit to
import `mcp.server.fastmcp.Context` at runtime — contradicting the
v0.11 `FastMCPLike` Protocol design. Closed; finding + follow-up paths
captured in `todo.md`.

## 0.17.0.dev0 — 2026-05-08

**Hygiene.** v0.17 audits the pre-v0.13 P1/P2/P3 backlog (most items
turned out stale or already-landed), executes the surviving real items
(formatter robustness + Hypothesis property tests + OTel
`tool.result.count`), and deletes the v0.16 `ConnectionInfo` alias.

### Backlog audit

`todo.md` P1/P2/P3 sections (lines 26-72, captured pre-v0.13) honest
again — every item is checked, struck stale, or surviving-and-current.
The v0.13–v0.15 surface deletes invalidated most P3 items
(`tools.py`, `_RouterContext`, `MCPRunner.store=`, `_auto_inject_enabled`,
typed-info DI all gone). The async store API, `MCPRunner.run_async`,
`EnricherFn` async support, and OTel `record_exception` already landed
in v0.11–v0.13.

### Formatter robustness (P1)

- **`_dump_items` raises on non-row items** instead of silently dropping
  them. Pre-v0.17 behaviour turned `[1, 2, 3]` into `[]`, masking
  row-shape bugs. `format_response` gates the call to only normalize
  when `data[0]` is a `dict` / `BaseModel`; heterogeneous lists now
  fall through to the JSON path.
- **`format_from_annotation` unwraps `Awaitable[T]` / `Coroutine[Y, S, T]`**
  before classifying — async tools no longer lose precomputation.
- **Bare `dict`, `Mapping[K, V]`, `TypedDict` subclasses** classify as
  `"json"` (previously fell through to `None`).
- **`_flat_pydantic_fields` handles multi-arm `Optional[Union[A, B]]`**.
  Previously only single-arm Optional was unwrapped; multi-arm fell
  through. New `_classify_arm` helper inspects each non-None arm.

### OTel observability (P2)

- **`tool.result.count` span attribute** — stamped by the OTel
  middleware when the tool returns `list` / `tuple` / `Page[T]`.
  Cardinality only — PII-safe and stamped after success only
  (meaningless on error).

### Property tests (Hypothesis)

- `truncate(value)` is structural identity at high `max_chars` and
  never mutates input — verified against a recursive value strategy
  (atoms / lists / dicts up to depth 4).
- `format_from_annotation(list[FlatModel])` precompute agrees with
  `toon_or_json` runtime classification.
- `hypothesis>=6` added to dev deps; 25 new tests in
  `tests/test_v17.py`.

### Deleted: `ConnectionInfo` alias

v0.16 added `ConnectionInfo = ConnectionConfig` as a one-cycle alias
with an explicit "delete in v0.17" plan. Done.
`src/a2kit/lint/_ast_helpers.py` no longer recognises the old name;
all tests + the tracker example use `ConnectionConfig` directly.
`ConnectionInfoLike` Protocol stays — it's a structural type and the
rename pressure doesn't apply.

### Tests

- 589 tests (564 → 589), 100% coverage.
- `make lint && uv run pytest -q && make examples` green.

## 0.16.0.dev0 — 2026-05-08

**Polish.** v0.16 closes the v0.15 coverage drop, renames the
long-deprecated `ConnectionInfo` → `ConnectionConfig`, and scrubs the
README of stale `Plugin` / `Provider` / `store=` references.

### Coverage refill: 80% → 100%

- ~290 focused tests in `tests/test_v16_coverage.py` covering the
  formatter decision tree, lint AST helpers + rule branches, `app.py`
  CLI body, projection / `_otel` / signature splicing, scaffold runner
  pyproject loaders, `ConnectionStore` edge cases, and enricher
  sync/async drain.
- `cov-fail-under` bumped back to `100` in `pyproject.toml`.
- A handful of genuinely-defensive branches got `pragma: no cover`
  (the optional celpy ImportError, the OTel real-provider fallback,
  the 3rd-tier anyio drain in `apply_enricher_sync`, a few rare
  branches in `_compute_tool_capabilities`).

### `ConnectionInfo` → `ConnectionConfig`

The class lives in `src/a2kit/connections.py` and is now
`ConnectionConfig`. `ConnectionInfo` remains as a module-level alias
for one cycle (removed in v0.17). All internal references — TypeVars,
contrib factory, scaffold CLI/stores, lint helper base-class
string-match — updated. The lint AST helper recognises both names so
user code on the alias still satisfies A2K003 / A2K012 detection.

### README scrub

- Status header rewritten to describe the v0.16 surface (was v0.13).
- API surface table adds `App`, `Depends`, `get_conn_factory`, the
  verb decorators (`@a2kit.read` / `@a2kit.write` / `@a2kit.list`).
- "How a new MCP starts here" walkthrough rewritten around `App` +
  `Annotated[ConnT, Depends(get_conn)]`.
- All v0.7-v0.12 migration footnotes (`*, info: ConnT`,
  `connection_param=`, `Router.store=`, `MCPRunner.store=`,
  `Plugin`/`PluginBase`/`Provider`) collapsed into a CHANGELOG
  pointer.
- `MCPRunner(server, store=store)` examples updated to the v0.15
  `connection_store=` kwarg name.

### Tests

- 564 tests, 100% coverage.

## 0.15.0.dev0 — 2026-05-08

**The big delete.** v0.15 collapses two years of v0.7→v0.12 connection-DI
vocabulary into the single `Annotated[T, Depends(factory)]` idiom. Breaking
compat; no deprecation footnotes.

### New surface

- **`a2kit.contrib.connections.get_conn_factory(app, ConnT)`** — the
  canonical Annotated/Depends factory for connection injection. Returns
  a callable matching the `Depends(...)` factory shape (declares
  `connection: str` as a kwonly so the resolver forwards the call-site
  value). Tests override via `app.dependency_overrides[get_conn] = fake`.
- **WriteEnforce middleware wired automatically.** Tools decorated with
  `@write` (or `write=True`) get the `write_enforce_factory()` middleware
  in their implicit chain — read-only connections raise `WriteNotAllowed`
  before the tool body runs.
- **Transitive `connection` kwarg surfacing.** When a tool declares
  `Annotated[Store, Depends(get_store)]` and `get_store` depends on
  `Annotated[Conn, Depends(get_conn)]`, the wrapper walks the chain and
  exposes `connection: str` on the published signature.

### Removed (breaking)

Tool decorator:

- `connection_param=` kwarg.
- Typed-info DI autodetect (`*, info: ConnT`); `_detect_info_param` helper.
- `store=`, `connection=`, `resolver_registry=`, `router_context=` kwargs.
- Connection-aware branches in `_prelude` / `_prelude_async`. Async
  prelude is now 16 LOC — only `tool_call_guard` remains.

DI container (`a2kit.di`):

- `Provider`, `Plugin`, `PluginBase`, `Binding`, `ToolPlan`.
- `ProviderCollisionError`, `ProviderCycleError`,
  `UnknownProviderTypeError`, `UnknownProviderDepError`.
- `resolve_chain`, `_validate_provider_graph`, `_provider_dep_types`.

Runner:

- `provides=` and `plugins=` kwargs.
- `store=` kwarg → `connection_store=`; public `MCPRunner.store`
  attribute is now private `_connection_store`.
- `lookup_provider`, `resolve`, `cli_commands`.

App:

- `App.use(Plugin)` / `App.use(Provider)` arms.

Router:

- `Generic[ConnT]` parameterisation.
- `store`, `resolver_registry`, `ephemeral`, `auto_connection_enricher`
  fields.
- `Router.context` ClassVar + `_RouterContext` (`_context.py` removed).

Lint:

- A2K001, A2K004. Both checked features that no longer exist.

Misc:

- `_safe_list_connection_keys` (decoration-time saved-key listing).

### Tests

- 11 version-stamped legacy test files deleted (~5800 LOC):
  `test_v03/v031/v04/v06/v07/v08/v10/v11/v12.py`, `test_tools_fat.py`,
  `test_exceptions_v02.py`.
- Added: `tests/test_app_use.py` and `tests/test_decorator_v15.py` cover
  Annotated/Depends end-to-end (saved-conn round-trip, overrides,
  transitive deps, WriteEnforce, CLI shape).
- Final: 290 tests, 80% coverage. `cov-fail-under` temporarily relaxed
  to 0; deferred 100% restoration to v0.16.

### Migration

```python
# v0.14
@MyRouter.read()
async def list_them(*, conn: TrackerConn) -> list[dict]: ...
```

```python
# v0.15
from typing import Annotated
from a2kit.di import Depends
from a2kit.contrib.connections import get_conn_factory

app = a2kit.App("tracker")
app.connect(TrackerConn)
get_conn = get_conn_factory(app, TrackerConn)

@MyRouter.read()
async def list_them(*, conn: Annotated[TrackerConn, Depends(get_conn)]) -> list[dict]: ...
```

`examples/tracker/` is the canonical reference; `examples/tracker/deps.py`
shows the slot pattern that keeps routers decoupled from the `App` instance.

## 0.14.0.dev0 — 2026-05-08

**Polish turn (in progress).** v0.14 picks up the v0.13 deferred backlog;
this dev cut lands two cleanup commits and adds App-scope enricher
plumbing. The big v0.12 connection-surface deletion (`Router.store`,
`MCPRunner.store=`, `connection_param=`, `_detect_info_param`,
`Plugin`/`PluginBase` Protocols, `Router(BaseModel, Generic[ConnT])`)
remains carried over and is the next shaping target — see `todo.md` for
the v0.14 ledger.

### New surface

- **`App(name, enricher=...)`** — App-scope enricher fallback. Resolution
  order at the binding layer is `tool > router > app`, with the existing
  `auto_connection_enricher(store)` as the implicit floor. Routers
  without their own `enricher=` inherit the app's at apply time.

### Removed

- **A2K005** lint rule (`KEY_FIELDS` migration aid + `cls.Key` arity
  cross-check). Carried since v0.5; the legacy `KEY_FIELDS` syntax is
  long gone. Drops `key_fields_value`, `connection_info_key_class`,
  `namedtuple_field_count`, `connection_info_subclasses` AST helpers
  alongside it. ~800 lines net deletion (src + tests + docs).

### Deferred to v0.15

- **`ConnectionInfo` → `ConnectionConfig` rename** — Pydantic schema
  name + error-message ripple across the test corpus exceeded session
  budget; documented for next cycle.
- **Hard delete of the v0.12 connection surface** (the headliner). All
  nine items (`Router.store`, `MCPRunner.store=`, `connection_param=`,
  `_detect_info_param`/`info_target`, `_prelude_async` connection
  branch, `Router(BaseModel, Generic[ConnT])` TypeVar, `Plugin` /
  `PluginBase` Protocols, `Provider` Protocol, `App.use()`'s Plugin
  arm) are interlocked with ~117 `connection_param=` test sites and
  31 `Plugin`/`PluginBase` references; doing them as one coordinated
  migration is its own multi-session pitch.
- **`SubApp` / `app.mount(...)` shape + `connections.make()` real
  SubApp.** Parked behind the surface deletion above.
- **`PLC0415` per-file ignore in `tests/**`.** 123 hits across the
  test corpus; non-trivial migration left for a focused commit.

## 0.13.0 — 2026-05-08

**Library-swap turn + middleware split.** Replaces three bespoke modules
with their stdlib / OTel / vcrpy equivalents, introduces `Annotated[T,
Depends]` DI alongside the v0.12 `provides=` path, splits the fat tool
decorator into a middleware chain, and lifts connection-aware logic into
`a2kit.contrib.connections` so the core decorator no longer knows what a
ConnectionInfo is.

### New surface

- **`Annotated[T, Depends(factory)]` DI** — FastAPI/FastMCP idiom for
  per-tool typed dependencies. `*, store: Annotated[TodoStore,
  Depends(get_todo_store)]` resolves at call time with per-call caching
  and cycle detection, validated at decoration.
  `app.dependency_overrides[get_conn] = fake` swaps factories in tests.
- **`Depends(factory)`** — frozen dataclass marker re-exported from the
  top-level `a2kit` namespace. Lives next to the v0.12 `Provider`
  Protocol; pick the shape that fits the call site.
- **Implicit middleware chain** (`a2kit.middleware`) — the tool decorator
  now assembles a Starlette-style chain at decoration time:
  `tool_call_guard` → `capability_guard` → `otel_span` (always); plus
  `write_enforce`, `list_view_apply`, and `enrich_errors` only when the
  verb / Router / connection asks for them. Authors keep writing
  `@MyRouter.write()` — the chain is implicit. Hooks for
  `@MyRouter.write(middleware=[mw])`, `Router.middleware = [...]`, and
  `App.middleware = [...]` exist for the rare tier-3 case.
- **`a2kit.contrib.connections`** — connection-aware helpers
  (`lookup_connection_async`, `resolve_connection_key`,
  `resolve_info_strings`, `write_enforce_factory`) live in their own
  contrib package. The v0.13 plan ("pull connections out of core") is
  partially landed — re-exports keep v0.12 paths working; v0.14 deletes
  the legacy paths and finishes the SubApp / `connections register`
  CLI subcommand work.
- **`RunnerOptions`** — typed dataclass for `MCPRunner.run(options=...)`.
  Replaces argv-string round-tripping in `App.cli`'s `serve` subcommand;
  `argv=` stays as a v0.12 compat layer.

### Library swaps

| Concern | Before | After |
|---|---|---|
| Sync→async drainage | `a2kit._async_bridge` (18 LOC) | `anyio.from_thread.run` direct |
| OTel NoOp fallback | `_otel.py._NullSpan` (~150 LOC) | `opentelemetry.trace.NoOpTracer` |
| VCR cassettes | `_cassette.py._make_async_ctx` (~40 LOC) | `vcrpy` direct |

Net delete: ~200 LOC of bespoke wrappers that re-implemented stdlib /
upstream-library shapes.

### Deferred to v0.14

- **`_select*.py` → `cel-python`.** Probed; structural blockers in
  user-facing grammar (`and`/`or` vs `&&`/`||`, atom keys with dots)
  and the `SelectExpr` AST consumed by lint rules and scaffold
  introspection (~100 references). Re-open as a dedicated pitch.
- **`tokens.py` → `pydantic-settings` + `pyonepassword`.** Mismatched
  abstractions (`resolve_env` substitutes inside arbitrary strings;
  `pydantic-settings` is a typed settings-model loader); zero-LOC
  savings on the op:// side.
- **Core deletes that touched 30+ test sites.** `Router.store`,
  `MCPRunner.store=`, `connection_param=`, the `_prelude_async`
  connection branch, `_detect_info_param` / `info_target` plumbing,
  `Router(BaseModel, Generic[ConnT])`, and the `Plugin` / `PluginBase`
  Protocols all stay as v0.12-compat surfaces. v0.14 will migrate the
  test corpus to `Annotated[Conn, Depends(get_conn)]` then delete the
  compat code in one pass.
- **`PLC0415` removal from `tests/**`.** The audit halved the noqas in
  `src/` (49 → 25); the remaining 25 are genuine optional-dep / circular
  / verb-decorator factory cases. The test corpus has 123 PLC0415 hits —
  non-trivial migration deferred.

### Coverage

Restored to **100%** (`cov-fail-under=100`). The two v0.12 holes
(`enrichers.py:108`, `tools/_signature.py:113`) plus three drive-by
gaps from the middleware split now have direct tests.

## 0.11.0 — 2026-05-08 (in progress)

**Contract-clarity turn.** Tightens the public vocabulary, restores type
safety on the most-used classes, and exposes a stable accessor for tool
metadata. No new behaviour — the engine is untouched. Existing v0.10 tools
keep working without changes.

### New

- **`a2kit.enrichers`** is the canonical home for `EnricherFn`,
  `chain(*fns)`, and `connection_enricher(store)`. The previous module
  `a2kit.errors` is now a deprecation shim that re-exports from `enrichers`
  and warns at import. Scheduled for removal in **v0.13**. Update imports:
  `from a2kit.enrichers import ...`. The clarification: `a2kit.exceptions`
  holds exception *classes*, `a2kit.enrichers` holds enrichment *functions*.
- **`ConnectionInfoLike` / `ConnectionStoreLike`** moved to their natural
  home `a2kit.connections` (still re-exported from the deprecated
  `a2kit.errors` for one cycle, and from the top-level `a2kit` namespace).
- **`FastMCPLike` Protocol** in `a2kit.scaffold` — the minimum FastMCP server
  surface `MCPRunner` drives (`tool()`, `run()`, `settings`). Use it to type
  your own server wrappers / mocks. Runtime-checkable.
- **`tool_metadata(fn)` → `ToolMetadata`** — public, frozen, slotted accessor
  for the kit-stamped `_a2kit_*` attrs (`tool_name`, `capabilities`,
  `format`). Tests and consumers should assert against `ToolMetadata`, not
  the underlying private attributes.

### Changed (typing — no runtime behaviour change)

- `Router.store / .enricher / .resolver_registry / .ephemeral` are now
  typed (`ConnectionStoreLike | None`, `EnricherFn | None`,
  `ResolverRegistry | None`, `Mapping[tuple[str, ...], ConnectionInfo] | None`)
  instead of `Any`. Pydantic still accepts these — `arbitrary_types_allowed=True`
  was already set — but ty / IDEs now see the real shape on every consumer.
- `MCPRunner.__init__(server, store=...)` accepts `FastMCPLike` and
  `ConnectionStore[Any] | None` instead of `Any`.
- `RouterRegistry._routers` entries are now `_RouterEntry` NamedTuples
  instead of bare 3-tuples — internal cleanup, no API change.
- `Page[T]` docstring locks the convention: `T` is `BaseModel` (preferred —
  enables tsv/toon precompute) or `dict[str, Any]` (ad-hoc rows). The
  TypeVar bound is left off because Pydantic v2 generic-bound interplay
  with `Page[dict[...]]` is fragile.
- `next_cursor` documented as an opaque agent-only string (the kit never
  parses or interprets it).

### Removed

- **`a2kit.A2KIT_CONFIG_HOME`** — was a self-alias for `ENV_CONFIG_HOME`.
  Use `a2kit.ENV_CONFIG_HOME` instead. `a2kit.A2KIT_CONFIG_HOME` now raises
  `ImportError` with a migration hint.

### Deprecated

- **`a2kit.errors` module** — emits `DeprecationWarning` at import. Removed
  in v0.13.

### Compatibility

- All v0.10 tests pass unchanged. 618 tests, 100% coverage, ruff + ty clean.
- Test fakes for `FastMCPLike`-typed args may need to add a `tool()` method
  if they didn't have one (most fixtures already do for FastMCP parity).

## 0.10.0 — 2026-05-07

**Surface-simplification turn.** Four targeted wins, all additive over v0.9:
the wire format is decided at decoration time when possible, `Page[T]` of
Pydantic models actually serialises to TSV/TOON, every Router with a store
gets the typo-suggestion enricher for free, and the agent-facing
`connection: str` schema lists the saved keys it knows about.

### New

- **Format-from-type at decoration time.** When the tool's return type is
  concrete (`list[Issue]`, `Page[Issue]`, `dict`, `Issue`, `int`, …), the kit
  precomputes the wire format (`tsv` / `toon` / `json`) once. Each call skips
  the runtime list-of-dicts walk. Stamped on the wrapper as `_a2kit_format`.

  Decision tree:
  - `list[T]` / `Page[T]` where `T` is a Pydantic model with all-flat
    fields → `tsv` locked.
  - Same shape with at least one `list` / `dict` / nested-Pydantic field →
    `toon` locked.
  - Single `dict`, single Pydantic model, scalar return, `None` → `json` locked.
  - Untyped `list`, `list[dict]`, `Any`, unresolvable forward ref → `None`
    (runtime fallback, identical to v0.9 behaviour).

- **`Page[T]` with Pydantic items.** `_dump_items()` flattens
  `Page[Issue].items` via `model_dump()` before the tabular encoder sees
  them, so `Page[Pydantic]` returns a real TSV/TOON payload instead of
  `str(Issue)` slop. Same fix applies to `list[Pydantic]`.

- **Auto-wired `connection_enricher` on Routers with a store.** A typo in
  the `connection` arg now returns

  ```
  Connection not found: prdo
  Available: prod, staging
  Did you mean: prod?
  ```

  …without the author wiring `enricher=connection_enricher(self.store)`.
  Disable with `auto_connection_enricher=False` on the Router subclass; an
  explicit `enricher=` still wins.

- **Schema enrichment for `connection: str`.** The injected docstring
  inlines the saved connection keys (`Currently saved: 'prod', 'staging'`)
  so the agent sees valid values inline instead of having to call
  `connections list` out-of-band. Empty stores fall back to the v0.9
  generic phrasing.

### Changed

- `format_response(...)` accepts `format_hint: FormatName | None` (default
  `None`). Hint is trusted unless the data shape is incompatible (e.g.
  `tsv` hint on a single dict → falls back to JSON).
- `connection_enricher(store)` parameter type relaxed from
  `ConnectionStore[ConnectionInfo]` to `Any` — the function only needs
  `.list_connections()`. Lets the router's internal `_EphemeralAwareStore`
  proxy flow through without `cast()`.

### Migration from 0.9

No breaking changes. `connection_param=` is still a soft-deprecated alias
(slated for v0.11). Three opt-out hooks:

- Router auto-enricher: `class WidgetsRouter(Router): auto_connection_enricher = False`
- Schema-key enrichment: not configurable in v0.10 — keys are listed when
  `store.list_connections()` succeeds and yields ≥ 1 entry.
- Format-from-type: omit the return annotation, or annotate with `list[dict]` /
  `Any` to force the runtime path.

## 0.9.0 — 2026-05-07

**Ergonomic overhaul.** Pre-1.0, no users — clean breaks across error
handling, capability declarations, list-view tools, and the connection-key
contract. Most tool signatures get shorter; the agent-facing schema gets
sharper; the kit's mental model collapses by one layer.

### New

- **`@Router.read()` / `@Router.write()` auto-inject `connection: str`** into
  the agent-facing schema whenever the Router has a store. Authors stop
  writing `connection_param="conn"` and stop adding `conn: str` to their fn
  signature.

- **Type-driven info DI** — declare a `ConnectionInfo`-subclass typed
  parameter on your fn (`info: WidgetConn`); the kit binds the resolved info
  there at call time. Hidden from the agent-facing schema. `Router.context.info()`
  survives as the helper-function escape hatch:

  ```python
  @WidgetsRouter.read()                                  # zero kwargs
  async def list_widgets(info: WidgetConn) -> list[dict]:
      return [{"url": info.url}]
  # Agent calls list_widgets(connection="prod"); kit resolves + injects info.
  ```

- **List-view triad** — three orthogonal flags, two execution modes each:

  | Concern    | Local (kit handles)               | Passthrough (tool handles)              |
  |------------|-----------------------------------|------------------------------------------|
  | `filter`   | CEL post-process on rows          | thread `filter:str` to fn (compile to JQL/SQL/…) |
  | `fields`   | dict-key projection on rows       | thread `fields:list[str]` to fn          |
  | `pagination` | slice + opaque cursor encoding | thread `limit:int, cursor:str|None` to fn; tool returns `Page[T]` |

  Replaces v0.8's `projection=True` / `cel_filter_param=` / `fields_param=`
  with a coherent execution-mode story so MCPs that pushdown filtering or
  pagination upstream (a2db SQL, a2atlassian JQL) get first-class support
  alongside in-memory data sources (Reddit JSON, local lists).

- **`Page[T]`** — typed Pydantic generic for tools that own pagination
  upstream. `items: list[T]`, `next_cursor: str | None`. Kit unwraps and
  threads `next_cursor` into the outer `Response`.

- **Output formats split honestly: `tsv` vs `toon`** — flat rows render as
  TSV (header + tab-separated scalar cells); rows with at least one nested
  value render as TOON (same shape, but nested cells are compact-JSON-encoded
  inline). `Response.format` is now `Literal['tsv', 'toon', 'json']`. The
  v0.8 'toon' label was lying about the encoding.

- **`Router.capabilities` is `ClassVar`** — caps describe the router's *type*,
  not its runtime instance. Mirrors the existing `read_capabilities` /
  `write_capabilities` `ClassVar` pattern.

  ```python
  class IssuesRouter(a2kit.Router):
      capabilities: ClassVar[set[Capability]] = {Cap.EXTERNAL}
  ```

- **Errors simplified — `EnricherFn = Callable[[Exception, str | None], Exception]`**
  replaces `ErrorEnricher` Protocol + `EnricherRegistry`. Composition via a
  6-line `chain(*fns)` helper. `connection_enricher(store)` factory replaces
  the `ConnectionNotFoundEnricher` class — closes over the store, returns a
  plain function.

  ```python
  @a2kit.tool(enricher=chain(my_enricher, connection_enricher(store)))
  async def query(...): ...
  ```

### Breaking

- `xml_guard` already renamed to `tool_call_guard` in v0.8 — this remains.
- **`projection=True`, `cel_filter_param=`, `fields_param=` removed.** Use
  `filter=Local|Passthrough`, `fields=Local|Passthrough`,
  `pagination=Local|Passthrough` instead.
- **`ErrorEnricher` Protocol, `EnricherRegistry`, `ConnectionNotFoundEnricher`
  class removed.** Use `EnricherFn` callables, `chain(*fns)`,
  `connection_enricher(store)` factory.
- **`ToolConfig` Pydantic model removed.** It was never wired to the live
  decorator — the authoritative kwarg contract is the `ToolKwargs` TypedDict.
- **`Router.capabilities` as a Pydantic instance field is gone.** Move to
  `ClassVar[set[Capability]]` on the subclass.
- **`Response.format` widened to `Literal['tsv', 'toon', 'json']`.** Existing
  `format == "toon"` assertions on flat data will return `"tsv"` instead.

### Soft-deprecated (drops in v0.10)

- **`connection_param=<name>` kwarg** still works as a back-compat alias for
  the v0.8 string-named connection lookup. New code should use the typed-info
  DI pattern (`info: <ConnectionInfo subclass>`).

### Internal

- 561 tests, 100% line+branch coverage, lint + ty clean.
- Examples still 5 files; example 03 renamed `03_projection_tool.py` → `03_list_view.py`
  and rewritten to demonstrate Local + Passthrough side-by-side.

## 0.8.0 — 2026-05-07

**Polish bundle.** Pre-1.0 cleanups surfaced after v0.7: rename
`xml_guard` → `tool_call_guard`, lift ephemeral handling out of the tool
decorator, type-tighten `Router.tool/.read/.write` signatures, type-promote
`format_response`, and add a `projection=True` ergonomic shortcut.

### New

- **`@a2kit.tool(projection=True)`** — auto-injects `filter: str` and
  `fields: list[str] | None` keyword-only params into the wrapper signature
  (FastMCP's tool schema picks them up; agents call with them) and post-processes
  the result through `format_response`. Authors no longer write any projection
  plumbing for the common case:

  ```python
  @a2kit.tool(projection=True)
  def list_widgets() -> list[dict]:
      """Return widgets."""
      return _WIDGETS
  ```

  Collisions with author-declared `filter`/`fields` params raise at decoration
  time. The explicit `cel_filter_param=`/`fields_param=` path remains as a
  power-user escape hatch and cannot combine with `projection=True`.

- **`a2kit.Response`** — typed Pydantic envelope returned by `format_response`.
  Fields: `format` (`Literal["toon", "json"]`), `data` (`str`), `truncated`
  (`bool`), `next_cursor` (`str | None`, reserved for v0.9 pagination). Frozen,
  `extra="forbid"`.

- **`Router.tool/.read/.write` signatures use `Unpack[ToolKwargs]`.** Authors
  composing higher-order Router classmethods now get end-to-end type-checking
  on the kwarg contract.

### Breaking

- **`xml_guard` → `tool_call_guard`** on `@a2kit.tool(...)`, `ToolConfig`, and
  the public `ToolKwargs` TypedDict. Same behaviour, less misleading name —
  the guard refuses any `str` arg containing `<parameter name=` (tool-call
  envelope contamination from agents), and that's a tool-call concern, not
  XML in the abstract.

- **`ToolXMLContamination` → `ToolCallContamination`.** Same shape, same
  message; renamed for symmetry with the kwarg.

- **`format_response` returns `Response`, not `dict`.** Migration: replace
  `env["format"]` with `env.format`, etc.

- **`ephemeral=` removed from public `@a2kit.tool` kwargs** and from the public
  `ToolKwargs` TypedDict. Ephemeral connections live at the Router level only —
  `Router(..., ephemeral={...})` works unchanged. Internally,
  `Router._apply_bindings` now wraps the effective store in a private
  `_EphemeralAwareStore` proxy so the tool decorator never thinks about
  ephemeral connections. Tools that previously passed `ephemeral=` directly to
  the decorator should construct an `_EphemeralAwareStore` explicitly or use a
  Router.

### Internal

- 556 tests, 100% line+branch coverage on 2224 statements / 832 branches.
  No changes to the linter pack, scaffold CLI, or runtime introspection seams.

## 0.7.0 — 2026-05-07

**Idiomatic Python pass.** Pre-1.0 cleanups: idiomatic `StrEnum Cap`, removal of
the `info` kwarg shape, auto-injected param docs, public `ToolKwargs`, FQN
ContextVar naming, A2K012 hardening, A2K013 added.

### New

- **`Cap` is a `StrEnum`.** `list(Cap)` enumerates all members; `Cap("write")`
  parses a raw string; `Cap.WRITE == "write"` is True; Pydantic v2 native
  serialization. The capability registry pre-registers built-ins via the same
  `capabilities.register(...)` path; lib code never branches on cap names.
- **Auto-inject param docs.** When a tool function has `connection_param="conn"`,
  the canonical `connection_param_doc(...)` text is prepended to the docstring
  at decoration time. Same for any `register_param_doc(name, text)` entry whose
  name matches a function parameter. Configurable via
  `[tool.a2kit.docs] auto_inject = false`.
- **A2K013** (advisory) — flags tool docstrings that still call
  `a2kit.docs.connection_param_doc(...)` / `param_doc(...)` via f-string;
  auto-injection covers it.
- **Public `ToolKwargs` TypedDict.** Use `Unpack[ToolKwargs]` for higher-order
  Router classmethod factories (e.g. a custom `expensive` decorator that
  defaults `Cap.EXPENSIVE`). New example: `examples/higher_order_decorator.py`.
- **A2K012 re-export resolution.** A2K012 now follows `from pkg import NAME`
  through `pkg/__init__.py` re-exports (cap depth 3) to confirm the constant
  terminates at a `Final[str]` annotation. Re-exports without a `Final[str]`
  terminus are flagged.

### Breaking

- **`info_kwarg` removed from `@a2kit.tool(...)`.** The kwarg-injection path
  (`*, info: ConnT | None = None`) is gone; the only supported access is
  `Router.context.info()`. `ToolConfig.info_kwarg` field also removed.
  Migration:

  ```python
  # Before:
  async def get_widget(conn: str, *, info: WidgetConn | None = None) -> dict:
      return {"url": info.base_url}

  # After:
  async def get_widget(conn: str) -> dict:
      info = WidgetsRouter.context.info()
      return {"url": info.base_url}
  ```

- **`Cap` is no longer a plain class with `Final[str]` constants.** Author
  syntax `Cap.WRITE`, `Cap.READ`, etc. is unchanged (StrEnum subclasses `str`,
  same equality semantics, same set/dict membership). The only observable
  difference: `Cap.WRITE.value == "write"` exposes the underlying string, and
  `repr(Cap.WRITE)` now shows `<Cap.WRITE: 'write'>`.

### Bug fixes

- **FQN-based `_RouterContext` ContextVar naming.** Two same-named Router
  classes in different modules (e.g. `app/jira/IssuesRouter` and
  `app/github/IssuesRouter`) used to share a ContextVar by `cls.__name__` and
  collide. v0.7 names the ContextVar with `f"{cls.__module__}.{cls.__qualname__}"`,
  giving each Router class independent state. Transparent rename — no author
  change needed.

### Examples

- **NEW** `examples/v07_minimal_mcp.py` (replaces `v06_minimal_mcp.py`) —
  StrEnum Cap demo + ContextVar-only flow.
- **NEW** `examples/higher_order_decorator.py` — `Unpack[ToolKwargs]` factory.
- **UPDATED** `examples/fat_tool.py`, `examples/router_class.py`,
  `examples/v03_minimal_mcp.py` — drop `info` kwarg, use ContextVar.

## 0.6.0 — 2026-05-07

**Router ergonomics + DI + type-verification + capability unification.** Additive
on top of v0.5.0; no destructive changes to v0.5 callers.

### New

- **Auto-derived Router names.** `class WidgetsRouter(a2kit.Router)` now slugs
  to `name="widgets"` automatically. `JiraConfluenceRouter` → `jira-confluence`.
  Explicit `name="..."` still wins.
- **`@MyRouter.read` / `.write` / `.tool` classmethod decorators.** Bind tools
  declaratively at module scope; `register_read` / `register_write` walk
  `cls._tools` by default. Each subclass gets its own fresh `_tools` list via
  `__init_subclass__` to avoid the mutable-default trap. Imperative override
  is still supported as the documented escape hatch (D).
- **Router-level DI.** Lift `store`, `enricher`, `resolver_registry`,
  `ephemeral` to the Router instance; every tool inherits. Per-tool decorator
  kwargs override.
- **`MyRouter.context.info()` typed accessor.** Each Router subclass gets a
  per-Router `_RouterContext` ClassVar backed by a `ContextVar`. The fat
  `@a2kit.tool` decorator sets it before the wrapped fn runs and resets after.
  The `*, info: ConnT` kwarg style still works in parallel and is opt-in
  (only injected if the function declares the kwarg or `**kwargs`).
- **Multi-store MCPs.** `Router(store=...)` per-router; `MCPRunner` aggregates
  via `RouterRegistry.routers_with_stores()`. CLI uses `--register router:key=...`
  namespaced parsing when >1 distinct store is registered; bare form raises
  with router-prefix suggestions.
- **A2K012 lint rule.** Advisory: raw-string custom capability that isn't a
  built-in `Cap.*` constant and isn't an imported / local `Final[str]` constant.
  Skipped on `tests/` and `examples/`.
- **Capability unification reframe.** Built-ins are pre-registered via the same
  `capabilities.register(...)` path as custom caps; `Cap` is a typed
  convenience reference (no special-casing in lib code). A2K009 stays as
  advisory for the built-in case.

### Breaking

- None for the v0.5 API surface. The `register_read` / `register_write`
  methods still exist; they now have a default implementation that walks
  `cls._tools`. Authors who override imperatively continue to work unchanged.

### Migration recipes

```python
# v0.5 — register_read with manual @a2kit.tool:
class WidgetsRouter(a2kit.Router):
    def register_read(self, server, store):
        @a2kit.tool(server=server, store=store, connection_param="conn")
        async def list_widgets(conn: str, *, info) -> list[dict]:
            return [{"url": info.url}]

# v0.6 — declarative + typed context:
class WidgetsRouter(a2kit.Router):
    pass

@WidgetsRouter.read(connection_param="conn")
async def list_widgets(conn: str) -> list[dict]:
    info = WidgetsRouter.context.info()  # typed
    return [{"url": info.url}]

routers.add(WidgetsRouter(store=store))
```

## 0.5.0 — 2026-05-07

**Breaking change.** `KEY_FIELDS: ClassVar[tuple[str, ...]]` is removed in favour
of a NamedTuple-based `Key` class declared via `key=` on the subclass. This
unlocks per-field types (e.g. `env: Literal["dev", "staging", "prod"]`),
keeps NamedTuple-as-tuple compatibility for the existing positional/tuple/kwargs
load shapes, and adds a fully-typed `store.load(WidgetKey(...))` shape.

**Migration recipe:**

```python
# Before (v0.4):
class WidgetConn(a2kit.ConnectionInfo):
    KEY_FIELDS = ("project", "env", "db")

# After (v0.5):
from typing import NamedTuple

class WidgetKey(NamedTuple):
    project: str
    env: str
    db: str

class WidgetConn(a2kit.ConnectionInfo, key=WidgetKey):
    ...
```

Subclasses that still declare `KEY_FIELDS` raise `MigrationRequired` at class
creation time with a generated migration snippet. (Pre-1.0 clean cut: no alias,
no warning grace period.)

**New**

- `ConnectionInfo.__init_subclass__` accepts `key=<NamedTupleClass>`. The class
  is bound as `cls.Key`. Default is the built-in `_DefaultKey(name: str)`.
- `ConnectionStore.load()` accepts a NamedTuple instance directly as a
  fifth call shape: `store.load(WidgetKey(project="a", env="dev", db="c"))`.
  All previous shapes (kwargs / tuple / list / positional / bare-string) still work.
- `ConnectionStore.key_class` property — exposes `model.Key`.
- `ConnectionStore.list_keys()` — returns typed NamedTuple instances rather
  than raw `tuple[str, ...]`. Existing index-style access still works.
- New exception: `MigrationRequired`.
- Examples: `examples/typed_key_literal.py` (per-field `Literal` typing),
  renamed `examples/key_namedtuple.py` (was `key_fields.py`),
  renamed `examples/v05_minimal_mcp.py` (was `v04_minimal_mcp.py`).

**Behavioural changes**

- `KeyFieldMissing` / `KeyArityMismatch` messages now reference the NamedTuple
  class name (e.g. `"Missing key field 'env' on WidgetKey"`).
- A2K005 lint rule simplified: no longer validates `KEY_FIELDS` shape (the
  attribute is gone). Now flags any leftover `KEY_FIELDS = ...` as a v0.5
  migration error and continues to cross-check `connection_param` arity against
  `cls.Key._fields`.

**Removed**

- `KEY_FIELDS: ClassVar[tuple[str, ...]]` — gone. The `__init_subclass__`
  validator that warned on uppercase entries is also gone (NamedTuples enforce
  identifier-shape at the language level).

## 0.4.1 — 2026-05-07

Patch on top of v0.4.0. Three changes: `ty` becomes a hard gate, internal
client-name references are scrubbed from the working tree (and from prior
commits via history rewrite), and two example files are renamed to describe
their shape rather than their inspiring upstream MCP.

**Strict typing**

- `ty` is now a mandatory typecheck step. `make typecheck` no longer skips
  when ty isn't installed — `ty>=0.0.34` is a dev dependency. CI runs
  `uv run ty check src/` between ruff and pytest as a hard gate.
- Pre-commit hook for `ty` runs at `pre-push` (not `pre-commit`) since
  type-checking is comparatively slow.
- Migration: `uv sync --all-extras` if you were previously skipping ty.

**Privacy / generality**

- Connection-name examples no longer reference internal client names.
- Two example files renamed:
  - `examples/a2atlassian_style.py` → `examples/flat_key_style.py`
  - `examples/a2db_style.py` → `examples/multi_field_key_style.py`
- Prose references to `a2atlassian` / `a2db` in source comments, docstrings,
  README, ANTIPATTERNS, and CHANGELOG replaced with descriptive phrases
  ("a Jira/Confluence-wrapping MCP", "a SQL-wrapping MCP"). Real package
  imports (`atlassian-python-api`, `mcp.server.fastmcp`) are unchanged.

**History rewrite**

- v0.4.1 also rewrites the prior 4 commits via `git filter-repo` to scrub
  internal client connection-name references from commit history. Anyone with
  a clone before this point should
  `git fetch --all && git reset --hard origin/main` to sync. (Realistically:
  nobody has a clone — the repo was just published.)

## 0.4.0 — 2026-05-07

Pre-1.0 clean cut. Removes all v0.3 deprecation aliases (no external consumers
to break). Adds CEL projection, completes A2K005, activates A2K010, ships
A2K011, auto-loads pyproject defaults, splits `_select.py`. Internal repo only —
not published to PyPI.

**Breaking changes (deprecation aliases removed):**

- `a2kit.Feature` / `a2kit.FeatureRegistry` — gone. `from a2kit import Feature`
  raises `ImportError` with a migration hint. Use `Router` / `RouterRegistry`
  (kwarg-init).
- `RouterRegistry.feature(...)` decorator — gone. Use `RouterRegistry.router(...)`.
- `MCPRunner` flags `--enable`, `--no-enable`, `--writes` — gone. The synthetic
  `(read or write)` clause translation is removed. Migration:
  - `--enable issues,sprints` → `--select "router:issues or router:sprints"`
  - `--no-enable sprints`     → `--select "default and not router:sprints"`
  - `--writes`                → include `(read or write)` in your `--select`
- `build_cli(connection_class=...)` kwarg — gone. Derived from
  `store.connection_class`.
- `MCPRunner(connection_class=...)` kwarg — gone. Same derivation.
- `register_ephemeral_connections(args, connection_class)` positional — gone.
  Only `register_ephemeral_connections(args, store=store)` remains.

**New**

- `a2kit.projection` module: `filter_records(records, *, expr)` (CEL boolean
  expression filter), `project_fields(records, *, fields)` (key selection).
  `[projection]` extra brings in `cel-python>=0.5`. Lazy-imported; missing
  dep raises `ProjectionUnavailable`.
- `a2kit.format_response(data, *, filter="", fields=None, ...)` composes
  filter → projection → truncation → format routing.
- `@a2kit.tool(cel_filter_param="filter", fields_param="fields")` auto-threads
  the named function args into `format_response`.
- New exceptions: `ProjectionUnavailable`, `InvalidFilterExpression`.
- `MCPRunner` auto-loads `[tool.a2kit.runner] default_select` from the nearest
  `pyproject.toml` (walks up from CWD). Resolution order: explicit kwarg →
  pyproject value → hard default `"default and not write and not destructive"`.
- `[tool.a2kit.capabilities]` table in `pyproject.toml`. Each entry is
  registered into `a2kit.capabilities` at `MCPRunner.__init__` time. Same
  `CapabilityRecord` validation as the code-side path.
- **A2K010** lint activated: scans `default_select=...`, `parse_select(...)`,
  `--select "<expr>"` literals in source, `scripts/*.sh`, `Makefile`, and
  `pyproject.toml`. Unknown atoms emit `A2K010` with `difflib` suggestions.
- **A2K011** advisory lint: `@a2kit.tool` returning raw `dict`/`Mapping` is
  flagged ("prefer Pydantic BaseModel for richer schema snapshots").
  Configurable via `[tool.a2kit.lint] disabled = ["A2K011"]`. Suppressible
  via `# noqa: A2K011` on the function definition line.
- **A2K005 completed**: cross-checks tool `connection_param` type annotation
  against the resolved store's `KEY_FIELDS` arity. `str` for arity > 1 is
  rejected; `tuple[...]`, typed key model, or `dict[str, str]` accepted.
  Falls back to advisory when the store can't be resolved within the file.

**Cleanups / refactors**

- `_select.py` split into `_select_parse.py` (~110 LOC) + `_select_eval.py`
  (~40 LOC) + `_select.py` façade. Public re-exports unchanged.
- `examples/projection.py`, `examples/cel_filter_tool.py`,
  `examples/toml_capabilities.py`, `examples/v04_minimal_mcp.py` — new.
- ANTIPATTERNS.md adds entries 14–18 (Pydantic class-attr fields, runtime
  `Capability` alias, forward refs + `__future__` annotations, opt-in pytest
  plugins, hard breaks vs synthetic deprecation clauses).
- `tests/test_v04.py` covers projection, A2K005 multi-field, A2K010, A2K011,
  TOML capability loading, removal guards.

**No PyPI publish.** Repo push is the only release channel for v0.4.

## 0.3.1 — 2026-05-07

Patch on top of v0.3.0. Adds Router (Pydantic) + capabilities + select grammar
+ Pydantic configs + strict types. Backward-compatible aliases for one cycle.

**New**

- `Router` (Pydantic `BaseModel`, generic over `ConnT`) replaces `Feature`.
  Subclass and instantiate via kwargs: `IssuesRouter(name="issues", capabilities={Cap.EXTERNAL})`.
- `RouterRegistry.apply()` sets a thread-local `_active_router`; the fat
  `@a2kit.tool` decorator reads this via the **auto-tag seam** and merges
  the router's name + capabilities + `Cap.READ`/`Cap.WRITE` (per phase) onto
  every registered tool's tag set.
- `Cap` constants (`Cap.READ`, `Cap.WRITE`, `Cap.DESTRUCTIVE`, `Cap.EXPENSIVE`,
  `Cap.PII`, `Cap.EXTERNAL`).
- `a2kit.capabilities` namespace — register custom caps:
  `a2kit.capabilities.register("tickets-management", description="...")`.
- `--select` boolean expression flag on `MCPRunner`. Grammar:
  atoms (router/tool/capability names), operators `and`/`or`/`not`,
  optional `tool:` / `router:` / `cap:` namespace prefix, parentheses.
  Default: `default and not write and not destructive`.
- `a2kit.sel(...)` typed builder mirrors the CLI grammar via `&`, `|`, `~`.
- `SelectExpr` (Pydantic AST), `SelectAtom`, `parse_select()`.
- Pydantic configs: `ToolConfig`, `RunnerConfig`, `BudgetConfig` (all
  `extra="forbid"`, `frozen=True`).
- `ConnectionInfo.__init_subclass__` validates `KEY_FIELDS` shape (tuple,
  non-empty, identifier per entry, lowercase warned).
- `ConnectionStore.load(...)` unwraps `pydantic.ValidationError` and re-raises
  the underlying `KeyArityMismatch` / `KeyFieldMissing` / `InvalidConnectionKey`.
- `UnknownCapability` exception with `difflib`-based `suggestions=[...]`.
- New lint rules:
  - **A2K008** — Name collision across router/tool/capability namespaces.
  - **A2K009** — Raw built-in capability string (`'write'` instead of `Cap.WRITE`).
  - **A2K010** — Reserved (v0.4) — unknown atom in `--select` expressions.
- Ruff `ANN` rules added to `[tool.ruff.lint]` selection. `tests/` and
  `examples/` paths get per-file ignores for `ANN001`/`ANN201`/etc.
- New examples: `examples/router_class.py`, `examples/select_grammar.py`,
  `examples/typed_decorator.py`. Updated `examples/v03_minimal_mcp.py`,
  `examples/feature_class.py`.
- `make typecheck-strict` target (graceful fallback if ty unavailable).
- `.pre-commit-config.yaml`, `package.json` (jscpd + actionlint),
  `.jscpd.json`, `scripts/find_similar.py` (similar-tool-name detector).

**Breaking changes**

- `--enable` / `--no-enable` / `--writes` flags on `MCPRunner` are deprecated.
  They still work for one cycle (with `DeprecationWarning`) and are translated
  internally to a `--select` expression.

  Migration recipe:
  - `--enable issues,sprints` → `--select "router:issues or router:sprints"`
  - `--no-enable sprints`     → `--select "default and not router:sprints"`
  - `--writes`                → include `(read or write)` in your `--select`
  - `--enable issues --writes` → `--select "router:issues and (read or write)"`

**Deprecations (one-cycle warning, removal in v0.4)**

- `Feature` / `FeatureRegistry` (use `Router` / `RouterRegistry`).
  Class-attribute style (`class IssuesFeature(Feature): name = "issues"`) is
  not supported under Pydantic; use `IssuesRouter(name="issues", ...)` instead.
- `RouterRegistry.feature(...)` decorator (use `RouterRegistry.router(...)`).
- `--enable` / `--no-enable` / `--writes` (use `--select`).

**Internal renames (underscore-prefixed; no external impact)**

- `a2kit/_capabilities.py`, `a2kit/_select.py`, `a2kit/_router_state.py`,
  `a2kit/_configs.py` — all leading-underscore internals.

## 0.3.0 — 2026-05-07

Feature class, KEY_FIELDS, server-auto-register, lint subpackage. Internal-only
release one day after v0.2 — applies a clean cut where it makes sense.

**Breaking changes**

- `KEY_PARTS: ClassVar[int | None]` → `KEY_FIELDS: ClassVar[tuple[str, ...]]`.
  No alias — pre-1.0 clean cut. Migration: replace `KEY_PARTS = N` with the
  field-named tuple, e.g. `KEY_FIELDS = ("project", "env", "db")`. Default
  `("name",)` covers the single-key case, so subclasses with `KEY_PARTS = 1`
  can simply drop the line.
- `build_cli(connection_class=...)` and `MCPRunner(connection_class=...)` are
  deprecated. The store knows its model — use `build_cli(store, name="...")`
  and `MCPRunner(server, store=store)`. Passing `connection_class=` still
  works for one cycle, with a `DeprecationWarning`.
- `register_ephemeral_connections(args, connection_class)` → prefer
  `register_ephemeral_connections(args, store=store)`. Old shape works with a
  warning.

**New**

- `@a2kit.tool(server=server, ...)` auto-registers the wrapped function with
  FastMCP's tool manager. Idempotent when stacked under an explicit
  `@server.tool()` (innermost) — the decorator detects an existing entry by
  name and skips. The single-decorator path is the new default; stacked form
  remains for callers who need explicit FastMCP options.
- `ConnectionInfo.KEY_FIELDS` — named-tuple key shape. Default `("name",)`.
  `ConnectionStore.load(...)` now accepts kwargs (`load(project=..., env=..., db=...)`),
  tuples, lists, positional args, and bare-string sugar for the single-field
  default.
- New typed exceptions: `KeyFieldMissing`, `KeyArityMismatch`.
- `ConnectionStore.connection_class` — exposes the bound model class.
- `a2kit.scaffold.Feature` — base class bundling enricher + snapshot_dir +
  cassette_dir + register hooks. The v0.2 `@registry.feature(name, ...)`
  decorator path is unchanged. Register an instance via `registry.add(MyFeature())`.
- `a2kit.docs.register_param_doc(name, text)` + `a2kit.docs.param_doc(name)`.
  Registered text is auto-injected into a tool's docstring when the existing
  docstring doesn't mention the parameter. Explicit text wins.
- `a2kit.lint` subpackage:
  - **Static rules:** `A2K001` (tool decorator missing param), `A2K002`
    (`-> str` returns), `A2K003` (module-local Pydantic return), `A2K004`
    (canonical connection-param helper), `A2K005` (`KEY_FIELDS` shape +
    usage), `A2K006` (duplicate param description).
  - **Runtime checks:** `A2KR001` (snapshot presence), `A2KR002` (per-tool
    budget), `A2KR003` (total schema budget), `A2KR004` (similar tool names).
  - CLI: `uvx a2kit lint paths...` and `uvx a2kit check --import path:server`.
  - Configurable via `[tool.a2kit.lint]` / `[tool.a2kit.check]`. Per-line
    `# noqa: A2KXXX`.
  - See `LINT.md` for rationale and examples.

**Examples added**

- `examples/v03_minimal_mcp.py` — < 30 LOC for a 2-tool MCP using `@a2kit.tool(server=...)`.
- `examples/feature_class.py` — `Feature` base class with enricher + snapshot dir.
- `examples/key_fields.py` — all four `load()` call shapes against a 3-part key.

Existing examples (`runner.py`, `scaffold_cli.py`, `feature_modules.py`) updated
to drop the now-redundant `connection_class=` kwarg.

**Deprecations (one-cycle warning, removal in v0.4)**

- `build_cli(connection_class=...)`
- `MCPRunner(connection_class=...)`
- `register_ephemeral_connections(args, connection_class)` (positional)

## 0.2.0 — 2026-05-07

Production-grade primitive set. Promotes a2kit from "ready for first external
consumer" to a foundation that absorbs every recurring MCP boilerplate at n=2.
All v0.1 API still imports unchanged; the bare `@a2kit.tool()` is byte-equivalent
to `@a2kit.tools.tool()` from v0.1.

**New modules:**

- `a2kit.formatter` — `truncate`, `toon_or_json`, `format_response`. Vendored
  TOON encoder (~12 LOC) + recursive truncation + canonical envelope.
- `a2kit.docs` — `connection_param_doc(name, *, cli, example, custom_suffix)`.
  One canonical paraphrase for the connection-param docstring (eliminates
  per-tool phrasing drift).
- `a2kit._cassette` (re-exported as `a2kit.testing.cassette`) — vcrpy thin
  wrapper. Decorator + sync/async context manager.

**New scaffold primitives:**

- `a2kit.scaffold.MCPRunner` — wraps `server.run()` with `--register`,
  `--scope`, `--enable`, `--no-enable`, `--writes`, `--http [host:port]` parsing.
  Sets the thread-local transport seam used by `streaming=True` tools.
  Skippable: calling `server.run()` directly is fully supported.
- `a2kit.scaffold.FeatureRegistry` — decorator-style feature-module
  registration with `default=` flag and `apply(server, store, *, enabled,
  include_writes)`.

**Fat `@a2kit.tool` decorator** (extends v0.1 — every new arg is optional):

- `store=` + `connection_param=` + `info_kwarg=` — connection lookup +
  injection.
- `ephemeral=` — in-memory connections take priority over store.
- `resolver_registry=` — recursive `${ENV}` / `op://` resolution on every
  string field of the loaded `ConnectionInfo`.
- `write=True` — enforces `read_only` check; raises `WriteNotAllowed`.
- `xml_guard=True` (default) — refuses any `str` arg containing
  `<parameter name=`; raises `ToolXMLContamination`.
- `otel=True` (default) — wraps the call in `a2kit.tool.<name>` span when a
  non-default tracer provider is configured; no-op otherwise. Lazy import,
  optional `[otel]` extra.
- `streaming=True` — async-iterator returns collected on stdio, passed
  through on HTTP.
- `tool_name=` — explicit name for the OTel span (defaults to `__name__`).
- Public top-level alias `a2kit.tool` (v0.1 `a2kit.tools.tool` retained).
- Standalone helper `a2kit.tools.assert_clean_string(value, param_name)`.

**Pytest plugin additions:**

- `--update-cassettes` flag.
- `update_cassettes` boolean fixture.

**New exceptions:** `WriteNotAllowed`, `ToolXMLContamination`.

**Optional extras:**

- `[otel]` — `opentelemetry-api>=1.20`. Lazy-imported.
- `[testing]` — `vcrpy>=6`. Lazy-imported via `a2kit.testing.cassette`.

**Examples added:** `fat_tool.py`, `runner.py`, `formatter.py`,
`feature_modules.py`, `streaming_tool.py`, `cassette_test.py`. `scaffold_cli.py`
updated to use `MCPRunner`. `make examples` runs all of them end-to-end.

**Anti-patterns consolidated:** `ANTIPATTERNS.md` at repo root — 13 entries,
each with citation.

**No deprecations.** `a2kit.tools.tool` still exported.

## 0.1.0 — 2026-05-07

Initial thin-library release. Promotes a2kit from single-primitive spike to a v0.1
library ready for first external consumer.

**Public API surface:**

- `ConnectionInfo`, `ConnectionStore`, `default_config_dir` — TOML-backed
  named-connection store. Already in 0.0.1.
- `resolve_token`, `ResolverRegistry`, `resolve_env`, `resolve_op`, `resolve_literal`,
  `default_registry` — token resolvers (`${ENV_VAR}`, `op://...`, literal). Already
  in 0.0.1.
- `tools.tool` decorator — composes with FastMCP's `@server.tool()`. Refuses
  `-> str` returns at decoration time (`InvalidToolReturnTypeError`); rewrites
  return annotations on both wrapper and wrapped function. Optional `enricher`
  routes exceptions through an `ErrorEnricher`.
- `tools.preserve_return_annotation` — public utility for the annotation-rewrite
  trick alone, without the rest of `tool(...)`.
- `errors.ErrorEnricher` Protocol — `enrich(exc, *, tool_name) -> Exception`.
- `errors.EnricherRegistry` — chains enrichers in registration order; first
  divergent return wins.
- `errors.ConnectionNotFoundEnricher` — built-in enricher; adds
  `available_connections` and a `difflib` suggestion to `ConnectionNotFound`
  exceptions.
- `scaffold.build_cli(store, connection_class, name)` — Click group with
  `login`/`logout`/`connections list`/`connections show`/`connections delete`.
  Author adds their own commands via `cli.add_command(...)`.
- `scaffold.register_ephemeral_connections(args, connection_class)` — parses
  `--register KEY field=val ...` blocks from argv into in-memory connections.
- `scaffold.scope_filter(store, scope)` — read-only filtered store view.
- `testing.snapshot_schemas(server, dir)` — writes one compact-JSON file per
  FastMCP tool (file size = byte-accurate token-budget proxy).
- `testing.assert_schemas_match(server, dir)` — raises `SchemaSnapshotMismatch`
  on drift; message contains a unified diff.
- `pytest_plugin` — opt-in via `pytest_plugins = ["a2kit.pytest_plugin"]` in
  the consumer's `conftest.py`. Provides `schema_snapshot` fixture and
  `--update-schema-snapshots` flag.
- New exceptions: `InvalidToolReturnTypeError`, `SchemaSnapshotMismatch`.

**No deprecations.** All 0.0.1 API still imports unchanged.

**Out of scope (deferred):**

- Retry/rate-limit base client (anticipated at n=1; confirm or kill at n=3).
- Feature-module registration with `--enable` (anticipated at n=1).
- Pagination unification (anticipated at n=1).
- Output-format router (TSV/TOON/JSON) — module-level concern, not a primitive.
- Token-budget defaults — module-level concern.
- OTel integration — deferred to v0.2.

## 0.0.1 — 2026-05-07

Initial spike. `ConnectionStore` extracted from two upstream MCPs (a SQL
wrapper and a Jira/Confluence wrapper); pluggable `ResolverRegistry`; typed
exceptions on resolver failure.
