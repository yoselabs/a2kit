## Context

v0.20 shipped a thin core: 3 named verbs (`add_router`/`add_cli`/`add_mcp_middleware`), no plugin protocol, no class-as-DI-key. But the verb decorators still accept four feature kwargs (`enricher`, `list_view`, `report`, `router_slug`), `A2KitMeta` carries dedicated fields for each, and `WriteNotAllowed` keeps the word "connection" in `src/a2kit/exceptions.py`. To a senior reviewer this reads as "every feature parks a kwarg on the central decorator" — the same accumulation pattern that kicked off the first de-magic round.

The audience for this code is the entire DataArt practice. Senior Python engineers reviewing it will ask:
- "Why does the core know about connections?"
- "Why does the verb decorator have an enricher kwarg?"
- "Where did the slug 'tasks' come from when I wrote `class TasksRouter`?"
- "Why is there a `ContextVar` and a method monkey-patch in the CLI builder?"

This change closes those four questions.

## Goals / Non-Goals

**Goals:**
- `src/a2kit/*.py` (excluding `packages/`) contains zero references to "connection", "enricher", "list_view", "report_type", "router_slug" — verified by lint.
- Verb decorator kwargs collapse to `(name, tags, annotations)`. Anything else lives on a feature-owned decorator that stacks on top.
- Router slug derivation is one explicit lookup with a verbatim fallback — no string surgery.
- CLI builder has no monkey-patch and no module-level `ContextVar`.
- `A2KitMeta` shape stops growing as features are added — extension goes through `extra: dict[str, Any]`.

**Non-Goals:**
- Not changing the three composition verbs (`add_router`/`add_cli`/`add_mcp_middleware`).
- Not removing the `Router` base class. Routers stay; their internal scan changes.
- Not introducing a public plugin protocol. `extra` is for first-party feature packages; cross-package access is fine but external users should prefer adapter middleware.
- Not changing the connection store / `connections_cli` factory shape.
- Not promoting the LDD env-var read out of `App.__init__` — separate concern.

## Decisions

### D1. `A2KitMeta.extra` is the only extension point

Drop `enricher`, `list_view`, `report_type`, `report_schema`, `router_slug` as named fields. Features write namespaced keys into `extra`:

```
extra["a2kit.enricher"]    : EnricherFn
extra["a2kit.list_view"]   : ListViewSettings
extra["a2kit.report_type"] : type
extra["a2kit.report_schema"]: dict[str, Any]
```

`router_slug` is set by `Router.__init__` directly on the meta dataclass (it's a composition-time fact, not a feature attachment) — but as a separate field is gone. The Router stamps the slug back onto each tool's `extra["a2kit.router_slug"]` during collection.

**Rationale**: keeps `A2KitMeta` stable as features grow. Extension is a string key, not a schema change. Lint can enforce the `a2kit.` namespace.

**Alternatives considered**:
- Per-feature `Annotated[..., Marker]` types. Rejected: forces every tool author to import marker types and clutters signatures.
- `weakref.WeakKeyDictionary[fn, dict]` registries per feature. Rejected: harder to introspect, harder to lint, and we already have `extra` sitting unused.

### D2. Stacked decorators

Each feature exposes one decorator that reads/writes `_a2kit` attribute via `get_meta`/`set_meta`:

```python
@a2kit.read()
@enriches(my_enricher)
@reports(MyReport)
async def get_task(self, *, id: str): ...
```

Order: stack bottom-up. The `@a2kit.read()` decorator runs last (outermost) and creates the meta if not present; feature decorators run earlier and pre-stage `extra` keys via a transient attr (e.g. `_a2kit_pending_extra: dict`) that `_stamp` consumes.

**Alternatives considered**:
- Feature decorator runs *outside* `@read`. Rejected: the verb decorator does `_check_return` and creates the meta — features need a stamped meta to extend, so they should run "after" verb in execution order, which means *inside* in source order. Inside-order is what stacked decorators give us.

### D3. Bound-method router collection

`Router._collect_methods` switches from `type(self).__dict__.values()` to `inspect.getmembers(self)` with predicate `lambda m: callable(m) and getattr(m, '_a2kit', None) is not None`. This returns bound methods. `_a2kit` falls through `MethodType.__getattr__` to the underlying function, so `get_meta` still works.

`_bind_if_method` in `builder.py` is deleted. Tools are already bound. `inspect.signature` on a bound method already excludes `self`, so the existing `user_input_params` filter for `self/cls` is now redundant but harmless.

**Rationale**: removes one layer of indirection (`type(...).__dict__` walk + manual rebind) and makes `Router.tools()` return plain Python callables.

### D4. Explicit Router naming

```python
class Router:
    name: str | None = None
    def __init__(self, name: str | None = None) -> None:
        self.slug = name or self.name or type(self).__name__
```

That's it. `_slugify` deleted. If a user writes `class TasksRouter(Router): pass` and instantiates with no `name=`, slug = `TasksRouter` (verbatim, ugly enough that they fix it). If they write `name = "tasks"` or `Router(name="tasks")`, slug = `tasks`.

**Rationale**: the previous algorithm answered the question "what slug do I get?" with three sequential transformations (strip `Router` suffix → camelCase split → lowercase). Senior reviewers find that surprising. Verbatim fallback is the forcing function — the name looks bad enough that no one ships without setting it.

### D5. Per-app CLI build, no ContextVar

`build_full_cli(app)` already builds a fresh group per app. The `--no-reports` / `--no-events` handlers and the lazy `serve` registration both need access to `app`. Currently they get it via the `_APP_CTX` ContextVar that `_wrap_main_with_app_ctx` sets by monkey-patching `group.main`.

Replace with closures:
- `--no-reports/--no-events` callback closes over `app` directly (it's right there in the builder scope).
- Lazy `serve` registers `lazy_subcommands={"serve": _build_serve(app)}` where `_build_serve` returns a `click.Command` whose callback closes over `app`. The command isn't *imported* lazily anymore — but the **fastmcp import** still happens lazily inside the callback. That's the actual cold-start invariant; the lazy `LazyGroup` mechanism was a means, not the end.

**Trade-off**: we lose the `LazyGroup` for `serve` if we eagerly construct the Command. To keep cold-start, we keep `LazyGroup` but the registry value becomes a *callable factory* `() -> click.Command` instead of an `import_path:attr` string, and the factory closes over `app`. `LazyGroup.get_command` calls the factory on demand. fastmcp still imports only when the user types `serve`.

### D6. Pydantic schema generation moves to mcp/reports

`_report_schema(report_type)` — currently in `tool.py` — moves into `a2kit.packages.mcp.reports`. The `reports(ReportT)` decorator computes the schema at decoration time and stamps both `extra["a2kit.report_type"]` and `extra["a2kit.report_schema"]`. Core has no pydantic import.

### D7. WriteNotAllowed migration

Move `WriteNotAllowed` to `a2kit.packages.connections.exceptions`. Core's `__init__.py` no longer re-exports it. Anyone catching it imports from the connections package. The tracker example does this; one import-site change in the tests.

### D8. Lint as the boundary keeper

Two new static rules:

- **A2K-CORE-CLEAN**: `src/a2kit/*.py` (excluding `packages/**`) MAY NOT contain any of the tokens `connection`, `enricher`, `list_view`, `report_type`, `report_schema`, `router_slug` as identifiers. Implementation: AST visitor over `Name`/`Attribute`/`arg` nodes, fail on match. (String literals exempt — docstrings can mention "connection" in prose.)
- **A2K-EXTRA-NAMESPACE**: any subscript write to `meta.extra[KEY]` or constructor call `A2KitMeta(extra={KEY: ...})` where `KEY` is a string literal MUST start with `a2kit.` or a registered package prefix. Implementation: AST visitor.

Both rules join the existing `a2kit lint static` table. Both run in CI.

## Risks / Trade-offs

- **Stacked decorator ordering bug** → an explicit test matrix in `tests/test_decorator_stacking.py` covering all 6 combinations (verb alone, verb+enricher, verb+reports, verb+lists, verb+enricher+reports, verb+all-three).
- **`getmembers(self)` is slower than `__dict__.values()`** for routers with many inherited attributes → benchmark in test suite; acceptable as long as Router init stays <1ms for a 10-tool router.
- **Closure-based lazy serve breaks if `LazyGroup.get_command` is reused across apps** → it isn't (each app builds its own group), but add a comment and an assertion in `LazyGroup` that a registered factory has not been called twice with different parents.
- **A2K-CORE-CLEAN false positives in docstrings** → string-literal exemption already handled; double-checked by running the rule against current source after the move.
- **External users of `WriteNotAllowed` from `a2kit`** → none yet (v0.20 is fresh). Add to CHANGELOG breaking-changes section. Provide a one-line migration: `from a2kit.packages.connections.exceptions import WriteNotAllowed`.
- **Router.slug ugliness for users who forget `name=`** → that's the design. The "ugly fallback" is the forcing function. README + ANTIPATTERNS.md call it out.

## Migration Plan

1. Land `extra` namespace + lint rule first (additive — no breakage).
2. Add stacked decorators in feature packages; teach them to write into `extra`. Old kwargs still work.
3. Migrate tracker example + tests to stacked form.
4. Remove old kwargs from `tool.py` decorators and corresponding fields from `A2KitMeta`.
5. Switch Router to bound-method collection; delete `_bind_if_method`.
6. Replace `_wrap_main_with_app_ctx` + `_APP_CTX` with closure-based factories in `LazyGroup`.
7. Move `WriteNotAllowed`. Update tests' imports.
8. Drop `_slugify`. Update tracker routers to set `name=`.
9. Final pass: `A2K-CORE-CLEAN` rule run; expect 0 hits; flip rule from warn to error in CI.

Rollback: each step is a separate commit; `git revert` per-step is clean. The split between additive (steps 1–3) and breaking (4+) means we can land 1–3 in a point release if we want a soak.

## Open Questions

- Do we keep `EnricherFn` exported from `a2kit.metadata`, or move it fully into `packages/enrichers`? Leaning: move. Core type alias has no business knowing about enrichment.
- Should `extra["a2kit.router_slug"]` be writable by feature decorators or read-only after Router init? Leaning: read-only — Router stamps it, no one else writes it. Lint rule could enforce.
- Do we keep the `tool` verb at all? It's barely used in the tracker example. Out of scope here; flag for de-magic round 3.
