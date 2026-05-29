## ADDED Requirements

### Requirement: Per-call correlation id is a request-scope primitive
Every tool dispatch SHALL mint a unique `call_id` published on the
request scope as a standalone primitive — available to ANY dispatch
stage and to log records for the lifetime of the call, independent of
whether the call-log is enabled. Concurrent dispatches SHALL receive
distinct ids. (Rationale: a gate stage such as a future policy ledger
needs `call_id` correlation even with the call-log off; `call_id` is the
shared spine, not a call-log-internal detail.)

#### Scenario: concurrent calls get distinct ids
- **WHEN** two tools dispatch concurrently
- **THEN** each call's log records and call-log record carry a distinct `call_id`

#### Scenario: call_id exists even when the call-log is disabled
- **WHEN** a tool dispatches with the call-log off
- **THEN** a `call_id` is still minted on the request scope and readable by other stages

#### Scenario: concurrent calls do not cross-contaminate (verified)
- **WHEN** multiple tool calls run concurrently under `asyncio.gather` and interleave at `await` points
- **THEN** each call reads only its own `call_id` (per-task `copy_context` + copy-on-write `request_scope.publish`)
- **AND** a child task spawned inside a call inherits that call's `call_id`

### Requirement: The call record is span-shaped
The `CallRecord` SHALL carry `trace_id`, `span_id`, and `parent_span_id`
alongside `call_id`, modelled on the OpenTelemetry span data model — WITHOUT
importing the OpenTelemetry SDK (the SDK's cold-start cost is rejected on
the same grounds as structlog, ADR 0020). `parent_span_id` enables nested
tool calls (a tool that dispatches another tool) to record parent/child
structure. The shape SHALL be trivially convertible to an OTLP span so the
`otel` handler can export it for opt-in consumers.

#### Scenario: a nested tool call records its parent
- **WHEN** a tool dispatches another tool within its own dispatch
- **THEN** the inner call's record carries the outer call's `span_id` as its `parent_span_id`

#### Scenario: contextvars do not cross a thread boundary (documented edge)
- **WHEN** a tool offloads work to a raw `threading.Thread` or `ProcessPoolExecutor`
- **THEN** the worker does NOT inherit the `call_id` (standard Python contextvar limitation) and MUST capture+rebind or pass `call_id` explicitly

### Requirement: The call record is an access-log on a dedicated non-streaming logger
The dispatch-boundary stage SHALL emit each call record on a dedicated
logger `a2kit.calls` configured with `propagate=False`. Only the call-log
file handler SHALL be attached to `a2kit.calls`; the MCP wire handler and
the stdout/CLI handler SHALL NOT be attached to it. Consequently a call
record (and any `debug` body routed to the call-log file) SHALL be
structurally incapable of reaching the agent stream or stdout — the agent
already holds the tool's return value, so streaming a structured copy is
redundant. This guarantee SHALL hold regardless of per-handler level
configuration (e.g. it MUST hold even with the wire level set to DEBUG).

#### Scenario: a call record never reaches the wire
- **WHEN** a tool dispatches under an enabled call-log and the MCP wire level is set to DEBUG
- **THEN** the structured call record appears in the call-log file but NOT in the MCP wire stream

#### Scenario: a debug body never prints to stdout
- **WHEN** a tool logs `a2kit.log.debug("html", html=h)` in CLI mode
- **THEN** the body is captured in the call-log file (if on) but is NOT printed to stdout (which carries only the rendered result + info+ commentary)

### Requirement: Opt-in durable call-log file handler
The framework SHALL ship a call-log file handler that persists call
records at full fidelity (no text cap). Records SHALL be written as one
JSON object per line (jsonl), with large bodies content-addressed to
sidecar files (hash stored in the row, body in `bodies/<hash>`) above a
size threshold. Newline-bearing values SHALL be JSON-escaped so each
record stays one physical line. The row SHALL carry at least `call_id`,
`ts`, `tool`, `domain`, `principal`, `elapsed_ms`, the span fields, and
the hash of each persisted body. The call-log SHALL be opt-in via
configuration (default off); when off, the boundary stage SHALL self-skip
and no file SHALL be written.

#### Scenario: large body is content-addressed, not inlined
- **WHEN** a call persists a body larger than the inline threshold
- **THEN** the body is written to a sidecar keyed by its content hash, and the jsonl row carries the hash, not the body

#### Scenario: domain filter does not read sidecars
- **WHEN** the call-log is queried by `domain` (DuckDB over the jsonl)
- **THEN** the matching rows are selected from the jsonl columns without reading any blob sidecar

#### Scenario: off by default writes nothing
- **WHEN** a tool dispatches with `CALL_LOG` off (the default)
- **THEN** no call-log file is written and the boundary stage self-skips

### Requirement: Dispatch-boundary auto-capture (transport-neutral)
The call-log SHALL capture each tool call's arguments, result, timing,
and principal at the dispatch boundary via a transport-neutral
`DISPATCH_PIPELINE` stage (NOT a per-transport handler), without
requiring the tool author to emit anything. The captured `result` SHALL
be the raw return VALUE snapshotted BEFORE the per-transport formatter,
so the captured fields are identical regardless of which interface (CLI /
MCP / HTTP / in-process) the call arrived through.

#### Scenario: a silent tool still gets a call record
- **WHEN** a tool that makes no log calls completes under an enabled call-log
- **THEN** a call record exists with its args, result, timing, and principal

#### Scenario: identical captured fields across interfaces
- **WHEN** the same tool call is dispatched via CLI and via MCP
- **THEN** the call records carry identical captured fields (args, raw result value, principal) — the invariant is identical CAPTURED FIELDS, not byte-identical wire output

#### Scenario: an erroring tool is captured as a typed error
- **WHEN** a tool raises instead of returning
- **THEN** the record captures the typed error in the result position (not a missing/half record)

#### Scenario: a streaming return is captured as its materialized value
- **WHEN** a tool returns a generator / async-iterator
- **THEN** the record captures the materialized value (or an explicit streamed-marker), never a bare `<generator object>`

### Requirement: Enrichment is debug logging correlated by call_id
The framework SHALL provide no dedicated enrichment verb. Domain values
the dispatch boundary cannot see (intermediate locals such as raw HTML or
extracted markdown) SHALL be added to the durable record by logging them
at `debug` on `a2kit.log`. The active `call_id` SHALL be auto-injected onto every
such record by the filter, so the call-log file holds both the auto
call-record and the debug rows sharing one `call_id`; a full call is
reconstructed by grouping on `call_id` (the access-log / app-log join pattern).
There SHALL be NO `journal.record(...)` / `attach(...)` API and NO merged
single-record-per-call contract.

#### Scenario: consumer enriches via a debug log
- **WHEN** a tool calls `a2kit.log.debug("html", html=h)` during dispatch under an enabled call-log (DEBUG level)
- **THEN** a row carrying `html` and the active `call_id` is written to the call-log file, groupable with the auto call-record by `call_id`

#### Scenario: capture is call-I/O only; scoring metadata is consumer-correlated
- **WHEN** an eval harness computes `cost_usd` / `cache_hit` outside the tool call (no active call scope)
- **THEN** those are NOT auto-captured; they enter the record only if the harness correlates them by an explicit `call_id` it carries (the call-log replaces the I/O dump, not the scoring layer)
