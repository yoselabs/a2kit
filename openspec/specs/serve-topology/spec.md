# serve-topology Specification

## Purpose
TBD - created by archiving change multiplex-serve-topology. Update Purpose after archive.
## Requirements
### Requirement: `serve --transport=http` runs a multiplexed server

When `serve` is invoked with `--transport=http`, the framework SHALL run a single process listening on a single port, serving every enabled surface from an a2kit-owned parent ASGI application. Each surface SHALL be a sub-application mounted under a distinct path prefix: the MCP surface under `/mcp`, the REST surface under `/api`. The parent application SHALL be run under an ASGI server (uvicorn). The author SHALL write no transport, mount, or server code to obtain this.

#### Scenario: One process serves both surfaces on one port

- **GIVEN** an `a2kit.App` with at least one registered tool
- **WHEN** the app is started with `serve --transport=http --host=127.0.0.1 --port=8000`
- **THEN** a single process listens on `127.0.0.1:8000`
- **AND** the MCP streamable-HTTP endpoint is reachable under the `/mcp` path
- **AND** the REST surface is reachable under the `/api` path

#### Scenario: MCP is served as a mounted sub-application

- **WHEN** the multiplexed server is built
- **THEN** the MCP surface is the Starlette application returned by `build_mcp_server(app).http_app(...)`, mounted on the parent application
- **AND** the parent application, not the FastMCP server, owns the uvicorn run

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

### Requirement: The multiplex server dependency is imported lazily

The ASGI server (uvicorn) and the parent-application composition SHALL be imported only on the `serve --transport=http` path, never at `import a2kit`. `import a2kit` SHALL NOT import uvicorn.

#### Scenario: `import a2kit` does not import the ASGI server

- **WHEN** `import a2kit` runs in a fresh interpreter
- **THEN** `uvicorn` is absent from `sys.modules`

### Requirement: `AppRuntime` owns the surface set via explicit composition

`a2kit.runtime.build(app)` (or the canonical runtime-construction seam) SHALL accept a `surfaces: tuple[Surface, ...]` parameter with a default of `(McpSurface(), ApiSurface())`. The constructed runtime SHALL carry a per-runtime surface registry (`runtime.surfaces`) populated from this tuple in the order supplied. There SHALL be exactly one canonical owner of the surface set per runtime — the runtime itself — and no other code path SHALL register a surface after build time.

The CLI is now a `Surface` (`CliSurface`, `kind = SurfaceKind.LOCAL`). The top-level CLI SHALL be assembled by `CliSurface.bind(runtime, descriptors)` rather than by a free `build_full_cli` function outside the surface set. Because the CLI is a `LOCAL`-kind surface it is NOT mounted into the network parent ASGI application (it has no `/cli` HTTP path); it is materialized on demand by the CLI entry point (`a2kit.run`) via its surface's `bind`. The default network `surfaces=` tuple therefore stays `(McpSurface(), ApiSurface())` — the `NETWORK` surfaces — while the `LOCAL` CLI surface participates in the same uniform `bind(...)` protocol without changing the mounted-network default.

#### Scenario: Default composition mounts both built-in network surfaces

- **GIVEN** a default `App` (no `surfaces=` override)
- **WHEN** `a2kit.runtime.build(app)` runs
- **THEN** `runtime.surfaces.names()` returns `("mcp", "api")` in declaration order

#### Scenario: Third-party surface composes via explicit argument

- **GIVEN** a custom `class MySurface(Surface)` with `name = "my"`
- **WHEN** `a2kit.runtime.build(app, surfaces=(McpSurface(), ApiSurface(), MySurface()))` runs
- **THEN** `runtime.surfaces.names()` includes `"my"`
- **AND** no module-import side effect was required to mount it

#### Scenario: CLI is assembled via CliSurface.bind

- **GIVEN** a built runtime
- **WHEN** the top-level CLI is produced (the `a2kit.run` entry point)
- **THEN** the command is built by `CliSurface().bind(runtime)`, not by a free `build_full_cli` function outside the surface set
- **AND** because `CliSurface.kind` is `SurfaceKind.LOCAL`, the CLI is not mounted into the network parent ASGI app

### Requirement: `expose=` is validated at runtime build time, not at decoration time

The `@a2kit.read` / `@a2kit.write` / `@a2kit.list_` decorators SHALL capture the `expose=` argument unchanged. Validation against the surface registry SHALL run exactly once, at `runtime.build()` time, after the surface set is composed. The previous cold-start no-op in `_verbs.py:_validate_expose` (which silently passed `expose=` validation when the registry was empty at decoration time) is removed.

#### Scenario: Unknown `expose=` value fails at build time

- **GIVEN** a tool decorated `@a2kit.read(expose=("typo-surface",))`
- **WHEN** `a2kit.runtime.build(app)` runs with the default surface set
- **THEN** build fails with a precise error naming `"typo-surface"` and listing the registered surface names `("mcp", "api")`

#### Scenario: Decoration order does not affect validation

- **GIVEN** `@a2kit.read(expose=("mcp",))` declared in a module imported BEFORE `a2kit.packages.mcp`
- **WHEN** `a2kit.runtime.build(app)` runs
- **THEN** validation succeeds — because the surface set is composed before validation runs, decoration-time ordering is irrelevant

### Requirement: There is no module-level surface registry

The framework SHALL NOT expose a module-level `SURFACE_REGISTRY` global. The per-runtime registry on `runtime.surfaces` is the only canonical access path. Internal callers that need the active registry without a runtime in hand SHALL use `a2kit.packages.dispatch.surface.current_registry()`.

#### Scenario: No module-level global

- **WHEN** code does `from a2kit.packages.dispatch import SURFACE_REGISTRY`
- **THEN** the import raises `ImportError`
- **AND** the only canonical access paths are `runtime.surfaces` (per-runtime) and `current_registry()` (active binding)

### Requirement: Co-resident loopback (UDS) listener shares the one runtime

`serve` (http path) SHALL support an optional second listener bound to a **Unix
domain socket** (the "spoke"), in addition to the public TCP listener. When the
spoke is enabled, `serve` SHALL build the `AppRuntime` **exactly once** and serve
**both** listeners from that single runtime, so they share the one DI root
container and therefore the one `SINGLETON` store handle (single-writer
preserved). The spoke socket SHALL be created with `0600` permissions.

Both listeners' lifespans SHALL be entered under a single `async with runtime:`
(the runtime entered once, exited last), as with the existing multi-surface
parent. The public TCP listener and its mounted surfaces (MCP/HTTP) and their
auth SHALL be unchanged whether or not the spoke is enabled.

The spoke SHALL serve the dispatcher-backed verb surface (same dispatcher, same
validation, audit, `authorize=`, `if_version`, typed errors as the public
surfaces) and SHALL NOT expose a second tool catalog: projected verbs SHALL carry
the identical canonical names served on the public API surface.

#### Scenario: Spoke and public listener share one store handle

- **WHEN** `serve` runs with the spoke enabled and a verb is invoked over the UDS
- **THEN** the call resolves through the same `AppRuntime` and writes through the
  same `SINGLETON` store instance that a TCP call resolves, with no second store
  handle opened

#### Scenario: Public surfaces unaffected by the spoke

- **WHEN** the spoke is enabled
- **THEN** the public TCP listener's MCP/HTTP mounts and their auth behave
  identically to a spoke-disabled run

#### Scenario: Spoke disabled by default

- **WHEN** `serve` runs without the spoke option
- **THEN** only the public TCP listener is started and no Unix socket is created

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

