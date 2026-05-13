# operational-contracts — mcp-structured-wire-error-envelope delta

## MODIFIED Requirements

### Requirement: Error envelope for unhandled tool exceptions

The system SHALL produce a documented error envelope when a tool body raises an exception other than `CancelledError`. The envelope contract on the **MCP wire** SHALL be owned by a2kit and SHALL NOT depend on FastMCP's `mask_error_details` flag or any other FastMCP-internal masking behavior.

When a tool body or its wrapper chain raises an exception that is not `FastMCPError` (or subclass), not `asyncio.CancelledError`, not `KeyboardInterrupt`, not `SystemExit`, and not a `BaseExceptionGroup` containing only `CancelledError`s, the MCP runtime SHALL emit a response with `isError: true` whose `content[0].text` is a JSON-encoded payload with at minimum:

- `class`: the unqualified Python class name of the exception (`type(exc).__name__`)
- `message`: the result of `str(exc)`

When `App(debug=True)`, the payload SHALL additionally include:

- `traceback`: the result of `traceback.format_exc()` at the point of catch

`fastmcp.exceptions.FastMCPError` and subclasses (including author-raised `ToolError`) SHALL propagate unwrapped so author-shaped error messages reach the wire on FastMCP's own path. `asyncio.CancelledError`, `KeyboardInterrupt`, and `SystemExit` SHALL propagate unwrapped (they are `BaseException` siblings outside the catch scope). A `BaseExceptionGroup` containing only `CancelledError`s SHALL propagate unwrapped.

The CLI transport is unchanged: exceptions surface as `error: <message>` on stderr (with traceback under `debug=True`) and a non-zero process exit code.

#### Scenario: MCP path emits structured payload

- **GIVEN** a tool `async def t() -> None` whose body raises `ValueError("bad input")`
- **WHEN** the tool is invoked via `fastmcp.Client(transport=build_mcp_server(app))` with `App(debug=False)`
- **THEN** the response has `isError=True`
- **AND** `json.loads(response.content[0].text) == {"class": "ValueError", "message": "bad input"}`

#### Scenario: debug flag includes traceback in MCP envelope

- **GIVEN** the same tool with `App(debug=True)`
- **WHEN** the tool is invoked over MCP
- **THEN** the JSON payload contains keys `class`, `message`, and `traceback`
- **AND** the `traceback` value contains the line `"ValueError: bad input"`

#### Scenario: CLI path exits non-zero with traceback to stderr

- **WHEN** a tool body raises during CLI invocation
- **THEN** the process exits with non-zero status
- **AND** the traceback appears on stderr

#### Scenario: Author-raised ToolError passes through unwrapped

- **GIVEN** a tool body `raise ToolError("permission denied")`
- **WHEN** invoked over MCP with `App(debug=False)`
- **THEN** the response has `isError=True`
- **AND** `response.content[0].text == "permission denied"` (NOT JSON-wrapped)

#### Scenario: CancelledError propagates unwrapped

- **GIVEN** a tool body `raise asyncio.CancelledError()`
- **WHEN** invoked over MCP
- **THEN** cancellation surfaces to the client; the server does NOT emit a structured-error envelope for cancellation

#### Scenario: Envelope is FastMCP-independent

- **GIVEN** an a2kit App whose MCP server is built against the pinned FastMCP version
- **WHEN** a tool raises `ValueError` and FastMCP's hypothetical `mask_error_details` flag is set to either `True` or `False`
- **THEN** the wire payload is identical: `{"class": "ValueError", "message": ...}`
- **AND** the envelope shape does NOT depend on the `mask_error_details` setting
