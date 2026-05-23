## ADDED Requirements

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

- **GIVEN** `@app.read async def fetch(*, id: str, db: Database) -> Memory: ...`
- **WHEN** an HTTP client posts `{"id": "x"}` to `/api/fetch` with `Content-Type: application/json`
- **THEN** the response is `200 OK` with the JSON-encoded `Memory`
- **AND** `db: Database` was resolved by the a2kit Container
- **AND** `GET /api/fetch` returns `405 Method Not Allowed`

### Requirement: Per-request DI scope is opened inside the generated wrapper

For every HTTP request to a projection or `@app.api.*` route whose handler has Container-known parameters, the framework SHALL open a per-call DI scope inside the wrapper body. The scope lifecycle, concurrency semantics, and exception-handling contract are defined by the `di-per-call-scope` capability. This requirement only asserts the HTTP-side entry point: scope-opening happens inside the substrate-rewritten wrapper, NOT via a Starlette middleware.

#### Scenario: HTTP wrapper opens the scope inside its body

- **WHEN** the FastAPI sub-app is built and a request arrives for any handler with Container-known params
- **THEN** the per-call scope is opened inside the wrapper body before the author function runs
- **AND** the FastAPI middleware stack does NOT contain a "per-call scope" middleware

### Requirement: `container.override(T, fake)` is the test seam

To swap a Container-known dependency in HTTP handler tests, callers SHALL use `runtime.container.override(T, fake)` (the existing Container override API). FastAPI's `dependency_overrides[T]` SHALL NOT be expected to work for Container-known types because they are not registered as `Depends` callables.

The documentation SHALL state this explicitly with a worked example in both the README and the change's test fixtures.

#### Scenario: container.override swaps a Container-known dep in tests

- **GIVEN** `@app.read async def fetch(*, id: str, db: Database) -> Memory: ...` and a test that wants `db` replaced with `FakeDatabase()`
- **WHEN** the test runs the handler inside `async with runtime.container.override(Database, FakeDatabase()):`
- **THEN** the handler resolves `db` as the `FakeDatabase` instance
- **AND** outside the `with` block the original provider is restored

#### Scenario: dependency_overrides does NOT swap Container-known deps

- **GIVEN** the same setup
- **WHEN** the test does `app.api.fastapi_app.dependency_overrides[Database] = FakeDatabase` and runs the handler without `container.override`
- **THEN** the handler resolves `db` from the original Container provider, NOT the fake
- **AND** the test framework documentation explains why `container.override` is the right seam
