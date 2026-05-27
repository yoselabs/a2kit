## MODIFIED Requirements

### Requirement: Transport render stages retrieve rendered state via the typed accessor

`McpErrorRenderStage`, `CliErrorRenderStage`, **and `HttpErrorRenderStage`** SHALL retrieve rendered prose and envelope via `get_rendered_error(exc) -> RenderedError | None` — NOT via `getattr(exc, "rendered_prose", ...)` or any other untyped attribute lookup, and NOT via a parallel re-derivation of `AppError → kind → wire-shape`. When `get_rendered_error(exc)` returns `None` (defensive case: an exception slipped through without `ErrorEnvelopeStage` running), the render stage MAY fall back to `str(exc)` and `exc.to_envelope_dict()`, but the fallback path SHALL be documented inline as defensive-only.

#### Scenario: MCP render stage uses the typed accessor

- **WHEN** `McpErrorRenderStage` handles a `CapturedError` whose wrapped exception is an `AppError`
- **THEN** it calls `get_rendered_error(exc)` to retrieve `RenderedError`
- **AND** the prose and envelope it forwards to the FastMCP middleware come from that `RenderedError`

#### Scenario: CLI render stage uses the typed accessor

- **WHEN** `CliErrorRenderStage` handles a `CapturedError` whose wrapped exception is an `AppError`
- **THEN** it calls `get_rendered_error(exc)` to retrieve `RenderedError`
- **AND** the prose it writes to stderr comes from that `RenderedError`

#### Scenario: HTTP render stage uses the typed accessor

- **WHEN** `HttpErrorRenderStage` handles a `CapturedError` whose wrapped exception is an `AppError`
- **THEN** it calls `get_rendered_error(exc)` to retrieve `RenderedError`
- **AND** the `JSONResponse` it returns has `status_code = RenderedError.http_status` and `body = {"error": RenderedError.envelope_dict}`
- **AND** the HTTP render stage source contains no `kind → status` map of its own
