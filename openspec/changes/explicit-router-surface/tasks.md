# Tasks — Explicit Router surface

## 1. A1 — Explicit `slug` class attribute

- [ ] 1.1 Enumerate every `Router` subclass in `src/` and `examples/`
  with `rg "class \w+\((?:a2kit\.)?Router.*\):" -t py --vimgrep`.
- [ ] 1.2 For each subclass, add `slug = "<current-derived-value>"`
  as a class attribute. No behaviour change yet — the framework's
  `_derive_slug` still computes the same value.
- [ ] 1.3 Remove `_derive_slug` and the `name` constructor arg /
  `name` class attribute from `src/a2kit/routers.py`.
- [ ] 1.4 Add the explicit-slug assertion in `Router.__init__`:
  `TypeError` naming the subclass if `slug` is missing or not a
  non-empty `str`.
- [ ] 1.5 Update `tests/test_routers.py` (or equivalent) to assert
  the new error message and remove tests that exercised the
  derivation rule.

## 2. A2 — Explicit `tools` class attribute

- [ ] 2.1 For each `Router` subclass enumerated in 1.1, build a
  `tools = (m1, m2, ...)` tuple listing every method decorated
  with `@a2kit.read`, `@a2kit.write`, `@a2kit.list_`, or
  `@a2kit.tool`.
- [ ] 2.2 Remove `_collect_methods` (the `dir(self)` walk) from
  `src/a2kit/routers.py`.
- [ ] 2.3 Rewrite `Router.__init__` to iterate `type(self).tools`,
  resolve each entry via `getattr(self, fn.__name__)`, and stamp
  router-slug on each bound method's `_a2kit` meta. Raise
  `TypeError` if a listed entry has no meta marker.
- [ ] 2.4 Add the explicit-tools assertion: `TypeError` if
  `type(self).tools` is missing or not a tuple of callables.
- [ ] 2.5 Update tests to assert behaviour driven by the explicit
  tuple, including the error path for a method-without-meta in
  the tuple and a meta-bearing method NOT in the tuple (should
  not register).

## 2.5. A2.5 — Router lifecycle becomes an explicit `lifespan` method

- [ ] 2.5.1 Identify every Router subclass that today defines
  `on_startup` and/or `on_shutdown` methods (auto-bridged today by
  `App.add_router` at `src/a2kit/app.py:149-161`).
- [ ] 2.5.2 For each, write a single
  `@asynccontextmanager async def lifespan(self):` method: previous
  startup body runs before `yield`, previous shutdown body runs after.
- [ ] 2.5.3 In `src/a2kit/app.py`, remove the `on_startup` /
  `on_shutdown` auto-bridge loop (the `cls.__dict__` scan at lines
  149-161).
- [ ] 2.5.4 In `App.add_router(r)`, when `r.lifespan` is defined,
  compose it into the App's top-level lifespan via
  `a2kit.lifespan.compose(...)` (helper introduced by the sibling
  `lifespan-over-lifecycle-hooks` proposal). Order: the App's own
  lifespan first, then each Router's lifespan in `add_router` order.
- [ ] 2.5.5 Update tests to assert lifespan composition order and
  that pre-yield/post-yield bodies run at the right phases.

## 2.6. A2.6 — Router `providers` pinned as explicit declared class attribute

- [ ] 2.6.1 Audit every Router subclass to confirm `providers` (when
  present) is a class-level tuple, not built in `__init__` or via
  `__init_subclass__`. Move any non-conforming case to a class-level
  declaration.
- [ ] 2.6.2 Document in the `router-conventions` spec that
  `providers` is the canonical declaration surface, peer to `slug`
  and `tools`. (No source-code change in `add_router` — the
  existing `getattr(router, "providers", ())` read becomes pinned
  behaviour by spec.)
- [ ] 2.6.3 Add a test asserting that a Router with `providers = (P,)`
  installs `P` on the App's container when `add_router` runs.

## 3. A3 — Fold staging decorators into verb-decorator kwargs

- [ ] 3.1 Enumerate `@reports(` (and any other staging decorator)
  call sites: `rg "@reports\(" -t py --vimgrep`.
- [ ] 3.2 Add `reports: type | None = None` (and any other former
  staging-input kwargs) to `@a2kit.read`, `@a2kit.write`,
  `@a2kit.list_`, `@a2kit.tool`. The verb decorator writes the
  value into `A2KitMeta.extra` (or the typed extras shape) under
  the same key the staging path used (`a2kit.report_type`).
- [ ] 3.3 For each call site from 3.1, fold the staged argument
  into the adjacent verb decorator's kwarg.
- [ ] 3.4 Remove `stage_extra` and `PENDING_EXTRA_ATTR` from
  `src/a2kit/metadata.py`. Remove the verb decorator's flush-loop
  that consumed `_a2kit_pending_extra`.
- [ ] 3.5 Remove the `@reports` decorator definition and its
  hosting module at
  `src/a2kit/packages/mcp/reports.py`. Sweep any import sites
  (`rg "from a2kit.packages.mcp.reports" -t py`) and confirm the
  module is gone after this task lands.
- [ ] 3.6 Update tests in `tests/test_metadata.py` (or equivalent)
  to assert the kwarg path; remove tests that exercised the
  staging side channel.

## 3.5. Remove `Router.install` side-channel hook

- [ ] 3.5.1 Delete the `getattr(router, "install", None)` call
  site in `src/a2kit/app.py` (currently around lines 146-148) and
  the conditional branch that invokes it.
- [ ] 3.5.2 Sweep `tests/` for any test that defines an `install`
  method on a `Router` subclass or asserts its invocation; remove
  those tests. The discovery surface is closed to `slug`, `tools`,
  `providers`, `lifespan`.
- [ ] 3.5.3 Sweep `src/` and `examples/` for any `Router` subclass
  that defines `install`; fold its body into `providers` (provider
  registration) and/or `lifespan` (setup/teardown work).

## 4. Release prep

- [ ] 4.1 Confirm v0.31.0 release (paired with
  `lifespan-over-lifecycle-hooks`); see `design.md` D4.
- [ ] 4.1.1 Land `lifespan-over-lifecycle-hooks` first (to introduce
  `a2kit.lifespan.compose`), then this change.
- [ ] 4.2 Append this change's surfaces (slug, tools, reports,
  Router.install removal) to the v0.31.0 CHANGELOG entry created
  by `lifespan-over-lifecycle-hooks` task 8.2. Single bundled
  entry under v0.31.0; one-line before/after migration examples
  per surface.
- [ ] 4.3 Coordinate with `align-with-pydantic-and-stdlib` author
  on the `A2KitMetaExtras` destination shape; ensure both writers
  land on the same typed keys.
- [ ] 4.4 Notify `loud-degrade-everywhere` author that the
  `routers.py` bare-except site is gone after this lands — that
  scope item becomes a no-op and can be dropped.

## 5. Follow-ups (out of scope for this change)

- [ ] 5.1 Lint rule: report any `@a2kit.read/write/list_/tool`
  method missing from its enclosing Router's `tools` tuple, and
  vice versa.
