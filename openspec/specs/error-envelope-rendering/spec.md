# error-envelope-rendering Specification

## Purpose
TBD - created by archiving change a2effect-foundation. Update Purpose after archive.
## Requirements
### Requirement: Single-mode wire rule — structuredContent only when info differs

The framework SHALL emit `structuredContent` ONLY when its payload carries information that `content[0].text` does not. The decision SHALL be deterministic and based on result type, not on configuration:

- **Success, structured return** (any pydantic `BaseModel`, `dict`, `list`, tuple): `content[0].text = json.dumps(model_dump)`, `structuredContent` omitted, `isError = false`.
- **Success, primitive return** (`str`, `int`, `float`, `bool`): `content[0].text = str(value)`, `structuredContent` omitted, `isError = false`.
- **Success, `None` return**: `content[0].text = "ok"`, `structuredContent` omitted, `isError = false`.
- **Error** (any `AppError` including `UnexpectedDefect`): `content[0].text` carries human prose (LLM-readable), `structuredContent = {"error": <envelope dict>}` (machine-readable, carries fields not in prose), `isError = true`.

There SHALL be no configuration knob for this behavior. The rule is fixed.

#### Scenario: Success with Memory model emits text only

- **GIVEN** a tool returning `Memory(id="abc", text="hi")`
- **WHEN** the MCP renderer serializes the result
- **THEN** the result has `isError: false`
- **AND** `content[0].text == json.dumps({"id":"abc","text":"hi"})`
- **AND** the result does NOT contain a `structuredContent` field

#### Scenario: Error emits both channels with different info

- **GIVEN** a tool that raises `NotFound("memory id 'abc' does not exist", details={"id":"abc"})` with `hint = "verify..."` on the class
- **WHEN** the MCP renderer serializes the result
- **THEN** `isError == true`
- **AND** `content[0].text` is the formatted prose (kind label + message + hint)
- **AND** `structuredContent == {"error": {"type":"NotFound","kind":"input","base_kind":"input","retryable":false,"hint":"verify...","details":{"id":"abc"},"envelope_version":"1"}}`
- **AND** `content[0].text` does NOT contain the JSON envelope

### Requirement: Error prose format is fixed and predictable

Error rendering to `content[0].text` SHALL follow the fixed format:

```
{KindLabel} ({Type}): {message}

Hint: {hint}
```

Where:

- `{KindLabel}` SHALL be the human-readable label for the kind: `"Input error"` for `input`, `"Authentication required"` or `"Authorization denied"` for `auth` (selectable via the AppError subclass providing `kind_label_override`), `"Not allowed"` for `policy`, `"Service unavailable"` for `infra`, `"Internal error"` for `bug`.
- `{Type}` SHALL be the `AppError` subclass name.
- `{message}` SHALL be the message passed to the `AppError` constructor (or `str(exc)`).
- The `Hint: ...` line SHALL be present only when `hint` is non-None; absent otherwise (no empty line, no `"Hint: None"`).

#### Scenario: Prose format with hint

- **GIVEN** `NotFound("memory id 'abc' does not exist")` with class-level `hint = "verify the id from list_memories"`
- **WHEN** rendered
- **THEN** the text equals exactly:
  ```
  Input error (NotFound): memory id 'abc' does not exist

  Hint: verify the id from list_memories
  ```

#### Scenario: Prose format without hint

- **GIVEN** `InvalidId("bad format")` with `hint = None`
- **WHEN** rendered
- **THEN** the text equals exactly:
  ```
  Input error (InvalidId): bad format
  ```
- **AND** no trailing newline-Hint sequence appears

### Requirement: HTTP status code map from kind with per-class override

For HTTP rendering of errors, the framework SHALL map kind to status code per this table when `http_status` is not explicitly set on the `AppError` subclass:

| kind | status |
|---|---|
| input | 400 |
| auth | 401 |
| policy | 403 |
| infra | 503 |
| bug | 500 |

Subclasses MAY override via `http_status: ClassVar[int]`. Pythonic convention: `AppError` subclasses whose name contains `"NotFound"` SHOULD use `http_status = 404` (override on the subclass); subclasses whose name contains `"Timeout"` SHOULD use `http_status = 504`.

The HTTP error response body SHALL be `{"error": <envelope as dict>}` with `Content-Type: application/json`.

#### Scenario: NotFound maps to 404 via class override

- **GIVEN** `class NotFound(AppError): kind = "input"; http_status = 404`
- **WHEN** the HTTP renderer serializes
- **THEN** the response status is `404`
- **AND** the body is `{"error": {"type":"NotFound", ...}}`

#### Scenario: Generic InputError defaults to 400

- **GIVEN** `class InvalidId(AppError): kind = "input"` (no http_status override)
- **WHEN** rendered for HTTP
- **THEN** status is `400`

### Requirement: CLI exit code map from kind with per-class override

For CLI rendering of errors, the framework SHALL map kind to exit code per sysexits.h conventions when `cli_exit_code` is not explicitly set:

| kind | exit code | sysexits constant |
|---|---|---|
| input | 2 | (Unix convention for usage errors) |
| auth | 77 | EX_NOPERM |
| policy | 77 | EX_NOPERM |
| infra | 75 | EX_TEMPFAIL |
| bug | 70 | EX_SOFTWARE |

Subclasses MAY override via `cli_exit_code: ClassVar[int]`.

The CLI error output SHALL go to stderr formatted as the prose form (kind label + message + hint). stdout SHALL remain empty on error unless `--json` is set (see CLI capability for `--json` behavior).

#### Scenario: Input error exits 2

- **GIVEN** a tool raises `NotFound(...)` (kind=input)
- **WHEN** invoked via the CLI
- **THEN** the process exit code is `2`
- **AND** the prose form is written to stderr
- **AND** stdout is empty

#### Scenario: Infra error exits 75

- **GIVEN** a tool raises `InfrastructureError(...)` (kind=infra)
- **WHEN** invoked via the CLI
- **THEN** the process exit code is `75`

### Requirement: outputSchema is auto-generated as oneOf union

For every tool whose return annotation is `Annotated[ReturnT, Raises(E1, ..., En)]`, the framework SHALL emit the MCP `outputSchema` as:

```json
{"oneOf": [<ReturnT JSON Schema>, {"$ref": "#/components/schemas/ErrorEnvelope"}]}
```

For tools without `Raises(...)`, the `outputSchema` SHALL be the bare ReturnT schema (no union).

The `ErrorEnvelope` schema SHALL be defined exactly once in the MCP server's schema components and `$ref`'d from every tool's outputSchema. This SHALL prevent per-tool descriptor bloat.

The lint rule `A2K-OUTPUT-SCHEMA-COMPAT` SHALL fire if a tool author manually sets `outputSchema` on the decorator in a way that contradicts the annotation-derived schema (e.g., omitting the union when `Raises(...)` is declared).

#### Scenario: Tool with Raises gets oneOf union outputSchema

- **GIVEN** `Annotated[Memory, Raises(NotFound)]` return annotation
- **WHEN** the MCP `tools/list` response is built
- **THEN** the tool's `outputSchema == {"oneOf": [{"$ref":"#/components/schemas/Memory"}, {"$ref":"#/components/schemas/ErrorEnvelope"}]}`
- **AND** the response's `components.schemas.ErrorEnvelope` is defined exactly once

### Requirement: Rendered prose and envelope live on an explicit per-call side channel

The framework SHALL carry `ErrorEnvelopeStage`-rendered prose and envelope dict on an explicit per-call side channel, NOT as attributes on the in-flight `AppError` instance. The side channel SHALL be a `ContextVar[dict[int, RenderedError] | None]` opened by the transport adapter (CLI entry point or MCP middleware) before invoking the folded dispatch pipeline and closed on exit, keyed by `id(exc)`. The `AppError` class SHALL NOT acquire a `rendered_prose` or `rendered_envelope_dict` field; the exception is a pure domain value.

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

### Requirement: Envelope module is free of `ty: ignore[unresolved-attribute]` for render fields

`packages/dispatch/envelope.py` SHALL NOT contain any `# ty: ignore[unresolved-attribute]` comment relating to `rendered_prose` or `rendered_envelope_dict`. The static analyser SHALL pass clean for this module after the migration.

#### Scenario: Grep test enforces the invariant

- **WHEN** `grep -rn "ty: ignore\[unresolved-attribute\]" src/a2kit/packages/dispatch/envelope.py` runs
- **THEN** the output is empty

