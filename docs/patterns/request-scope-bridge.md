# Request-scope bridge

`a2kit.packages.context.request_scope` (re-exported as
`a2kit.packages.dispatch.request_scope`) is the single typed
substrate→dispatch bridge for per-request values: Principal, the
per-request DI container, log state, and any future request-scoped
type the framework adopts.

## The shape

```python
from a2kit.packages.context import request_scope

# Substrate (auth middleware, http middleware, log scope opener):
token = request_scope.publish(principal, call_scope, container)
try:
    # ... run the request
finally:
    request_scope.reset(token)

# Reader (dispatch stage, FastAPI bridge, log primitive):
principal = request_scope.get(Principal)            # raises on miss
maybe_scope = request_scope.try_get(_CallScope)        # returns None on miss
```

Publish is variadic. Each value is keyed by `type(value)`. Last-write-wins
on collision. `reset(token)` atomically clears every value the
returning `publish` added.

## The failure mode

`get(T)` raises `request_scope.RequestScopeMissing` when no scope is
open OR when no value of type `T` is published. The exception carries
`.requested_type` and a message pointing at substrate middleware order
as the most common cause:

```
RequestScope has no value of type 'Principal'. Substrate middleware
did not publish() it; check the middleware order at the transport
boundary.
```

`try_get(T)` returns `None` instead — use it when the absence is
expected (anonymous requests, optional features).

## When to publish

- **Substrate auth boundary** (`packages/auth/api_key.py`,
  `packages/mcp/principal_middleware.py`, the http FastAPI
  `_install_authorize_principal_bridge`) publishes the `Principal`.
- **HTTP request middleware** (`packages/http/build.py`) publishes the
  per-request `Container` child.
- **log scope opener** (`packages/log/ambient.py:bind_call_scope`)
  publishes the `_CallScope`. Every transport opens this scope around
  the tool body.

## When to read

- **Dispatch stages** (`DispatchHookStage`, `AuthorizeGateStage`) call
  `request_scope.all_seeds()` to thread framework-tier seeds into
  `Container.call_scope(framework_seeds=...)`.
- **log primitives** (`event`, `report`, `log`) read `_CallScope` via
  `request_scope.try_get(_CallScope)`, raising `RequestScopeMissing`
  (a `LookupError`) when absent.
- **FastAPI bridge** reads the per-request `Container` via the
  DI-package-local `_a2kit_request_scope` ContextVar (kept inside the
  DI package for standalone-shippability; the http middleware
  dual-writes).

## Adding a new request-scoped type

Adding a 4th value (TenantId, TraceContext, RequestId) is cheap:

1. One `request_scope.publish(tenant_id)` call at the substrate seam.
2. One `request_scope.get(TenantId)` call at the reader.

No new ContextVar. No new bridge module. No new noqa. The N+1 cost
is two lines plus a test.

## Layer placement

`request_scope` lives in `packages/context/` (layer 0). Earlier drafts
sketched it in `packages/dispatch/`, but the L0 log ambient module
needs to publish to it, and `log→dispatch` would invert the layer DAG.
`packages/dispatch.request_scope` is a re-export of the canonical
context home.

## See also

- `openspec/specs/request-scope/spec.md` — locked contract.
- `openspec/specs/dispatch-pipeline/spec.md` — `framework_seeds=` rename.
- `openspec/specs/principal-propagation/spec.md` — deprecation shim notes.
- `ANTIPATTERNS.md` entry 31 — "Don't add a new per-type ContextVar bridge."
