# Tasks — consolidate lifecycle on async-CM protocol

## 0. Prerequisites

- [x] 0.1 Baseline: `make test` + `make lint` green.
- [x] 0.2 Inventory existing surfaces this change removes:
  ```bash
  grep -rn "lifespan=" src/ tests/ examples/ --include='*.py' | wc -l
  grep -rn "Router.lifespan\|def lifespan(self)" src/ tests/ examples/
  grep -rn "singleton(.*teardown=" src/ tests/ examples/
  grep -rn "a2kit.lifespan.compose\|from a2kit.lifespan" src/ tests/ examples/
  ```
  Record baseline numbers for verification at task 7.

## 1. BDD-first — write failing tests against the new shape

- [x] 1.1 `tests/test_app_async_cm.py`:
  - GIVEN an App with one singleton (class with `__aenter__`/`__aexit__`)
    WHEN `async with app:` THEN `__aenter__` was called once
  - GIVEN the same app on exit THEN `__aexit__` was called once
  - GIVEN App construction THEN no async work fires (assert no
    `__aenter__` call before `async with app:`)
- [x] 1.2 `tests/test_singleton_type_inference.py`:
  - `app.singleton(SomeClass)` registers under `SomeClass`
  - `app.singleton(annotated_factory)` registers under the return type
  - `app.singleton(unannotated_lambda)` raises `TypeError` at registration
  - `app.singleton(BaseClass, lambda: SubClass())` registers under
    BaseClass (explicit override)
- [x] 1.3 `tests/test_singleton_lifecycle_detection.py`:
  - Instance with `__aexit__` → framework calls it during App exit
  - Instance with `aclose` (no `__aexit__`) → framework awaits it
  - Instance with `close` only → framework calls it
  - Instance with none of the above → no teardown, no error
- [x] 1.4 `tests/test_router_lazy_entry.py`:
  - GIVEN App with two routers (`gh`, `slack`) both with `__aenter__`
    WHEN dispatch hits `gh.fetch` THEN `Github.__aenter__` ran once,
    `Slack.__aenter__` did NOT run
  - WHEN dispatch hits `gh.push` after THEN no second `__aenter__`
    (already entered)
  - WHEN App exits THEN only `Github.__aexit__` ran; `Slack.__aexit__`
    did NOT (never entered)
- [x] 1.5 `tests/test_lifecycle_topology.py`:
  - GIVEN singleton `A` depending on singleton `B` via DI
    WHEN App enters THEN `B.__aenter__` ran before `A.__aenter__`
  - On exit THEN `A.__aexit__` ran before `B.__aexit__`
  - GIVEN concurrent first-touch on a router THEN `__aenter__` runs once
- [x] 1.6 `tests/test_lifecycle_migration_errors.py`:
  - `a2kit.App("x", lifespan=cm)` raises `TypeError` naming
    `lifespan=` and pointing at the migration path
  - `app.singleton(T, fn, teardown=...)` raises `TypeError` naming
    `teardown=` and pointing at `__aexit__`
  - Router subclass defining `lifespan` classmethod raises `TypeError`
    at `add_router` time
- [x] 1.7 Run the suite — all six new test files fail with the
  expected red.

## 2. App: `__aenter__` / `__aexit__` implementation

- [x] 2.1 Add `App.__aenter__` and `App.__aexit__` methods.
  Body opens an `AsyncExitStack`, iterates singletons in topological
  order, resolves each, probes for protocol (per D3 detection
  order), enters / registers callback as appropriate. Stores
  `self._stack = stack.pop_all()` for `__aexit__`.
- [x] 2.2 Add `self._entered_routers: dict[str, Router] = {}` to
  `App.__init__` (initialized to empty; populated lazily by
  dispatcher).
- [x] 2.3 `App.__aexit__` unwinds `_entered_routers` in reverse-of-
  enter order, then exits `self._stack`.
- [x] 2.4 Remove `App.lifespan_cm()` method (was the indirection used
  by FastMCP / CLI / TestClient — now they call `__aenter__`/
  `__aexit__` directly via `async with app:`).

## 3. App: remove `lifespan=` constructor arg

- [x] 3.1 Add `**_kw: Any` to `App.__init__` after documented kwargs;
  if `_kw` contains `lifespan` raise `TypeError` with the migration
  hint from design D8. Other unknown kwargs raise the standard
  "unexpected kwarg" message (this dovetails with
  `audit-loud-failure-discipline` task 3.1).
- [x] 3.2 Remove `self._lifespan` attribute, `_run_teardowns` method,
  `teardown_failures` attribute. The topological unwind handled by
  `AsyncExitStack` covers what `_run_teardowns` did.
- [x] 3.3 Remove `_router_lifespan_factory` helper. Routers now
  enter via their own `__aenter__`.

## 4. Singletons: type inference, lifecycle auto-detection

- [x] 4.1 In `Container.register_singleton`: accept
  `(arg1)` or `(arg1, arg2)` form. Resolve `T` per design D3
  algorithm. Raise `TypeError` with action-oriented message for the
  unannotated-lambda case.
- [x] 4.2 Remove `teardown=` kwarg from `App.singleton`,
  `Container.register_singleton`, `Container._teardowns`. The
  protocol-probe in `App.__aenter__` (task 2.1) replaces it.
- [x] 4.3 Update `App.singleton` signature + docstring. Method-call
  form remains the only path (the v0.33 docstring already says
  this).
- [x] 4.4 If a singleton's `__aexit__` raises during App `__aexit__`,
  log under `a2kit.lifecycle` at ERROR with traceback. Continue
  unwinding sibling singletons. (Matches the in-flight behavior
  from `_ShieldShutdown` in `a2kit/lifespan.py` — port that
  shielding into `AsyncExitStack`-compatible shape.)

## 5. Routers: `__aenter__` / `__aexit__`

- [x] 5.1 Update `add_router` to detect `__aenter__` on the instance.
  Raise `TypeError` with hint (per D8) if the subclass defines
  `lifespan` in `cls.__dict__`.
- [x] 5.2 Implement lazy router entry in the dispatcher (per D2).
  Per-router `asyncio.Lock` for first-touch coalescing. Failed
  `__aenter__` does NOT cache the router in `_entered_routers`.
- [x] 5.3 Add `asyncio.Lock` per router stored on `App` (or on the
  Router instance — design decision; prefer App-side to keep Router
  pure-data).

## 6. Remove `a2kit.lifespan` public module

- [x] 6.1 Delete `src/a2kit/lifespan.py`. The `_ShieldShutdown`
  shield-shutdown helper migrates inline into `App.__aenter__`
  (or `a2kit/packages/di/container.py`, beside the existing
  topological-order logic).
- [x] 6.2 Remove `a2kit.lifespan` from public re-exports in
  `src/a2kit/__init__.py` (if exported).
- [x] 6.3 Verify no consumer in `tests/` or `examples/` imports
  `from a2kit.lifespan ...` — migrate any uses.

## 7. Wiring updates

- [x] 7.1 `build_mcp_server(app)`: wrap `async with app:` in the
  FastMCP `lifespan(server)` slot (per D5).
- [x] 7.2 CLI runtime: dispatch inside `async with app:` (per D6).
- [x] 7.3 TestClient: `async with TestClient(app) as client:` —
  internally `await app.__aenter__()` then `await app.__aexit__()`
  on exit (per D7).

## 8. Migration error messages

- [x] 8.1 Implement each migration `TypeError` per design D8.
  Centralize the messages in `src/a2kit/_migration_errors.py` (new
  module) so the test in task 1.6 can assert exact substrings.

## 9. Spec deltas

- [x] 9.1 `openspec/changes/consolidate-lifecycle-on-async-cm-protocol/
      specs/app-lifecycle/spec.md` — MODIFIED requirements documenting
      `async with app:` as canonical entry, AsyncExitStack composition,
      topological order. REMOVED requirements for the `lifespan=`
      argument shape.
- [x] 9.2 `.../specs/app-singletons/spec.md` — MODIFIED requirements
      for type inference and protocol auto-detection. REMOVED
      requirements for `teardown=` kwarg.
- [x] 9.3 `.../specs/router-conventions/spec.md` — MODIFIED
      requirements for `__aenter__`/`__aexit__` shape and lazy
      entry. REMOVED `Router.lifespan` classmethod requirement.

## 10. Documentation

- [x] 10.1 README Lifecycle section: rewrite with the four canonical
      shapes (zero-arg class, factory with annotation, explicit base
      registration, marker-singleton for resourceless bookends).
- [x] 10.2 README symbol table: remove `lifespan=` from
      `a2kit.App(...)` row; add note that App is an async CM.
- [x] 10.3 `OPERATIONAL_CONTRACTS.md`: update lifespan section to
      reflect the new wiring chain.
- [x] 10.4 CHANGELOG `Unreleased` — migration table rows for:
      `App(lifespan=...)` removed, `Router.lifespan` removed,
      `singleton(...teardown=)` removed, `a2kit.lifespan` module
      removed, `App.lifespan_cm()` removed. Each row names the
      replacement.

## 11. Consumer migration (a2web)

- [x] 11.1 Port a2web's lifespan body to the new model: extract DB,
      browser pool, LLM client into singletons with `__aenter__`/
      `__aexit__`; remove the imperative `lifespan` function.
- [x] 11.2 Verify a2web's tests pass against the migrated shape.
- [x] 11.3 Capture the diff size as proof-of-ergonomics.

## 12. Verify

- [x] 12.1 All task-1 tests pass.
- [x] 12.2 Full `make test` green.
- [x] 12.3 `make lint` green.
- [x] 12.4 Re-run inventory greps from task 0.2 — `lifespan=` /
      `Router.lifespan` / `singleton(...teardown=)` /
      `a2kit.lifespan` return zero hits in src/.
- [x] 12.5 README example apps run end-to-end.

## 13. Out-of-scope (deferred)

- [x] 13.1 Idle-timeout-driven router teardown. Routers stay entered
      until App exit. Future proposal if a real need surfaces.
- [x] 13.2 Per-tool resource scopes beyond `app.provide(factory)`.
- [x] 13.3 Health-probe restructure (covered by
      `remove-health-tool-flag`).
