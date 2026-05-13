# Tasks — singleton-teardown-topological

## 0. Prerequisites

- [x] 0.1 Baseline: `make lint` + `make test` green.

## 1. Container

- [x] 1.1 Add `_teardowns: dict[type, Callable[[Any], Any]]` to
      `Container.__init__`.
- [x] 1.2 Extend `Container.register_singleton(type_, factory, *,
      teardown=None)` to accept and store teardown.
- [x] 1.3 Add `Container.teardown_order() -> list[type]` per
      design D-TOPO-ALGORITHM. Cycle detection emits WARN.
- [x] 1.4 Unit tests in `tests/test_di_container.py` (or new
      file): teardown_order with linear dep chain, with diamond,
      with cycle (deterministic break + WARN).

## 2. App-level wiring

- [x] 2.1 Add `teardown` kwarg to `App.singleton(type_, factory,
      *, teardown=None)`. Wire to `container.register_singleton`.
- [x] 2.2 Add `App.teardown_failures: list[tuple[type, Exception]]`
      attribute, initialized empty.
- [x] 2.3 Add `App._run_teardowns()` async helper per design
      D-ERROR-ISOLATION. Iterates `container.teardown_order()`,
      awaits each (sync or async), catches `Exception`, records
      `(type, exc)` to `teardown_failures`, emits `_log.error`
      per failure with class+message+type-name, continues.
- [x] 2.4 Add `App._wrap_with_teardowns(inner_cm)`
      `@asynccontextmanager` per design D-LIFESPAN-COMPOSITION.
- [x] 2.5 Update `App.lifespan_cm()` to wrap the composed inner
      lifespan (or `nullcontext()`) in `_wrap_with_teardowns`
      whenever at least one teardown is registered. When no
      teardowns are registered AND no user/Router lifespan
      exists, return `nullcontext()` as today (no behavioural
      change).
- [x] 2.6 Update `App.has_lifespan()` to also return True when
      teardowns are registered.

## 3. Exception class

- [x] 3.1 Add `A2KitSingletonTeardownError(A2KitError, RuntimeError)`
      to `src/a2kit/exceptions.py`. Constructor:
      `(failures: list[tuple[type, Exception]])`. Message lists
      each failure as `f"<TypeName>: <ExceptionClass>: <message>"`.

## 4. Tests

- [x] 4.1 `tests/test_singleton_teardown.py`: basic — register one
      singleton with teardown, enter+exit `lifespan_cm`, assert
      teardown ran.
- [x] 4.2 Topological ordering — register two singletons where
      `B`'s factory depends on `A`. Both have teardowns. Assert
      teardown order: B first, then A.
- [x] 4.3 Error isolation — one teardown raises `ValueError`;
      assert other teardowns still ran; assert
      `app.teardown_failures` contains the `(type, exc)` tuple.
- [x] 4.4 Sync vs async teardown — register both forms; both
      fire.
- [x] 4.5 No teardown registered for some singletons — they're
      skipped; only registered teardowns fire.
- [x] 4.6 App without any lifespan but with teardowns — entering
      `lifespan_cm()` and exiting still runs teardowns.
- [x] 4.7 Cycle: synthetic factory pair that depends on each
      other (test via direct `_providers` manipulation). Assert
      WARN log line fires and both teardowns still run.
- [x] 4.8 Integration with user lifespan: a `lifespan=` callable
      records enter/exit, plus a singleton teardown. Assert
      order: user enter → ... → user exit → teardown.

## 5. Spec delta

- [x] 5.1 `openspec/changes/singleton-teardown-topological/specs/app-singletons/spec.md`
      — ADD requirement *"App.singleton accepts `teardown=` for
      framework-managed shutdown"* with scenarios for ordering,
      error isolation, cycle handling.

## 6. OPERATIONAL_CONTRACTS

- [x] 6.1 Add new section "Q-Teardown: Singleton teardown contract"
      to `OPERATIONAL_CONTRACTS.md`. Document:
      - ordering (topological, dependents first)
      - error isolation (failures don't cascade; logged + recorded)
      - the `App.teardown_failures` attribute for programmatic
        introspection
      - composition with user/Router lifespans (user `finally` runs
        first, framework teardowns after)

## 7. Verify

- [x] 7.1 `make lint` green.
- [x] 7.2 `make test` green; new tests pass.
- [x] 7.3 Smoke a downstream consumer (a2web): single
      `app.singleton(SqliteResource, build, teardown=...)` call;
      confirm the hand-rolled `finally` block can be deleted from
      the consumer's lifespan body.
