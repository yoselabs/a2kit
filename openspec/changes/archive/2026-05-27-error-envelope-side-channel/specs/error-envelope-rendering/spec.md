## MODIFIED Requirements

### Requirement: Rendered prose and envelope live on an explicit per-call side channel

The framework SHALL carry `ErrorEnvelopeStage`-rendered prose and envelope dict on an explicit per-call side channel, NOT as attributes on the in-flight `AppError` instance. The side channel SHALL be a `ContextVar[dict[int, RenderedError] | None]` opened by the dispatch pipeline at call entry and closed at call exit, keyed by `id(exc)`. The `AppError` class SHALL NOT acquire a `rendered_prose` or `rendered_envelope_dict` field; the exception is a pure domain value.

#### Scenario: AppError instance is unmutated

- **GIVEN** a tool body raising `InvalidInput("x")`
- **WHEN** the dispatch pipeline runs end-to-end and `ErrorEnvelopeStage` produces rendered output
- **THEN** `hasattr(exc, "rendered_prose") is False`
- **AND** `hasattr(exc, "rendered_envelope_dict") is False`
- **AND** `get_rendered_error(exc)` returns a populated `RenderedError`

#### Scenario: Side channel is per-call isolated

- **GIVEN** two concurrent calls each raising distinct `AppError` instances
- **WHEN** both calls' `ErrorEnvelopeStage` runs
- **THEN** `get_rendered_error(exc_a)` returns A's render
- **AND** `get_rendered_error(exc_b)` returns B's render
- **AND** neither call sees the other's render state

#### Scenario: Side channel is cleared on scope exit

- **GIVEN** a dispatched call that wrote to the side channel
- **WHEN** the per-call scope exits (normally or via exception)
- **THEN** the side channel for that call is empty
- **AND** no entry leaks to subsequent calls in the same process

### Requirement: Transport render stages retrieve rendered state via the typed accessor

`McpErrorRenderStage` and `CliErrorRenderStage` SHALL retrieve rendered prose and envelope via `get_rendered_error(exc) -> RenderedError | None` — NOT via `getattr(exc, "rendered_prose", ...)` or any other untyped attribute lookup. When `get_rendered_error(exc)` returns `None` (defensive case: an exception slipped through without `ErrorEnvelopeStage` running), the render stage MAY fall back to `str(exc)` and `exc.to_envelope_dict()`, but the fallback path SHALL be documented inline as defensive-only.

#### Scenario: MCP render stage uses the typed accessor

- **WHEN** `McpErrorRenderStage` handles a `CapturedError` whose wrapped exception is an `AppError`
- **THEN** it calls `get_rendered_error(exc)` to retrieve `RenderedError`
- **AND** the prose and envelope it forwards to the FastMCP middleware come from that `RenderedError`

#### Scenario: CLI render stage uses the typed accessor

- **WHEN** `CliErrorRenderStage` handles a `CapturedError` whose wrapped exception is an `AppError`
- **THEN** it calls `get_rendered_error(exc)` to retrieve `RenderedError`
- **AND** the prose it writes to stderr comes from that `RenderedError`

### Requirement: Envelope module is free of `ty: ignore[unresolved-attribute]` for render fields

`packages/dispatch/envelope.py` SHALL NOT contain any `# ty: ignore[unresolved-attribute]` comment relating to `rendered_prose` or `rendered_envelope_dict`. The static analyser SHALL pass clean for this module after the migration.

#### Scenario: Grep test enforces the invariant

- **WHEN** `grep -rn "ty: ignore\[unresolved-attribute\]" src/a2kit/packages/dispatch/envelope.py` runs
- **THEN** the output is empty
