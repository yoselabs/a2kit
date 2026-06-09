# Design — refound LDD on stdlib logging + a durable call access-log

> Decision trail (split-then-unify, the brainstorm rounds) lives in
> ADR 0027's dated amendments. This document is the clean final design.

## The model: one author surface, two logging cases

There is exactly **one author-facing concept: `a2kit.log`** — stdlib
logging level methods (`debug` / `info` / `warning` / `error`). An AI
writing an MCP tool already knows it: "log things that make calls
traceable." Underneath, two *kinds* of record flow, distinguished the way
every Python program already distinguishes them — **by logger and by
level**, not by a second API.

```
   AUTHOR SEES                     ROUTES TO
   ─────────────────────────       ──────────────────────────────────────────
   a2kit.log.info("...", k=v)      app log  → wire(INFO+) · stderr(INFO+) · file(DEBUG+)
   a2kit.log.debug("html", h=…)    app log  → file only (wire/stderr are INFO+)
   a2kit.log.info(TierEnded(...))  app log  → typed instance rides the level method

   <framework, automatic>          access log → its OWN file, NEVER streams
   one record per tool call                   (dedicated a2kit.calls logger)
```

The durable call record is **not a new concept** — it is an **access
log**: one structured record per tool call, auto-emitted on a dedicated
logger, written to its own file, never shown on the console or wire. This
is the exact pattern every web server uses for `access.log`, separate from
application logs. Calling it "logging" is not a category error; it is the
logging idiom *for* this case.

## Two axes, not two APIs: severity × kind

LDD only ever moved along one axis (shape). Two orthogonal axes actually
govern where a record goes:

```
   SEVERITY (how loud)        debug ── info ── warning ── error
                              controls per-handler thresholds:
                              wire/stderr = INFO+, call-log file = DEBUG+
                              → debug is "kept on disk, not streamed"

   KIND (what it is)          commentary  vs  call access-record
                              controls WHICH logger, hence which handlers:
                              commentary → a2kit        (streams + file)
                              call record → a2kit.calls  (file ONLY, propagate=False)
```

Severity handles the author's own logs (`info` is live, `debug` is
file-only — and a 100KB HTML body genuinely *is* debug-level diagnostic
detail). Kind handles the always-on auto-record: it lives on a separate
logger the streaming handlers are not attached to, so it **structurally
cannot** reach the agent or stdout — even if an operator cranks the wire to
`DEBUG`. The author never names that logger; the framework emits to it.

This is why the two routing problems the design once worried about both
vanish into stdlib idiom: "keep bulky data off the stream" = use `debug`;
"keep call records off the stream" = a dedicated logger + `propagate=False`
— three lines, the same three every web framework writes for its access
log.

## The call access-log

```
   calls/2026-05-30.jsonl                 bodies/  (content-addressed)
   ──────────────────────────────         ──────────────────────────
   {call_id, ts, tool:"ask",              ab3f…  ← raw HTML
    domain:"x.com", args:{…},             9c1e…  ← extracted MD
    result_hash:"9c1e", elapsed_ms,
    principal, trace_id, span_id,
    html_hash:"ab3f"}        ← scan-light, query-fast (DuckDB over jsonl)
```

- **Auto-capture at the dispatch boundary** (new `DISPATCH_PIPELINE` stage,
  per ADR 0025): the framework records `args` + `result` + `timing` +
  `principal` for every tool, with no author cooperation. A
  framework-level interceptor is the only layer that can do this uniformly,
  and it is the opposite of the "author narrates" grain — so it belongs in
  a stage, not a `log` call. The stage emits the finalized record on
  `a2kit.calls`.
- **Dedicated non-streaming logger.** `a2kit.calls` has `propagate=False`;
  only the call-log file handler is attached. The wire and stdout handlers
  are attached to `a2kit` (commentary), never to `a2kit.calls`. So the
  agent never sees the structured copy of a result it already has, and the
  CLI never double-prints it. The redundancy you'd otherwise hit is
  designed out by topology, not patched out by a filter.
- **JSONL, queryable.** The file handler writes one JSON object per line;
  DuckDB reads it directly (`read_json_auto`) — `WHERE domain='x.com'`
  works out of the box, the original requirement (analyse later, by AI and
  by hand, filter by domain). Large values are content-addressed to
  `bodies/<hash>` sidecars past a threshold, so domain-scans read thin rows
  and touch a blob only when opened. Newlines inside any value are
  JSON-escaped — every record stays one physical line, losslessly. The
  sidecar threshold is the only sink-internal detail; the author never sees
  it.
- **Opt-in, off by default.** Config under `A2KIT_LOG__`:
  `CALL_LOG = off | on | <path>` (off → stage self-skips, file never
  written, zero cost), `CALL_LOG_LEVEL = DEBUG | INFO` (DEBUG also captures
  the author's `debug` blobs; INFO captures only info+), `WIRE_LEVEL = INFO`
  (always separate — what the agent sees). "Debug mode" is just
  `CALL_LOG=on` + `LEVEL=DEBUG` behind a dev toggle. An idle `log.debug(...)`
  when nothing captures DEBUG is a stdlib no-op (short-circuits before
  formatting); guard with `isEnabledFor(DEBUG)` only if a value is computed
  *solely* to log it.

### Enrichment is just logging — correlated, not merged

The boundary can't see intermediate values (`raw_html`, `extracted_md` are
locals deep in `fetcher.py`, never crossing the dispatch boundary). The
consumer logs them at `debug` with the active `call_id` auto-injected by
the filter:

```python
a2kit.log.debug("html", html=h)          # captured by the call-log file (DEBUG+),
                                          # carries call_id, never streams
```

The file then holds the auto call-record AND the debug row, sharing a
`call_id`. You reconstruct a full call in DuckDB by grouping on `call_id` —
exactly how you'd join an access log to app logs. **No enrichment verb, no
merged-record API.** An earlier draft had `journal.record(Payload)`;
correlation-by-`call_id` removes the need for it and removes the second
concept. (The only case that would want one merged atomic object per call
is one we don't have; correlated rows satisfy the stated use-case.)

## Why an access-log, not an `a2kit.journal` concept

A four-agent brainstorm split emission from recording into two public
namespaces (`a2kit.log` + `a2kit.journal`), reasoning that a durable record
is "not logging." A later turn collapsed that: the durable record *is* a
logging case — the access-log case — and a second public namespace + a
`record()` verb is cognitive tax for something an AI already models as
"logs, saved." The collapse keeps the structural win the split chased: the
**record is still produced by a transport-neutral dispatch stage** (so it's
identical across CLI/MCP/in-process by construction — the "same
side-effects regardless of interface" invariant holds); the logging system
only decides *where* it's written. Best of both — one concept, and the
invariant.

## CallRecord is span-shaped (OTel data model, NOT the OTel SDK)

The record carries `trace_id` / `span_id` / `parent_span_id` alongside
`call_id`, without importing the OTel SDK (its cold-start cost is rejected
on the same ADR-0020 grounds as structlog). Costs ~nothing today and buys:

- **call NESTING** — a tool that dispatches another tool; `parent_span_id`
  makes parent/child a non-breaking field, not a future migration that flat
  `call_id` would force.
- the existing `otel` handler becomes a *real* exporter for opt-in
  consumers; "migrate to OTel" is a config flag, not a rewrite.

"trace" therefore names exactly one thing in this design — the span spine
on the record (`trace_id`/`span_id`) plus the optional `trace` *level*
alias in `levels.py`. It is deliberately NOT the name of the author surface
(that's `a2kit.log`), so the word is not double-booked.

## Verified: per-call isolation holds (eval use-case safe)

A red-team flagged a possible FATAL concurrency bug (parallel calls
cross-contaminating `call_id`). **Falsified empirically** against
`packages/context/request_scope.py`: `publish` is copy-on-write
(`dict(current)` then `_scope.set`), and asyncio Tasks run in a
`copy_context()` snapshot — so `gather`-interleaved calls stay isolated
(A→A, B→B, C→C) and child tasks correctly inherit the parent's `call_id`.
This is the mechanism `feedback_parallel_runs` (A/B eval runs need run_id
isolation) depends on; it works.

Caveat to record in the spec: contextvars do NOT cross a raw
`threading.Thread` / `ProcessPoolExecutor` boundary (standard Python
limitation). A tool offloading to a thread must capture+rebind or pass
`call_id` explicitly. Not an a2kit bug; a documented edge.

## "byte-identical" relaxed; the eval-metadata scope line

- The invariant is **"identical CAPTURED FIELDS across interfaces,"** not
  byte-identical wire output. The capture stage snapshots the raw return
  *value* (pre-formatter) + args + principal + timing. Error cases (no
  return value → captured as a typed error in the result position),
  streaming/generator returns (captured as the materialized value or a
  marker, never a bare generator object), and transport-injected ids are
  defined explicitly in the spec.
- The call-log subsumes **call-I/O capture**, NOT the eval-scoring layer.
  a2web's `fetch_result.json` carries harness-computed metadata
  (`cost_usd`, `cache_hit`, `extraction_model`) that is NOT a tool
  arg/return — it is synthesized by the eval harness, sometimes *outside*
  any dispatch. That stays consumer enrichment, correlated by `call_id`,
  not auto-capture. Honest scope: the call-log replaces the I/O dump, not
  the scoring metadata.

## instance-as-payload stays; the `event()`/`log()` verbs die

a2web has 28 sites passing typed dataclasses (`TierEnded(step=...,
verdict=...)`). Forcing `info("msg", **kwargs)` everywhere loses
construction-time type-checking, IDE autocomplete, and adds boilerplate — a
usability cliff. So a level method accepts `info(instance | msg, **fields)`:
the instance IS the structured payload (dumped into `extra`). The separate
`event()` verb dies (that name goes), and so does the loose `log()` verb;
the *ability* to pass a typed instance survives under the level methods.
The documented common idiom is plain `info("msg", **fields)`; instances are
there for those who want them.

## The unifying mechanism: one record → many handlers

stdlib `logging`'s architecture collapses every stated requirement (CLI
stdout, MCP streaming, token-condensed for the LLM, full-fidelity queryable
for review) into one diagram — handlers differ by level + formatter, and
the call-log handler differs also by *which logger it listens to*:

```
   logger a2kit (commentary)                logger a2kit.calls (auto record)
   author: info/debug/...                   framework: boundary stage
   + call_id/tool/elapsed_ms (Filter)       propagate=False
          │                                          │
   ┌──────┼───────────────┬───────────────┐         │
   ▼      ▼               ▼               ▼         ▼
 stderr  MCP wire      call-log file   (file also  call-log file
 INFO+   INFO+ ASYNC    DEBUG+          gets a2kit  DEBUG+ JSONL
 cond.   cond. inline   JSONL           debug rows) bodies sidecar'd
 fmt     await ctx.log  + bodies                    ← the ONLY handler
                                                       on a2kit.calls
```

Condensing is a property of the LLM-facing handlers (stderr, wire); the
call-log file deliberately does not condense. "Same record, different
formatter — and for the access-record, a different logger" is the entire
answer to STDOUT vs streaming vs token-saving vs full-fidelity.

## Mapping: what LDD has → where it goes

| LDD today | stdlib logging home | fate |
|---|---|---|
| `LDD_LEVEL_RANK` (`levels.py`) | logging levels | fold |
| sinks + `_dispatch_sinks` fan-out | `logging.Handler`s | re-express |
| `wire.py` / `TEXT_CAP` / `format_ldd_line` | a `logging.Formatter` | fold |
| ambient `_LddState` / `ldd_state_for_call` | a `logging.Filter` reading a contextvar | re-express + mint `call_id` |
| `event(Typed)` | `info(instance)` (instance in `extra`) | **keep the ergonomic, drop the verb** |
| `info/debug/warning/error` | thin logger wrappers | keep (cheap) |
| `otel_sink` / `live_sink` / stderr sinks | handlers | re-express, behaviour preserved |
| `report()` / `@reports` / `report_type` | — | **DELETE** (0 callers) |
| `EventRegistry` / `emit_typed` / progress | — | **DELETE** (0 callers) |
| most of `lint/rules/ldd.py` (147 LOC) | — | **DELETE** (nothing bespoke to police) |

## The async wire boundary — RESOLVED: live streaming is mandatory

**Decision (2026-05-29): the wire path streams live, inline.** Live,
mid-call log appearance is the *whole point* of LDD as a dev technique:
when an MCP call takes 30 minutes, you must see what it is doing *as it
runs* — not wait for a terminal dump. Hard requirement, not a preference.

The load-bearing fact: **this already works today**, because the emission
primitives are `async` and `await ctx.log()` **inline** in the tool body —
MCP ships that as a stream notification immediately, mid-call. So the
requirement is **"do not regress streaming,"** not "add streaming."

stdlib `logging.Handler.emit()` is **synchronous** and cannot `await` a
network send. The danger is therefore regression: naively routing the MCP
wire through a sync stdlib `Handler` would destroy the streaming we have.
The binding rule:

```
   The MCP wire emission MUST remain an inline `await ctx.log()` inside the
   async emission primitive. NOT deferred behind a sync stdlib Handler, a
   buffer, or an end-of-call flush. No queue (inline await is simpler and
   lower-latency; a drainer only matters if a slow client must not throttle
   the tool — not a dev-logging concern).

   Sync stdlib Handlers are used ONLY where "now" already means "write
   now": stderr and the call-log JSONL row. The wire is the one channel
   where "now" means "await a send," so it stays async-inline.
```

This *qualifies* the pure-stdlib thesis, it does not abandon it: stdlib
`logging` owns levels, the `call_id` filter, the condensed formatter, and
the sync handlers; the wire fan-out is an awaited inline call. Still
strictly less bespoke machinery than today (which hand-rolls levels,
formatter, and contextvar plumbing *as well as* the async fan-out).

## Why not structlog (recorded so it is not relitigated)

| axis | stdlib shim | structlog | bespoke (today) |
|---|---|---|---|
| owned LOC after change | ~300–400 | ~250–350 | ~1,300 |
| new dependency | none | **+structlog on hot path** | none |
| import cost | free (stdlib) | **~80ms+ (10× a2kit's whole import)** | free |
| new concepts for authors | none (universal) | a learned API | a learned API |
| wire byte-stability | kept for free | costs a custom renderer | kept |
| deletes the 147-LOC lint rule | yes | partly | no |

structlog's value is the *delta over stdlib* (processor-chain ergonomics ≈
50 LOC you'd write once). It deletes the *same* plumbing stdlib deletes,
then charges a hot-path dependency, a ~80ms import (violates the ADR 0020
cold-start guarantee; cf. ADR 0001 reluctantly accepting 70ms for Typer),
and a custom renderer to preserve the wire format — to land where stdlib
already puts us. It also does **not** solve the one hard thing: its async
support runs *sync* handlers off-thread, not native `await` of `ctx.log()`.
Net-negative on code size, cold-start, and deps.

Consumer-side, structlog is fine: ADR 0022 makes app-logging presentation
a consumer-owned concern. a2web may add a structlog handler in its own
composition root if it wants a pretty dev console; a2kit core neither
forces the dep nor eats the import.

## Naming: "LDD" retired — one surface, no second namespace

"LDD" (Logging / Data / Diagnostics) named a bespoke channel this change
deletes. With no backward-compat redundancy, the name goes with it — no
`ldd = log` alias, no shim. The surface sorts two ways (the durable record
is not a third namespace — it collapses into logging as the access-log
case):

```
   DELETE (stdlib logging replaces — renaming dead code = redundancy)
   ──────────────────────────────────────────────────────────────────
   report / @reports / EventRegistry   → gone (zero callers)
   event() / loose log() verbs         → gone (instance rides info())
   LddEmission                         → stdlib logging.LogRecord
   LddSink                             → stdlib logging.Handler
   LDD_LEVEL_RANK / levels.py          → stdlib logging levels
   format_ldd_line / TEXT_CAP          → a logging.Formatter
   A2K-LDD-REPORT-TYPE lint rule       → gone (report deleted)
   _LddState per-runtime fields        → stdlib logger/filter/handlers

   RENAME (genuine survivors — clean break, no alias)
   ──────────────────────────────────────────────────────────────────
   a2kit.ldd            → a2kit.log         (THE author surface)
   packages/ldd/        → packages/log/
   LddConfig            → LogConfig
   A2KIT_LDD__*         → A2KIT_LOG__*
   ldd_state_for_call   → bind_call_scope    (dispatcher SPI)
   _LddState            → _CallScope         (per-call context, internal)
   specs ldd-*          → log-* / call-log

   INTERNAL (not author-facing, no public name)
   ──────────────────────────────────────────────────────────────────
   a2kit.calls          dedicated access-log logger (framework emits)
   call-log file handler the opt-in JSONL sink on a2kit.calls
```

Why `log` not `trace`: the record is span-shaped, so `trace_id` / `span_id`
already name the durable span spine; `a2kit.trace` would double-book
"trace" against the span concept. `log` says what the surface literally is
(genuinely stdlib logging) and matches the owner's lean. `a2kit.logging`
stays rejected (shadows the stdlib module).

## _LddState dissolves into a thin per-call `_CallScope`

`_LddState` mixed *per-call identity* with *per-runtime config* — and the
config half duplicated stdlib logging, so it evaporates:

```
   _LddState field    per-call?    fate
   ────────────────   ─────────    ─────────────────────────────────
   ctx                PER-CALL     SURVIVES — the awaited wire endpoint
   start_monotonic    PER-CALL     SURVIVES — basis for elapsed_ms
   (call_id)          PER-CALL     ADDED    — call-log correlation
   (record)           PER-CALL     ADDED    — access-record accumulation
   ────────────────────────────────────────────────────────────────
   events_enabled     per-runtime  DIES  → stdlib logger level
   reports_enabled    per-runtime  DIES  → report() deleted
   report_type        per-runtime  DIES  → @reports deleted
   tool_name          per-runtime  MOVES → injected on LogRecord by a Filter
   sinks              per-runtime  DIES  → logging.Handlers
   level_threshold    per-runtime  DIES  → stdlib logger level
```

After the refound, only the per-call identity is left, and it's a
legitimately-needed contextvar object (the async wire path needs `ctx`
without threading it through every signature; the call-log needs
`call_id`). So `_LddState` → **`_CallScope`**: `{call_id, ctx,
start_monotonic, record}` — sibling to `request_scope`, deliberately
neutral (NOT `_LogScope`: it is the shared spine for both the app log and
the access record).

## The call record is a shared spine (call-log + future gates)

The `DISPATCH_PIPELINE` is an ordered tuple of self-skipping stages
(`AuthorizeGateStage` is the shipped precedent for a stage that can
*refuse* the body). Two distinct riders sit on this boundary — **two
stages, one record**:

```
   verb        stage                  failure mode          owner
   ────────    ──────────────────     ─────────────────     ────────────
   observe     CallLogStage (this)    swallow (never break)  a2kit core
   gate        policy-ledger (P131)   refuse (that's the     a2ledger pkg
                                        point)
```

A single fused hook was rejected: it would have to be both
swallow-on-failure (observe) and refuse-on-failure (gate) at once. What
they SHARE is the `call_id`-keyed record: the call-log writes
args/result/timing/principal; a future ledger gate writes its
verdict/evidence under the *same* `call_id`. `call_id` is minted at
dispatch regardless of whether either rider is enabled, so the spine is
always available.

> **OPEN (placement, governance call — defer to implementation):** does
> core own a **thin record** (`call_id` + args/result/timing/principal +
> open `extra` bag) with enrichers defining their own fields inside
> `extra`, OR a **richer typed record contract** that a2ledger conforms to?
> Lean: **thin record + open bag** — keeps a2kit core ignorant of
> a2ledger's domain vocabulary while giving both the shared `call_id`
> spine. A CONSTITUTION substrate/product placement decision; settle it
> when the record schema is implemented.

## Author surface after the change

```python
# THE author surface — a2kit.log (the 26-site a2web surface, renamed from a2kit.ldd)
# A level method takes a message+fields OR a typed instance. No event()/log()/journal verb.
await a2kit.log.info(TierEnded(step="extract", verdict=ok, dur_ms=300))  # streams
await a2kit.log.info("cache warm", host="x.com")                         # streams
await a2kit.log.debug("html", html=h)   # file-only (DEBUG+); never streams; carries call_id

# DURABLE call record — fully automatic. The dispatch boundary captures
# args+result+timing+principal+call_id and emits it on a2kit.calls (file only).
# Author writes NOTHING for it. Turn it on with config:
#   A2KIT_LOG__CALL_LOG=on  A2KIT_LOG__CALL_LOG_LEVEL=DEBUG
```

No `report`. No `EventRegistry`. No `event()` / `log()` verb. No
`a2kit.journal`, no `record()`. One concept the author learns — `a2kit.log`
with levels — and a config toggle for durability. The access-record is the
framework's job; the author just logs.
