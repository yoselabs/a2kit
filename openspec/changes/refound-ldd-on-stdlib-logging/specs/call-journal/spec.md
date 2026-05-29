## ADDED Requirements

### Requirement: Per-call correlation id is a request-scope primitive
Every tool dispatch SHALL mint a unique `call_id` published on the
request scope as a standalone primitive — available to ANY dispatch
stage and to enrichment calls for the lifetime of the call, independent
of whether the journal handler is enabled. Concurrent dispatches SHALL
receive distinct ids. (Rationale: a gate stage such as a future policy
ledger needs `call_id` correlation even with the journal off; `call_id`
is the shared spine, not a journal-internal detail.)

#### Scenario: concurrent calls get distinct ids
- **WHEN** two tools dispatch concurrently
- **THEN** each call's emissions and journal record carry a distinct `call_id`

#### Scenario: call_id exists even when the journal is disabled
- **WHEN** a tool dispatches with the journal handler off
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

### Requirement: Durable call journal handler
The framework SHALL ship a journal handler that persists call records at
full fidelity (no text cap). Records SHALL be written as one JSON object
per line (jsonl), with large bodies content-addressed to sidecar files
(hash stored in the row, body in `bodies/<hash>`). The row SHALL carry
at least `call_id`, `ts`, `tool`, `domain`, `principal`, `elapsed_ms`,
and the hash of each persisted body. The journal SHALL be opt-in via
configuration (default off).

#### Scenario: large body is content-addressed, not inlined
- **WHEN** a call persists a body larger than the inline threshold
- **THEN** the body is written to a sidecar keyed by its content hash, and the jsonl row carries the hash, not the body

#### Scenario: domain filter does not read sidecars
- **WHEN** the journal is queried by `domain`
- **THEN** the matching rows are selected from the jsonl columns without reading any blob sidecar

### Requirement: Dispatch-boundary auto-capture (transport-neutral)
The journal SHALL capture each tool call's arguments, result, timing,
and principal at the dispatch boundary via a transport-neutral
`DISPATCH_PIPELINE` stage (NOT a per-transport handler), without
requiring the tool author to emit anything. The captured `result` SHALL
be the raw return VALUE snapshotted BEFORE the per-transport formatter,
so the captured fields are identical regardless of which interface (CLI /
MCP / HTTP / in-process) the call arrived through.

#### Scenario: a silent tool still gets a journal record
- **WHEN** a tool that makes no emission calls completes under an enabled journal
- **THEN** a journal record exists with its args, result, timing, and principal

#### Scenario: identical captured fields across interfaces
- **WHEN** the same tool call is dispatched via CLI and via MCP
- **THEN** the journal records carry identical captured fields (args, raw result value, principal) — the invariant is identical CAPTURED FIELDS, not byte-identical wire output

#### Scenario: an erroring tool is captured as a typed error
- **WHEN** a tool raises instead of returning
- **THEN** the record captures the typed error in the result position (not a missing/half record)

#### Scenario: a streaming return is captured as its materialized value
- **WHEN** a tool returns a generator / async-iterator
- **THEN** the record captures the materialized value (or an explicit streamed-marker), never a bare `<generator object>`

### Requirement: Capture is call-I/O only; scoring metadata is enrichment
Auto-capture SHALL cover only the tool's own input/output (args, result,
timing, principal). Harness- or consumer-computed metadata that is NOT a
tool argument or return value (e.g. eval cost, cache-hit, model name) is
NOT auto-captured; the consumer enriches the record with it under the same
`call_id`. (Scopes the "subsumes hand-written result dumps" claim: the
journal replaces the I/O dump, not the scoring layer.)

#### Scenario: eval metadata requires enrichment, not auto-capture
- **WHEN** an eval harness computes `cost_usd` / `cache_hit` outside the tool call
- **THEN** those land in the record only if the harness enriches the record under the `call_id`; the auto-capture stage does not invent them

### Requirement: Call-record enrichment is a typed primitive
Any code running within a dispatch SHALL be able to enrich the active
call's record by passing a TYPED payload instance to `journal.record(...)`,
merged under the active `call_id`. The payload uses the SAME typed-instance
grammar as the log level methods (`log.info(instance)`) — not an untyped
`**fields` bag — so it type-checks and two distinct payload kinds namespace
cleanly without key collision. The primitive is sync (it mutates the
active per-call record, not a logging pipe). It is NOT consumer-specific:
a consumer records domain payloads (e.g. raw HTML, extracted markdown); a
future policy-ledger gate records its verdict and evidence under the same
seam. Payloads land in the record's open `extra` bag (keyed by payload
kind) so core stays ignorant of any enricher's domain vocabulary. An
explicit `journal.record(payload, call_id=...)` form SHALL exist for code
running OUTSIDE a dispatch (e.g. a post-hoc eval harness with no active
call scope).

#### Scenario: consumer records a typed payload onto its own record
- **WHEN** a tool calls `journal.record(FetchArtifacts(raw_html=..., extracted_md=...))` during dispatch
- **THEN** the payload's fields are merged into the call record under the current `call_id`, keyed by payload kind

#### Scenario: a second enricher merges without clobbering the first
- **WHEN** two enrichers record disjoint payload kinds under the same `call_id`
- **THEN** the record carries the union of both contributions

#### Scenario: out-of-dispatch enrichment uses an explicit call_id
- **WHEN** an eval harness calls `journal.record(EvalScore(...), call_id=cid)` with no active call scope
- **THEN** the payload is merged into the record identified by `cid`
