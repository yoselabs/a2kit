## MODIFIED Requirements

### Requirement: Singleton or router `__aexit__` failure SHALL log and continue unwinding

If a resource's `__aexit__` (or factory `finally` block) raises during App `__aexit__`, the framework SHALL log the exception via `logging.getLogger("a2kit.di.cleanup")` at level WARN with traceback, SHALL continue unwinding remaining entries in LIFO order, and SHALL NOT re-raise unless the original `__aexit__` was called with a non-None exception (in which case the in-flight exception SHALL win and the swallowed cleanup error SHALL still be logged). This is the App-lifecycle expression of the LIFO + per-resource isolation contract owned by `di-scope-cleanup-stack`; the cleanup-stack capability is canonical for the unwind semantics.

#### Scenario: Cleanup error logged, sibling unwind continues

- **GIVEN** resources `A` (well-behaved), `B` (raises in `__aexit__`), `C` (well-behaved), all entered during dispatches
- **WHEN** App `__aexit__` runs
- **THEN** `C.__aexit__` ran, `B.__aexit__` raised and was logged at WARN, `A.__aexit__` ran
- **AND** the `async with app:` block exited without raising

#### Scenario: In-flight error is preserved when cleanup also raises

- **GIVEN** the `async with app:` body raised `ValueError("x")` and resource `B`'s `__aexit__` raises `RuntimeError("y")` during the unwind
- **WHEN** the `async with` block exits
- **THEN** the caller sees the in-flight `ValueError("x")`
- **AND** `RuntimeError("y")` was logged at WARN and not re-raised
