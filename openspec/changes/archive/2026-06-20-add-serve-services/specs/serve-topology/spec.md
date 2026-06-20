## ADDED Requirements

### Requirement: App-registered on-serve services run inside the serve runtime lifecycle

An `App` SHALL be able to register **on-serve services** — coroutine functions
of the shape `async def (ctx: ServeContext) -> None` — via a `serve_services`
authoring ClassVar (a tuple), consistent with the `routers=` / `providers=`
axes. `build()` SHALL carry the registered services onto the `AppRuntime`, and
`serve` SHALL launch each registered service as a concurrent task **inside** the
single `async with runtime:` that the listeners run under, so services share the
one DI root container and its `SINGLETON` store handle.

Each service SHALL be invoked as `service(ServeContext(internal_uds=<bound
--internal-uds path or None>, transport=<"stdio"|"http">))`. `ServeContext`
SHALL be a frozen value object exported from the public surface (e.g.
`a2kit.ServeContext`) carrying exactly the bound `internal_uds` and the
`transport`.

Services SHALL be launched **only** by `serve`. Ordinary CLI verb dispatch SHALL
NOT start any service. An App that registers no services SHALL behave exactly as
before this change.

#### Scenario: A CLI verb starts zero services

- **WHEN** any non-`serve` CLI verb runs (e.g. `--help`, `entity read`)
- **THEN** no registered service is invoked

#### Scenario: Services start eagerly at serve start

- **WHEN** `serve` starts for an App with registered services
- **THEN** each service is invoked at serve start, not deferred to the first tool
  dispatch

#### Scenario: The bound internal-uds path reaches the service

- **WHEN** `serve --internal-uds PATH` runs
- **THEN** each service receives `ctx.internal_uds == PATH`
- **AND WHEN** `serve` runs without `--internal-uds`
- **THEN** each service receives `ctx.internal_uds is None`

#### Scenario: Services share the one runtime and store handle

- **WHEN** a service and the listeners run under the same `serve`
- **THEN** they resolve through the same entered `AppRuntime` / `SINGLETON`
  container (no second runtime is entered for services)

### Requirement: serve supervises listeners and services with asymmetric shutdown

`serve` SHALL supervise the union of its listeners (the public listener, and the
spoke listener when `--internal-uds` is set) and its registered services such
that:

- a **listener** exiting (cleanly or by error) SHALL end serve and cancel the
  remaining tasks;
- **any** task raising an exception SHALL tear serve down and propagate the
  exception (nonzero exit);
- a **service** that returns cleanly SHALL NOT end serve — the listeners keep
  serving.

On teardown, outstanding tasks SHALL be cancelled and awaited (best-effort)
before the spoke socket is cleaned up. A registered service that never returns
(e.g. a poll loop) SHALL NOT cause serve to hang on shutdown.

#### Scenario: A never-returning service does not hang shutdown

- **WHEN** a registered service loops indefinitely and the listener stops
  (signal / EOF)
- **THEN** serve cancels the service and exits without hanging

#### Scenario: A service returning cleanly does not stop serve

- **WHEN** a registered service returns immediately at serve start
- **THEN** the listeners continue serving normally

#### Scenario: A crashing service tears serve down

- **WHEN** a registered service raises
- **THEN** serve cancels the listeners and the run exits nonzero

## MODIFIED Requirements

### Requirement: stdio `serve` is a single-protocol MCP surface

The default `serve` transport (stdio) SHALL serve the MCP surface only,
because a stdio pipe cannot multiplex more than one protocol. Surface narrowing
on the `http` transport is expressed with `--select 'surface=...'` (the
`runtime-tool-selection` capability), not with dedicated surface flags.
Regardless of transport, `serve` SHALL run the public listener, any spoke
listener, and any registered services under a **single** `async with runtime:`
(the runtime entered once, exited last); the previously distinct bare
single-listener paths no longer exist as separate code paths.

#### Scenario: stdio still serves MCP

- **WHEN** the app is started with `serve` and no transport flag
- **THEN** the MCP surface is served over stdio exactly as before this change

#### Scenario: A bare serve with no spoke and no services is unchanged externally

- **WHEN** `serve` runs without `--internal-uds` and the App registers no services
- **THEN** the observable MCP (stdio) / multiplex (http) behavior is identical to
  before this change, though it is now produced by the one supervised engine
