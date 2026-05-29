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

### Requirement: Call-record enrichment is a general primitive
Any code running within a dispatch SHALL be able to attach additional
fields to the active call's record via a `journal_attach`-style primitive,
merged under the active `call_id`. The primitive is NOT consumer-specific:
a consumer attaches domain payloads (e.g. raw HTML, extracted markdown);
a future policy-ledger gate attaches its verdict and evidence under the
same seam. Fields land in the record's open `extra` bag so core stays
ignorant of any enricher's domain vocabulary.

#### Scenario: consumer attaches bodies to its own record
- **WHEN** a tool calls `journal_attach(raw_html=..., extracted_md=...)` during dispatch
- **THEN** those fields are merged into the call record under the current `call_id`

#### Scenario: a second enricher merges without clobbering the first
- **WHEN** two enrichers attach disjoint fields under the same `call_id`
- **THEN** the record carries the union of both contributions
