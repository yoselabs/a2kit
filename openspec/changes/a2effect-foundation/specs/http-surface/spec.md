## ADDED Requirements

### Requirement: Tool errors render to typed envelope with kind-mapped status

When a tool raised an `AppError` (or any subclass, including `UnexpectedDefect`) escapes through to the HTTP surface, the FastAPI sub-app SHALL render the response with:

- **Status code**: from `AppError.http_status` if set, else from the `kind` map defined in `error-envelope-rendering` (`input=400, auth=401, policy=403, infra=503, bug=500`). The Pythonic `NotFound`/`Timeout` subclasses convention (404, 504) is realised via class-level `http_status` overrides on those subclasses.
- **Body**: `{"error": <envelope as dict>}` per the `ErrorEnvelope` schema.
- **`Content-Type`**: `application/json`.

The HTTP surface SHALL NOT emit `HTTPException`-default plain-text responses, raw stack traces, or any wire shape other than the typed envelope for errors that propagate from tool bodies (including `@app.api.*` author-written routes whose body raises an `AppError`).

#### Scenario: NotFound returns 404 with envelope body

- **GIVEN** a tool whose body raises `NotFound(...)` (with class `http_status = 404`)
- **WHEN** an HTTP client posts to the tool's route
- **THEN** the response status is `404`
- **AND** the response body is `{"error": {"type":"NotFound","kind":"input","retryable":false,"hint":...,"details":...,"envelope_version":"1"}}`
- **AND** `Content-Type: application/json`

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

### Requirement: Per-request DI scope continues to honor typed-error propagation

Errors raised inside the per-request DI scope (opened by the substrate-rewritten wrapper per `di-per-call-scope`) SHALL propagate through the enricher chain before scope teardown. Scope teardown SHALL NOT suppress, rewrap, or mask typed errors; it SHALL run cleanup hooks and re-raise.

This preserves the contract that the typed envelope reaches the wire intact regardless of scope-cleanup activity.

#### Scenario: Error inside DI scope reaches the wire as envelope

- **GIVEN** a tool with a SCOPED provider that raises an unrelated exception during cleanup AFTER the tool body raised `NotFound`
- **WHEN** invoked via HTTP
- **THEN** the response carries the `NotFound` envelope (the primary error)
- **AND** the cleanup exception is logged but does not displace the wire envelope
