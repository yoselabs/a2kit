# di-scope-cleanup-stack Specification

## Purpose
TBD - created by archiving change di-scoped-lifecycle. Update Purpose after archive.
## Requirements
### Requirement: Each scope owns a custom cleanup stack distinct from `AsyncExitStack`

Each container scope (App-scope root container and per-call child containers) SHALL own its own cleanup stack data structure that records entered resources in insertion order. The stack SHALL NOT use `contextlib.AsyncExitStack` directly. The cleanup stack SHALL be a simple list of `(resource_descriptor, aclose_callable)` tuples, populated as resources are entered through resolution.

#### Scenario: Cleanup stack is not AsyncExitStack

- **WHEN** the source of `a2kit.packages.di` is grepped for `"AsyncExitStack"`
- **THEN** no usage matches outside docstrings that document the explicit non-use

#### Scenario: Cleanup stack records entries in resolution order

- **GIVEN** three app-scope resources `A`, `B(A)`, `C(B)` registered, where each depends on the previous
- **WHEN** a tool dispatches that resolves `C` (transitively requiring `A` then `B` then `C`)
- **THEN** the App-scope cleanup stack contains entries for `A`, `B`, `C` in that order (FIFO insertion)

### Requirement: Cleanup stack unwinds in LIFO order with per-resource exception isolation

When a scope closes, the framework SHALL iterate the cleanup stack in reverse insertion order (LIFO) and invoke each entry's cleanup callable. Each invocation SHALL be wrapped in `try/except` such that a raised exception during one resource's cleanup SHALL be logged via `logging.getLogger("a2kit.di.cleanup")` at level WARN with traceback, and unwinding SHALL continue with the remaining entries. The framework SHALL NOT re-raise individual cleanup exceptions during unwind.

#### Scenario: Bad cleanup logged and skipped

- **GIVEN** three resources entered in order `A`, `B`, `C` where `B`'s cleanup raises `RuntimeError("bad")`
- **WHEN** the scope closes
- **THEN** `C`'s cleanup runs first
- **AND** `B`'s cleanup raises and is logged at WARN with the traceback
- **AND** `A`'s cleanup runs after `B`'s logged failure
- **AND** the scope close completes without re-raising `RuntimeError("bad")`

#### Scenario: Body exception is preserved when cleanup also raises

- **GIVEN** a per-call scope where the tool body raised `ToolError("x")` and a per-call resource's cleanup raises `ShutdownError("y")`
- **WHEN** the per-call scope closes
- **THEN** the dispatcher's caller sees `ToolError("x")` (the original tool exception)
- **AND** `ShutdownError("y")` was logged at WARN

### Requirement: Cleanup stack supports both `__aexit__` and async-generator finalization

The cleanup stack SHALL store a uniform cleanup callable regardless of whether the resource was entered via a class with `__aenter__`/`__aexit__` or via an `@asynccontextmanager` generator factory. The container SHALL adapt both forms to a single `Callable[[], Awaitable[None]]` shape stored on the stack:

- Class `__aexit__` form: the stored callable invokes `instance.__aexit__(None, None, None)`.
- Generator form: the stored callable advances the generator past `yield` so its `finally` block runs.

#### Scenario: Class lifecycle resource cleaned up

- **GIVEN** a class `SmtpSender` with `async def __aenter__` and `async def __aexit__`, registered via `app.provide(SmtpSender)`
- **WHEN** the resource is entered during resolution and the scope later closes
- **THEN** `SmtpSender.__aexit__` is invoked exactly once with `(None, None, None)` on normal scope close

#### Scenario: Generator factory resource cleaned up

- **GIVEN** an `@asynccontextmanager` factory `smtp_factory` whose body has `yield sender` then `await sender.disconnect()` in `finally`, registered via `app.provide(SmtpSender, smtp_factory)`
- **WHEN** the resource is entered during resolution and the scope later closes
- **THEN** the generator's `finally` block runs exactly once on normal scope close
- **AND** `sender.disconnect()` was awaited

### Requirement: Cleanup stack is partial-entry-safe

If a resource fails during its own entry (e.g., `__aenter__` raises after partial construction), the framework SHALL NOT record an entry for that resource on the cleanup stack, and SHALL invoke the LIFO unwind of any resources already entered earlier in the current resolution chain. The propagated exception SHALL be the original `__aenter__` exception.

#### Scenario: Partial entry triggers LIFO unwind of already-entered siblings

- **GIVEN** App-scope resources `A` (clean), `B` (raises in `__aenter__`) where `B(A)` declares `A` as a dep
- **WHEN** the first dispatch resolves `B` for the first time
- **THEN** `A.__aenter__` ran, then `B.__aenter__` raised
- **AND** the cleanup stack contains only the entry for `A`
- **AND** the resolution call site sees the original `B.__aenter__` exception
- **AND** subsequent App close runs `A.__aexit__`

#### Scenario: Failed entry not recorded on stack

- **GIVEN** a resource `B` whose `__aenter__` raises
- **WHEN** the first resolution attempt raises
- **THEN** the cleanup stack contains no entry for `B`
- **AND** a subsequent resolution attempt for `B` will retry the factory (no cached failed instance)

### Requirement: Cleanup stack matrix covers the AsyncExitStack-class failure modes

The cleanup-stack implementation SHALL be covered by tests that explicitly exercise the failure modes that bite stdlib `AsyncExitStack` in MCP-adjacent code (cpython #137517, MCP SDK #1213, trio #1243):

- A background task raised during scope close.
- Partially-entered stack on startup failure (resource N+1 fails after N entered).
- Cleanup running inside a wider `TaskGroup` / `gather` context.

These tests SHALL be in `tests/packages/di/test_cleanup_stack.py` and SHALL be referenced from CI as part of the regression contract.

#### Scenario: Test suite contains the bug-class scenarios

- **WHEN** `tests/packages/di/test_cleanup_stack.py` is read
- **THEN** test functions named `test_background_task_exception_during_close`, `test_partial_entry_on_startup_failure`, and `test_cleanup_within_taskgroup_context` exist
- **AND** each function asserts both the propagated exception and the resources that were cleaned up

