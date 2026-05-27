## MODIFIED Requirements

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
