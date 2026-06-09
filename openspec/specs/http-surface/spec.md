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

`{tool_name}` SHALL be the tool's **canonical name** as resolved per `tool-descriptors` (`canonical_name_override` → `slug_leaf` for router verbs → bare `leaf` for app-level verbs). Router verbs SHALL be mounted via `FastAPI.include_router` (the homomorphism, ADR 0028 decision 3): each router becomes an `APIRouter` whose routes are included on the root app, carrying the slug as a grouping tag (`include_router(prefix=…, tags=[slug])` and/or `add_api_route(tags=[slug])`). The rendered route path SHALL be the flat canonical name (`/api/entity_update`), NOT a nested path (`/api/entity/update`) — the path segment is the canonical name so the wire identifier is byte-for-byte identical across MCP, HTTP, the CLI, and the audit log. The slug `tags` cluster the flat paths in the OpenAPI/Swagger document so flat names group without an extra drill-in. App-level verbs SHALL mount on the root app under their bare leaf (`/api/health`), with no slug prefix.

#### Scenario: Read-verb projection is also POST

- **GIVEN** `@a2kit.read async def fetch(*, id: str, db: Database) -> Memory: ...`
- **WHEN** an HTTP client posts `{"id": "x"}` to `/api/fetch` with `Content-Type: application/json`
- **THEN** the response is `200 OK` with the JSON-encoded `Memory`
- **AND** `db: Database` was resolved by the a2kit Container
- **AND** `GET /api/fetch` returns `405 Method Not Allowed`

#### Scenario: Router verb mounts at the flat canonical path with a slug tag

- **GIVEN** `class Entity(a2kit.Router): slug = "entity"` with `@a2kit.read async def update(*, id: str) -> Memory: ...`
- **WHEN** `build_http_app(runtime)` assembles the FastAPI app
- **THEN** a route `POST /api/entity_update` exists (the flat canonical name), and `POST /api/update` does NOT
- **AND** the route is included via `include_router` and carries `tags=["entity"]` so the OpenAPI document groups it under the slug

#### Scenario: App-level verb stays bare at the root

- **GIVEN** an app-level verb `@a2kit.read async def health() -> Health: ...` with no owning router
- **WHEN** `build_http_app(runtime)` assembles the FastAPI app
- **THEN** the route is `POST /api/health` (bare leaf, no slug prefix), mounted directly on the root app

#### Scenario: Explicitly-pinned name is verbatim and unchanged

- **GIVEN** a verb under `slug="jira"` authored `@a2kit.read(canonical_name_override="jira_search")`
- **WHEN** the FastAPI app is assembled
- **THEN** the route is `POST /api/jira_search` exactly — the slug is not re-applied (never `/api/jira_jira_search`)
- **AND** the path is byte-for-byte identical to the pre-migration explicit-name route

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

- **GIVEN** a runtime with one `@a2kit.read` tool and one `@app.api.get("/x")` route
- **WHEN** `build_http_app(runtime)` runs (the thin shim)
- **THEN** the resulting FastAPI app has both routes mounted, identical to pre-migration behaviour

### Requirement: Tool errors render to typed envelope with kind-mapped status

When a tool raises an `AppError` (or any subclass, including `UnexpectedDefect`) and it propagates through to the HTTP surface, the FastAPI sub-app SHALL render the response by reading the `RenderedError` from `_render_state` (populated by `ErrorEnvelopeStage` during pipeline folding) via `get_rendered_error(exc)`. The HTTP-side render stage (`HttpErrorRenderStage` in `packages/http/`) SHALL convert that `RenderedError` to a FastAPI `JSONResponse` with:

- **Status code**: from `AppError.http_status` if set, else from the `kind` map defined in `error-envelope-rendering` (`input=400, auth=401, policy=403, infra=503, bug=500`). The `NotFound` / `Timeout` subclass conventions (404, 504) realised via class-level `http_status` overrides.
- **Body**: `{"error": <envelope as dict>}` per the `ErrorEnvelope` schema (taken from `RenderedError.envelope_dict`).
- **`Content-Type`**: `application/json`.

The HTTP surface SHALL NOT re-derive the `kind → status` mapping inside `_install_typed_error_handlers` for AppError-shaped errors; the existing FastAPI exception-handler stack SHALL handle only non-AppError fallthrough (framework validation errors, generic `500` for unhandled exceptions that bypassed the pipeline).

The HTTP surface SHALL NOT emit `HTTPException`-default plain-text responses, raw stack traces, or any wire shape other than the typed envelope for errors that propagate from tool bodies (including `@app.api.*` author-written routes whose body raises an `AppError`).

#### Scenario: NotFound returns 404 with envelope body via the render stage

- **GIVEN** a tool whose body raises `NotFound(...)` (with class `http_status = 404`)
- **WHEN** an HTTP client posts to the tool's route
- **THEN** the response status is `404`
- **AND** the response body is `{"error": {"type":"NotFound","kind":"input","retryable":false,"hint":...,"details":...,"envelope_version":"1"}}`
- **AND** `Content-Type: application/json`
- **AND** the body bytes are byte-equal to the pre-change snapshot for the same `NotFound` raise

#### Scenario: Generic InfrastructureError returns 503

- **GIVEN** a tool whose body raises `InfrastructureError(...)` (kind=infra, no http_status override)
- **WHEN** an HTTP client invokes the tool
- **THEN** the response status is `503`
- **AND** body is `{"error": {"kind":"infra", "retryable":true, ...}}`

#### Scenario: Unhandled KeyError quarantined as 500 UnexpectedDefect

- **GIVEN** a tool body that raises `KeyError("foo")` with no enricher coverage
- **WHEN** an HTTP client invokes the tool
- **THEN** the response status is `500`
- **AND** body is `{"error": {"type":"UnexpectedDefect","kind":"bug","retryable":false,"cause":{"trace_id":"..."}}}`
- **AND** body does NOT contain a `KeyError` string

#### Scenario: HTTP error path reads from `_render_state`, not from re-derivation

- **WHEN** `packages/http/build.py` and the new `HttpErrorRenderStage` are inspected
- **THEN** neither contains a `kind → http_status` lookup table
- **AND** the rendered envelope dict comes from `get_rendered_error(exc).envelope_dict`
- **AND** `_apply_authorize_gate` does not exist

### Requirement: Per-request DI scope continues to honor typed-error propagation

Errors raised inside the per-request DI scope (opened by the substrate-rewritten wrapper per `di-per-call-scope`) SHALL propagate through the enricher chain before scope teardown. Scope teardown SHALL NOT suppress, rewrap, or mask typed errors; it SHALL run cleanup hooks and re-raise.

This preserves the contract that the typed envelope reaches the wire intact regardless of scope-cleanup activity.

#### Scenario: Error inside DI scope reaches the wire as envelope

- **GIVEN** a tool with a SCOPED provider that raises an unrelated exception during cleanup AFTER the tool body raised `NotFound`
- **WHEN** invoked via HTTP
- **THEN** the response carries the `NotFound` envelope (the primary error)
- **AND** the cleanup exception is logged but does not displace the wire envelope

