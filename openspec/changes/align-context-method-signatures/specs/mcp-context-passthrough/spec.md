# mcp-context-passthrough — align-context-method-signatures delta

## MODIFIED Requirements

### Requirement: CLI transport supplies a fastmcp.Context-shaped stub

The CLI runtime SHALL bind a CLI-specific stub class (`StderrToolContext`)
to the `ctx` parameter. **Every public method on the stub SHALL have a
runtime signature identical to its counterpart on `fastmcp.Context`**
(modulo `self`), as verified by
`inspect.signature(StderrToolContext.<method>) == inspect.signature(fastmcp.Context.<method>)`.

Method bodies are defined per-method:

- `debug`, `info`, `warning`, `error` (defined by `field-logging-via-ldd`)
  — emit a stderr line via `_emit`; structured-field form lives on
  `a2kit.ldd.*`.
- `log(message, level=None, logger_name=None, extra=None)` — emit a
  stderr line via `_emit` honouring `level`, `logger_name`, and
  `extra`.
- `report_progress(progress, total=None, message=None)` — emit a
  stderr progress line.
- `read_resource(uri: str | AnyUrl) -> ResourceResult` — for `file://`
  URIs, read the file and return a `ResourceResult` wrapping the
  content; for any other scheme, raise `MCPOnlyError`.
- `elicit(message, response_type, *, response_title=None, response_description=None)`
  — `response_type` is validated against the documented overload
  union (`type[T] | list[str] | dict[str, dict[str, str]] | None`);
  unsupported forms raise `MCPOnlyError`. Stdin loop handles
  `None` / `type[T]` / `list[str]` forms.
- `set_state`, `get_state`, `delete_state` — per-instance dict scoped
  to one CLI invocation.
- `sample`, `sample_step`, `get_prompt`, `list_resources`,
  `list_prompts`, `list_roots`, `send_notification` — signature
  matches fastmcp; body raises `MCPOnlyError`.

The stub SHALL NOT define `send_log_message`. Tools needing
protocol-neutral structured logging use `a2kit.ldd.log`; tools needing
MCP-protocol-level logging use `ctx.session.send_log_message`
(available only under MCP transport).

#### Scenario: Every public method signature matches fastmcp.Context

- **WHEN** `inspect.signature(getattr(StderrToolContext, m))` is
  compared against `inspect.signature(getattr(fastmcp.Context, m))`
  for every public name `m` in `dir(fastmcp.Context)` that's not in
  `MCP_ONLY`
- **THEN** the signatures are identical

#### Scenario: read_resource returns a ResourceResult on file:// URIs

- **GIVEN** a tool calling `await ctx.read_resource("file:///tmp/x.txt")` in CLI
- **WHEN** the file exists
- **THEN** the return value is a `ResourceResult` (or duck-typed
  equivalent) whose `content` attribute matches the file's bytes/text

#### Scenario: elicit rejects unsupported response_type forms

- **GIVEN** a tool calling `await ctx.elicit("prompt", response_type=SomeComplexNestedType)`
  on CLI where `SomeComplexNestedType` is outside the documented
  overload union
- **WHEN** the call executes
- **THEN** it raises `MCPOnlyError` with a hint pointing at the
  documented `type[T] | list[str] | dict[str, dict[str, str]] | None`
  shape

#### Scenario: send_log_message is absent from the stub

- **WHEN** a tool calls `await ctx.send_log_message(...)` in CLI
- **THEN** the call raises `AttributeError` — the method does not
  exist on `StderrToolContext`. The recommended migration is
  `await a2kit.ldd.log(ctx, level, msg, **fields)`.

## REMOVED Requirements

### Requirement: (legacy) Stub supplies send_log_message

**Reason for removal**: `send_log_message` is not a method on
`fastmcp.Context` (it lives on `ctx.session`). The stub inventing it
created a CLI-only method whose calls would `AttributeError` under
MCP transport — the same class of bug `field-logging-via-ldd`
repaired for the four logging methods.

**Migration**: replace `await ctx.send_log_message(level, logger,
data)` with one of:

- `await a2kit.ldd.log(ctx, level, message, **data)` — recommended;
  protocol-neutral.
- `await ctx.session.send_log_message(level, logger, data)` — fastmcp-
  native; MCP transport only.
