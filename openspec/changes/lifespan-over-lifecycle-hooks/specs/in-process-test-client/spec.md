# in-process-test-client — lifespan-over-lifecycle-hooks delta

## MODIFIED Requirements

### Requirement: In-process test client

The system SHALL provide `a2kit.testing.client(app)` — an async
context manager that runs the full dispatcher in-process and
exposes capture surfaces for assertions. On `__aenter__`, the
test client SHALL enter the App's `lifespan` (if any) exactly
once by calling `app.lifespan(app)` — the lifespan signature is
fixed at `(app,)` per the `app-lifecycle` capability; the test
client SHALL NOT introspect or resolve any kwargs. On `__aexit__`,
the test client SHALL exit the same lifespan exactly once,
including on exceptional exit. If the App has no
`lifespan=`, the test client SHALL use `contextlib.nullcontext()`
in its place (no setup, no teardown).

#### Scenario: invoke runs the same code path as production dispatch

- **WHEN** a test calls `await client.invoke("tasks.create", name="x")` on an app with `TasksRouter`
- **THEN** the dispatcher resolves DI, runs decorator processing, executes the tool body, and returns the value the tool returned

#### Scenario: App lifespan fires around the test session

- **GIVEN** an `App` constructed with a `lifespan=` callable that records enter/exit events
- **WHEN** a test enters `async with a2kit.testing.client(app) as c:`, invokes a tool, and exits the block
- **THEN** the lifespan entered before the first invoke and exited after the block, exactly once each

#### Scenario: App with no lifespan uses nullcontext

- **GIVEN** an `App` constructed without a `lifespan=`
- **WHEN** a test enters and exits `async with a2kit.testing.client(app) as c:`
- **THEN** no lifecycle code runs; `__aenter__` and `__aexit__` succeed without raising

#### Scenario: Lifespan exits on exceptional exit

- **GIVEN** an `App` with a `lifespan=` whose post-yield code records "exited"
- **WHEN** a test enters `async with a2kit.testing.client(app) as c:` and the block raises an exception
- **THEN** the lifespan post-yield code ran (exit observed) and the original exception still propagates to the test
