## ADDED Requirements

### Requirement: `AppError` sealed base with ClassVar metadata

The `a2effect.AppError` class SHALL be the sole base for typed errors recognised by the framework. Subclasses SHALL declare:

- `kind: ClassVar[ErrorKind]` (required) — one of the five core kinds `"input"`, `"auth"`, `"policy"`, `"infra"`, `"bug"`, or an extended kind registered via the extension registry (see `Open kind extension via base_kind` requirement below).
- `retryable: ClassVar[bool]` (default `False`) — whether the agent or framework should retry.
- `hint: ClassVar[str | None]` (default `None`) — actionable remediation guidance.
- `http_status: ClassVar[int | None]` (default `None`) — explicit HTTP status override; if `None`, status SHALL derive from `kind` per `error-envelope-rendering`.
- `cli_exit_code: ClassVar[int | None]` (default `None`) — explicit CLI exit-code override; if `None`, code SHALL derive from `kind`.

Instances MAY override `retryable` and `hint` per-raise (e.g., `InfrastructureError("...", retryable=True)`). Class-level `kind` SHALL NOT be overridable per-instance.

`AppError` itself SHALL be abstract: subclasses without `kind` declared SHALL raise `TypeError` at class-creation time.

#### Scenario: Subclass with kind passes class-creation

- **GIVEN** `class NotFound(AppError): kind = "input"`
- **WHEN** the class body is evaluated
- **THEN** the class is created without error
- **AND** `NotFound("x").kind == "input"`
- **AND** `NotFound("x").retryable is False`
- **AND** `NotFound("x").hint is None`

#### Scenario: Subclass without kind raises TypeError

- **GIVEN** `class Bad(AppError): pass`
- **WHEN** the class body is evaluated
- **THEN** a `TypeError` is raised at class-creation time
- **AND** the message names the missing `kind` attribute

#### Scenario: Per-instance override of retryable

- **GIVEN** `class InfrastructureError(AppError): kind = "infra"; retryable = True`
- **WHEN** an author raises `InfrastructureError("conn refused", retryable=False)`
- **THEN** the instance's `retryable` attribute is `False`
- **AND** the class default remains `True`

### Requirement: Five core kinds frozen for v1; open extension via `base_kind`

The framework SHALL recognise exactly five core `ErrorKind` values in v1: `"input" | "auth" | "policy" | "infra" | "bug"`. Adding a sixth core kind in any subsequent version is a wire-breaking change.

Consumers MAY register extended kinds via `a2effect.register_error_kind(name, base, retryable=False)`. The extension SHALL carry a `base` field referencing one of the core kinds; the wire envelope SHALL carry both `kind` (specific) and `base_kind` (core fallback) so clients ignorant of the extension fall back to core-kind handling.

#### Scenario: Core kind is accepted on subclass

- **WHEN** a subclass declares `kind = "input"`
- **THEN** the class is created
- **AND** `cls().base_kind == "input"`

#### Scenario: Extended kind registered with base falls back on the wire

- **GIVEN** `a2effect.register_error_kind("rate_limit", base="infra", retryable=True)`
- **AND** `class RateLimit(AppError): kind = "rate_limit"`
- **WHEN** `RateLimit("hit").to_envelope()` is called
- **THEN** the envelope contains `kind == "rate_limit"` AND `base_kind == "infra"` AND `retryable is True`

#### Scenario: Unregistered extended kind raises at class-creation

- **GIVEN** no registration for `"weird"`
- **WHEN** `class Weird(AppError): kind = "weird"` is evaluated
- **THEN** a `TypeError` is raised naming the unknown kind and listing accepted core kinds

### Requirement: `ErrorEnvelope` is the wire schema for typed errors

The `a2effect.ErrorEnvelope` pydantic model SHALL be the canonical structure for typed errors on every wire (MCP `structuredContent.error`, HTTP body `error`, CLI `--json` output). Fields:

- `type: str` — the AppError subclass name (e.g., `"NotFound"`).
- `kind: str` — the specific kind (core or extended).
- `base_kind: str` — the core kind (mirrors `kind` when no extension is in play).
- `retryable: bool` — whether to retry.
- `hint: str | None` — actionable guidance.
- `details: dict[str, Any]` — structured data carried by the raise (e.g., the bad id).
- `cause: dict | None` — optional `{type: str, message: str, trace_id: str}` when the error was raised `from another_exception`. The trace correlation ID points to server-side logs.
- `envelope_version: Literal["1"]` — version marker for forward-compatibility.

Authors SHALL NOT construct `ErrorEnvelope` instances directly; the framework's translation pipeline produces them from raised `AppError` instances.

#### Scenario: Envelope round-trips via pydantic

- **GIVEN** `env = NotFound("x", details={"id":"abc"}).to_envelope()`
- **WHEN** the envelope is serialized via `env.model_dump_json()` and re-parsed via `ErrorEnvelope.model_validate_json(...)`
- **THEN** the resulting envelope equals the original
- **AND** `env.envelope_version == "1"`

#### Scenario: Envelope carries cause chain when raised `from`

- **GIVEN** a tool that runs `try: raise asyncpg.NoData(); except asyncpg.NoData as e: raise NotFound("x") from e`
- **WHEN** the framework produces the envelope
- **THEN** `envelope.cause.type == "asyncpg.NoData"`
- **AND** `envelope.cause.message` is the original exception's string
- **AND** `envelope.cause.trace_id` is a server-side correlation ID resolvable in logs

### Requirement: `UnexpectedDefect` quarantines uncategorised exceptions

The framework SHALL wrap any exception that escapes the enricher chain in `a2effect.UnexpectedDefect(original)`. `UnexpectedDefect` SHALL be a final subclass of `AppError` with `kind = "bug"`, `retryable = False`. The original exception SHALL be preserved on `__cause__`. The wire envelope SHALL carry the typed boundary plus a `cause.trace_id` for server-side log lookup; raw exception types, raw messages, and stack traces SHALL NOT appear on the wire.

`UnexpectedDefect` SHALL also quarantine `asyncio.CancelledError`, `KeyboardInterrupt`, and `SystemExit` in v1. A future change MAY promote cancellation to a dedicated `kind = "cancelled"` via the extension registry.

#### Scenario: Unhandled KeyError becomes UnexpectedDefect

- **GIVEN** a tool body that raises `KeyError("foo")` not covered by any enricher and not in any declared `Raises(...)`
- **WHEN** the tool is invoked
- **THEN** the wire envelope has `type == "UnexpectedDefect"`, `kind == "bug"`, `retryable is False`
- **AND** the original `KeyError` is logged server-side with a correlation ID
- **AND** the envelope's `cause.trace_id` matches the log entry's correlation ID
- **AND** the wire payload does NOT contain `"KeyError"` as a top-level type

#### Scenario: asyncio.CancelledError quarantined as defect

- **GIVEN** a tool that propagates `asyncio.CancelledError`
- **WHEN** dispatch completes
- **THEN** the envelope has `type == "UnexpectedDefect"`, `kind == "bug"`
- **AND** the `cause.type == "asyncio.CancelledError"`
