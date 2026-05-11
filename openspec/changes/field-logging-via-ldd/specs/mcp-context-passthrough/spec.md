# mcp-context-passthrough — field-logging-via-ldd delta

## MODIFIED Requirements

### Requirement: CLI transport supplies a fastmcp.Context-shaped stub

The CLI runtime SHALL bind a CLI-specific stub class (`StderrToolContext`)
to the `ctx` parameter. The stub SHALL expose every public method of
`fastmcp.Context` as listed in the FastMCP version pinned in
`pyproject.toml`, with **signatures matching `fastmcp.Context` exactly**
(modulo `self`). Stub behavior is defined per-method:

- `debug`, `info`, `warning`, `error` — signature
  `(message: str, logger_name: str | None = None, extra: Mapping[str, Any] | None = None)`.
  Emit a stderr line in the LDD wire format `[ +s.mmm LEVEL] message k=v ...`
  where `k=v` pairs come from `extra` (plus a synthesised `logger=...`
  pair when `logger_name` is provided). The stub SHALL NOT accept
  arbitrary `**fields` kwargs; the kwargs form is reserved for
  `a2kit.ldd.log` (see below).
- `report_progress(progress, total=None, message=None)` — emit a
  stderr line `[ +s.mmm progress] current=N total=M`.
- `elicit(message, response_type=None, *, response_title=None, response_description=None)` —
  render via stdin loop; sentinel `--decline` returns
  `DeclinedElicitation`; EOF/SIGINT returns `CancelledElicitation`;
  otherwise `AcceptedElicitation(data=...)`.
- `read_resource(uri)` — `file://` URIs return contents; other schemes raise `MCPOnlyError`.
- `set_state`, `get_state`, `delete_state` — per-instance dict scoped to one CLI invocation.
- `send_log_message(level, logger, data)` — emit a stderr line in LDD wire format.
- `sample`, `list_resources`, `list_prompts`, `get_prompt`, `list_roots`,
  `send_notification` — raise `MCPOnlyError`.

#### Scenario: Plain logging works in CLI

- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext) -> str` calling `ctx.info("hi")`
- **WHEN** the tool runs via `<app> tasks t`
- **THEN** stderr contains a line matching `[ +\d+\.\d+ INFO    ] hi`

#### Scenario: Logging with extra works in CLI

- **GIVEN** a tool calling `await ctx.info("hi", extra={"x": 1})`
- **WHEN** the tool runs via CLI
- **THEN** stderr contains a line matching `[ +\d+\.\d+ INFO    ] hi x=1`

#### Scenario: Stub signatures match fastmcp.Context

- **WHEN** `inspect.signature(StderrToolContext.<method>)` is compared
  against `inspect.signature(fastmcp.Context.<method>)` for each of
  `info`, `warning`, `error`, `debug`, `log`, `report_progress`,
  `read_resource`, `elicit`, `set_state`, `get_state`, `delete_state`
- **THEN** the signatures are identical modulo the `self` parameter

#### Scenario: Kwargs on ctx.info are rejected

- **GIVEN** a tool calling `await ctx.info("hi", foo=1)`
- **WHEN** the tool runs via CLI **or** MCP
- **THEN** the call raises `TypeError`. The tool is expected to use
  `await a2kit.ldd.info(ctx, "hi", foo=1)` instead.

### Requirement: LDD event, report, and log primitives are protocol-neutral functions

The library SHALL expose `a2kit.ldd.event(ctx, ...)`,
`a2kit.ldd.report(ctx, ...)`, and `a2kit.ldd.log(ctx, level, msg_or_instance, **fields)`
as free functions that accept any `fastmcp.Context`-shaped object. The
three SHALL share a single dispatch shape (identity-check against the
live ctx type and route to either `ctx.log(extra=...)` on MCP or
`StderrToolContext._emit(...)` on CLI).

`a2kit.ldd.log` SHALL accept two call forms, matching `event`'s
shape verbatim:

- **String form**: `log(ctx, "info", "msg", k=v, ...)`. Third
  positional is the message; remaining kwargs are fields.
- **Instance form**: `log(ctx, "info", instance)`. Third positional
  is a dataclass / pydantic `BaseModel` / object. Message defaults
  to `type(instance).__name__`; fields derive via
  `model_dump(mode="json")` (pydantic), `dataclasses.asdict`
  (dataclass), or `vars(instance)` (fallback). `Enum` values
  are unwrapped to `.value`.

Convenience aliases `a2kit.ldd.info`, `warning`, `error`, `debug`
forward to `log` with the appropriate level literal and accept the
same two forms.

The library SHALL NOT add `event`, `report`, or `log` methods to the
`a2kit.ToolContext` re-export. Existing `--no-events` / `--no-reports`
CLI flags and the `A2KIT_LDD` env var SHALL gate these primitives;
`log` SHALL share the events flag's kill-switch.

#### Scenario: a2kit.ldd.info delivers a structured message on MCP

- **GIVEN** a tool calling `await a2kit.ldd.info(ctx, "starting", batch=2)`
- **WHEN** the tool runs under `<app> serve` via `fastmcp.Client`
- **THEN** the client receives a `notifications/message` whose
  `level="info"`, `message="starting"`, `extra={"batch": 2, "elapsed_ms": ...}`

#### Scenario: a2kit.ldd.info renders the same line on CLI

- **GIVEN** the same tool
- **WHEN** the tool runs via `<app> tasks t`
- **THEN** stderr contains a line matching `[ +\d+\.\d+ INFO    ] starting batch=2`

#### Scenario: Both transports agree on payload contents

- **GIVEN** identical `a2kit.ldd.info(ctx, "x", n=42)` calls under
  MCP and CLI
- **THEN** the structured `extra` payload (or its CLI `key=value`
  rendering) carries the same fields with the same values, except
  for transport-specific framing. `elapsed_ms` appears in both.

#### Scenario: Instance form derives message and fields

- **GIVEN** `@dataclass class ImportStarted: file: str; batch: int`
- **WHEN** `await a2kit.ldd.info(ctx, ImportStarted(file="/x.csv", batch=2))` is called
- **THEN** the delivered payload has `message="ImportStarted"` and
  `extra={"file": "/x.csv", "batch": 2, "elapsed_ms": ...}` on MCP,
  rendering as `[ +s.mmm INFO    ] ImportStarted file=/x.csv batch=2` on CLI

#### Scenario: Instance form and string form produce identical wire payload

- **GIVEN** `MyDC(x=1, y=2)` as a dataclass
- **WHEN** `a2kit.ldd.info(ctx, MyDC(x=1, y=2))` and
  `a2kit.ldd.info(ctx, "MyDC", x=1, y=2)` are called
- **THEN** the delivered `extra` (MCP) or rendered key=value pairs
  (CLI) are identical key-for-key, except `elapsed_ms`

#### Scenario: msg is capped at 60 chars before transport

- **WHEN** `a2kit.ldd.info(ctx, "<200-char string>", k=1)` is called on either transport
- **THEN** the delivered `message` (MCP) or rendered text (CLI) is
  exactly 60 characters with the final character `…`

### Requirement: Field-bearing logging lives on `a2kit.ldd.*`, not on `ctx.*`

The library SHALL document `a2kit.ldd.info` (and siblings) as the
canonical structured-narrative logging primitive. The library SHALL
treat `ctx.info(msg, **fields)` (with kwargs other than `logger_name`
/ `extra`) as an antipattern and reject it at runtime via fastmcp's
narrow signature.

#### Scenario: Antipattern is documented

- **WHEN** the ANTIPATTERNS.md is inspected
- **THEN** an entry exists titled "Kwargs on `ctx.info/warning/error/debug`"
  with the recommended replacement `a2kit.ldd.info(ctx, ...)` and a
  pointer to this requirement.

## REMOVED Requirements

### Requirement: (legacy) Logging works in CLI with kwargs form

**Reason for removal**: the kwarg form `ctx.info("hi", x=1)` was
asserted as the CLI behaviour while crashing under MCP. The
behaviour is replaced by `a2kit.ldd.info(ctx, "hi", x=1)`, which works
identically on both transports. The kwarg form is now rejected at
runtime on both transports.

**Migration**: `s/await ctx\.(info|warning|error|debug)\("([^"]*)", ([^=)]+=.*)\)/await a2kit.ldd.\1(ctx, "\2", \3)/`
catches the documented call shapes. `ctx.info("plain string")` and
`ctx.info("msg", extra={...})` continue to work — they were always
fastmcp-compatible.
