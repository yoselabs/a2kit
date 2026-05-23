## ADDED Requirements

### Requirement: The HTTP substrate opens the per-call scope inside the generated wrapper

The HTTP substrate SHALL open the per-call DI scope inside the substrate-rewritten handler wrapper body, using a `contextvars.ContextVar` to carry the active scope. The scope SHALL be closed in a `finally` block whether the handler returns normally or raises. The HTTP substrate SHALL NOT use a Starlette middleware to manage per-call scopes.

This requirement extends the existing per-call scope contract to the HTTP path with identical semantics — fresh child container per call, LIFO cleanup, per-resource exception isolation — but a different entry point. The MCP path's existing scope-opening behaviour is unchanged.

#### Scenario: HTTP wrapper opens scope before dispatch

- **GIVEN** `@app.read async def fetch(*, id: str, db: Database) -> Memory: ...` registered on the HTTP substrate, with `db` resolved via Container
- **WHEN** an HTTP `POST /api/fetch` request arrives
- **THEN** the generated wrapper enters `Container.call_scope(fn, wire_kwargs)` before invoking `fn`
- **AND** the scope token is set on the contextvar `_a2kit_scope`
- **AND** the scope is exited via `__aexit__` whether `fn` returns or raises

#### Scenario: Two concurrent HTTP requests get distinct SCOPED instances

- **GIVEN** `app.provides(Trace, trace_factory, scope=Scope.SCOPED)` and a tool that resolves `Trace`
- **WHEN** two HTTP clients concurrently POST to the tool's `/api/...` route
- **THEN** each request resolves its own `Trace` instance
- **AND** the two instances are distinct objects

#### Scenario: No Starlette middleware manages the per-call scope

- **WHEN** the FastAPI sub-app is built
- **THEN** the middleware stack does NOT contain a "per-call scope" middleware
- **AND** the per-call scope lifecycle is entirely wrapper-local
