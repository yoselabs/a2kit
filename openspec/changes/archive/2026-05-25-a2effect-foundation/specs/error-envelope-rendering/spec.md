## ADDED Requirements

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
