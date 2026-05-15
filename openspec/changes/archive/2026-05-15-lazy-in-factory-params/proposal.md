## Why

The `di-conditional-injection` capability spec already promises
that `Lazy[T]` works for **both** tool and factory parameters
(`openspec/specs/di-conditional-injection/spec.md` line 8):

> *"Tool **and factory** parameters annotated `Lazy[T]`... SHALL
> be recognized by the dispatcher as deferred-resolution requests
> for type `T`."*

The implementation honors this for tool dispatch
(`Container.resolve_params` at `packages/di/container.py:417-445`)
but **not for factory construction**
(`Container._construct_kwargs` at lines 539-554). A factory
declaring `Lazy[T]` as a parameter today raises
`UnresolvableType` because `_construct_kwargs` doesn't recognise
the `Callable[[], Awaitable[T]]` shape.

This is a spec-vs-implementation drift bug, not a new feature.
The consumer-visible consequence (per a2web round-10 Friction E):
aggregates like `AppState` cannot carry lazy handles for their
heavy/conditional resources. Consumers thread `Lazy[T]` kwargs
through every tool signature instead, adding noise that a single
collapsed parameter would eliminate.

Closing the gap is a ~6-line addition to `_construct_kwargs` plus
a scope-graph guard for one subtle invalid case (SINGLETON factory
declaring `Lazy[per-call-type]`).

## What Changes

### Implementation (`packages/di/container.py`)

`_construct_kwargs` gains the same Lazy-recognition path
`resolve_params` already has:

```python
async def _construct_kwargs(self, factory: Factory) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for spec in self._params_for(factory):
        ann = spec.annotation
        ...
        lazy_inner = _lazy_inner_type(ann)
        if lazy_inner is not None:
            kwargs[spec.name] = self._make_lazy_closure(lazy_inner)
            continue
        if self.has_provider(ann) or _looks_like_basesettings(ann):
            kwargs[spec.name] = await self.get(ann)
            continue
        ...
```

### Scope-graph guard

`_make_lazy_closure(self, type_)` captures `self`. When a SINGLETON
factory's parameters are resolved, `self` is the **root** container.
For `Lazy[app-scope-T]`, awaiting the closure later calls
`root.get(T)` which finds or builds the singleton — correct.

For `Lazy[per-call-T]`, awaiting the closure later calls
`root.get(per-call-T)` which routes into `_build_scoped` on root,
populating `root._scoped_cache` — wrong scope. The per-call type
gets a single instance pinned to the app's root cache forever,
breaking per-call semantics silently.

`_validate_scope_graph` SHALL detect this and raise `TypeError`
at `async with app:` time. The validator currently rejects
"SINGLETON factory with direct per-call dep"; it gains a mirror
clause "SINGLETON factory with `Lazy[per-call-type]` dep" with a
specific migration hint.

per-call factories with `Lazy[T]` (any scope) remain valid — the
closure captures the per-call child container, which correctly
resolves both singletons (via parent chain) and per-call types
(its own cache).

### Spec — `di-conditional-injection`

- **MODIFIED** Requirement `Lazy[T]` is a type alias for deferred
  resolution — the existing text already mentions factory
  parameters; promote one currently-aspirational scenario to a
  concrete one ("factory body declaring Lazy[T] receives a
  callable").
- **ADDED** Requirement "Scope-graph guards Lazy[per-call] in
  SINGLETON factories" with the rejection scenario.

### Tests

- `tests/packages/di/test_lazy_in_factory_params.py` — BDD scenarios:
  1. Singleton factory with `Lazy[app-scope-T]` — closure works,
     awaiting resolves the singleton.
  2. Singleton factory with `Lazy[T]` never awaited — `T`'s
     factory + `__aenter__` never run.
  3. Singleton factory with `Lazy[per-call-T]` — `async with app:`
     raises `TypeError` with the migration hint.
  4. per-call factory with `Lazy[T]` (both scopes) — closure
     captures child, resolves correctly per dispatch.

## Out of scope

- Attribute-side-effects (a2web's first interpretation of E:
  `state.browser_pool` resolves on read). Still rejected as
  implicit-magic.
- Changes to tool-dispatch `resolve_params` — already correct.
- Changes to `Lazy[T]`'s type alias surface.

## Impact

- **Spec drift closed.** Existing spec text becomes accurate.
- **Consumer ergonomics.** `AppState`-like aggregates can declare
  `Lazy[T]` fields, factory-injected. Tool signatures collapse
  from three injectables (`state`, `browser_pool`,
  `llm_extractor`) to one (`state`).
- **Migration.** No deprecation. Today the broken case raises
  `UnresolvableType`; after the change it works or raises a
  sharper scope-graph `TypeError`. Either way: louder than silent
  miswiring.
- **Code surface.** ~6 lines in `_construct_kwargs`, ~10 lines in
  `_validate_scope_graph`, ~80 lines of BDD tests.

## Why this is correct (not just convenient)

The asymmetry — "Lazy[T] works for tools but not factories" — has
no principled rationale. The closure captures `self` either way;
the scope-graph rules apply uniformly. The existing
`_construct_kwargs` simply missed the case. Closing the gap
generalises a working mechanism without inventing new surface.
