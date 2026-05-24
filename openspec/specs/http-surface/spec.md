# http-surface Specification

## Purpose

The FastAPI sub-application mounted at `/api` under `serve --transport=http`.
Materialized from add-multi-surface (archived 2026-05-23).
Supersedes rest-surface.

## Requirements

### Requirement: The HTTP surface is a FastAPI sub-application

The HTTP surface SHALL be produced by `a2kit.packages.http.build_http_app(runtime)` which SHALL return a `fastapi.FastAPI` instance. The multiplexed server SHALL mount it under `/api`. `build_http_app` and the `a2kit.packages.http` package SHALL be importable only on the `serve --transport=http` path; `import a2kit` SHALL NOT transitively import `fastapi`.

#### Scenario: build_http_app returns a FastAPI instance

- **GIVEN** an `AppRuntime` with at least one projection tool exposed on `"api"`
- **WHEN** `build_http_app(runtime)` is called
- **THEN** the returned value is a `fastapi.FastAPI` instance
- **AND** it carries one route per exposed tool plus any author-written `@app.api.*` routes

#### Scenario: HTTP module is not imported eagerly

- **WHEN** `import a2kit` runs in a fresh interpreter
- **THEN** `a2kit.packages.http` is absent from `sys.modules`
- **AND** `fastapi` is absent from `sys.modules`

### Requirement: Projection tools become POST routes at `/api/{tool_name}`

For every projection tool with `"api" in expose`, the HTTP surface SHALL register a route `POST /api/{tool_name}` regardless of verb. Read/list/write verbs all map to POST. Rationale: the projection surface mirrors MCP's `tools/call` RPC shape over HTTP — one wire shape per tool, request body carries wire params as JSON, response body is the JSON-encoded return value. RESTful verb-mapping (`read`→GET) is intentionally NOT used because it would split each tool's contract across two HTTP methods, complicating idempotency semantics for clients that consume both `/api` and MCP.

#### Scenario: Read-verb projection is also POST

- **GIVEN** `@a2kit.read async def fetch(*, id: str, db: Database) -> Memory: ...`
- **WHEN** an HTTP client posts `{"id": "x"}` to `/api/fetch` with `Content-Type: application/json`
- **THEN** the response is `200 OK` with the JSON-encoded `Memory`
- **AND** `db: Database` was resolved by the a2kit Container
- **AND** `GET /api/fetch` returns `405 Method Not Allowed`

### Requirement: Per-request DI scope is opened inside the generated wrapper

For every HTTP request to a projection or `@app.api.*` route whose handler has Container-known parameters, the framework SHALL open a per-call DI scope inside the wrapper body. The scope lifecycle, concurrency semantics, and exception-handling contract are defined by the `di-per-call-scope` capability. This requirement only asserts the HTTP-side entry point: scope-opening happens inside the substrate-rewritten wrapper produced by `a2kit.packages.dispatch.install_substrate_signature`, NOT via a Starlette middleware.

#### Scenario: HTTP wrapper opens the scope inside its body

- **WHEN** the FastAPI sub-app is built and a request arrives for any handler with Container-known params
- **THEN** the per-call scope is opened inside the wrapper body before the author function runs
- **AND** the FastAPI middleware stack does NOT contain a "per-call scope" middleware

### Requirement: Test seam for swapping Container-known dependencies

To swap a Container-known dependency in HTTP handler tests, callers SHALL re-register the test provider on a fresh `App` before `build()` (`App.provide` is last-write-wins). FastAPI's `dependency_overrides[T]` SHALL NOT route to Container-known types because those types are not registered as `Depends` callables.

#### Scenario: Re-providing on a fresh App swaps the dep

- **GIVEN** `@a2kit.read async def fetch(*, db: Database) -> Memory: ...` and a test that wants `db` replaced with `FakeDatabase()`
- **WHEN** the test constructs `a2kit.App("test").add_router(R()).provide(Database, lambda: FakeDatabase())` and builds the runtime
- **THEN** the handler resolves `db` as the `FakeDatabase` instance

#### Scenario: dependency_overrides does NOT swap Container-known deps

- **GIVEN** an `App` whose `Database` is provided through `provide()`
- **WHEN** the test does `fastapi_app.dependency_overrides[Database] = FakeDatabase`
- **THEN** the handler resolves `db` from the original Container provider, NOT the fake

### Requirement: HTTP build installs the DI bridge

`build_http_app` SHALL install a FastAPI middleware that opens a per-request a2kit child container and publishes it on the `_a2kit_request_scope` contextvar before any FastAPI dependency callable runs. It SHALL also invoke `Container.expose_as_fastapi_depends(T)` for every container-known type referenced by any descriptor's container-bucket or substrate-dep chain, registering the result in `fastapi_app.dependency_overrides[T]`. FastAPI Depends/Security callables keyed on `T` (via `Annotated[T, Depends(T)]`) then resolve through the a2kit bridge.

#### Scenario: dependency_overrides populated for container-known types

- **GIVEN** an app with `Database` registered in the container and an `@app.api.get` route whose handler / guard uses `Annotated[Database, Depends(Database)]`
- **WHEN** `build_http_app(runtime)` returns
- **THEN** `fastapi_app.dependency_overrides` contains an entry whose key is `Database`
- **AND** the registered resolver returns the container's scoped `Database` instance on every request

### Requirement: `ApiSurface` satisfies the `Surface` Protocol

`ApiSurface` SHALL subclass `DecoratorSurface[ApiRoute]` and SHALL set `name = "api"`, `reserved_types = frozenset({Request, Response, BackgroundTasks, WebSocket})`, `substrate_dep_markers = frozenset({fastapi.params.Depends, fastapi.params.Security})`. The body of `build_http_app` SHALL move into `ApiSurface.bind`; the existing function SHALL become a thin shim calling `ApiSurface().bind(...)`. `packages/http/__init__.py` SHALL register `ApiSurface()` with `SURFACE_REGISTRY` at lazy load.

#### Scenario: ApiSurface registered at lazy load

- **WHEN** `import a2kit.packages.http` first runs in a fresh interpreter
- **THEN** `SURFACE_REGISTRY.get("api")` returns an `ApiSurface()` instance

#### Scenario: build_http_app remains observably equivalent

- **GIVEN** a runtime with one `@app.read` tool and one `@app.api.get("/x")` route
- **WHEN** `build_http_app(runtime)` runs (the thin shim)
- **THEN** the resulting FastAPI app has both routes mounted, identical to pre-migration behaviour
