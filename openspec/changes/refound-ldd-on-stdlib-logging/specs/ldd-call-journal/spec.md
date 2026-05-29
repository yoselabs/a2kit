## ADDED Requirements

### Requirement: Per-call correlation id
Every tool dispatch SHALL mint a unique `call_id` published on the
request scope, available to all handlers and to consumer-enrichment
calls for the lifetime of the call. Concurrent dispatches SHALL receive
distinct ids.

#### Scenario: concurrent calls get distinct ids
- **WHEN** two tools dispatch concurrently
- **THEN** each call's emissions and journal record carry a distinct `call_id`

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

### Requirement: Dispatch-boundary auto-capture
The journal SHALL capture each tool call's arguments, result, timing,
and principal at the dispatch boundary via a `DISPATCH_PIPELINE` stage,
without requiring the tool author to emit anything.

#### Scenario: a silent tool still gets a journal record
- **WHEN** a tool that makes no emission calls completes under an enabled journal
- **THEN** a journal record exists with its args, result, timing, and principal

### Requirement: Consumer record enrichment
A consumer SHALL be able to attach additional fields (including large
bodies) to the active call's journal record via a `journal_attach`
primitive, merged under the active `call_id`. Intermediate values not
visible at the dispatch boundary (e.g. raw HTML, extracted markdown) are
the consumer's responsibility to attach.

#### Scenario: consumer attaches bodies to its own record
- **WHEN** a tool calls `journal_attach(raw_html=..., extracted_md=...)` during dispatch
- **THEN** those fields are merged into the journal record under the current `call_id`
