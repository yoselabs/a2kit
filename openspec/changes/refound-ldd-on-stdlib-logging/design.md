# Design — refound LDD on stdlib logging + durable call journal

## The two-axis model LDD conflated

LDD mixes two orthogonal axes but only ever moved along one (shape).
The whole design follows from separating them:

```
                    DESTINATION / LIFETIME  (axis 1)
                    realtime wire ──────────────────► durable store
                    (caller, now, ephemeral)          (analyst, later, queryable)
   ┌──────────────┐
   │  loose text  │   log()/info()…                   ✗ nothing
 S │  named loose │   event()                          ✗ nothing
 H │  structured  │
 A │  typed       │   report()  ← over-built,          ✗ nothing  ◄── THE JOURNAL
 P │  contract    │              zero callers              lives in this empty cell
 E └──────────────┘
   (axis 2 = shape)
```

Everything LDD has today is the **left column** (realtime). The journal
is the **right column** (durable). `report()` — the verb with zero
callers — is the typed shape that the journal *wants to persist*; it was
a half-built journal primitive that never got a durable destination. So
building the journal and finishing the LDD reshape are the same move.

## Decisive reframe (2026-05-29 brainstorm): split LOGGING from RECORDING

A four-agent brainstorm (red-team / prior-art / consumer / alternatives)
converged independently on one correction: **this is two systems, not one
"logging" system with a journal handler bolted on.** The earlier "one
record → many handlers, the journal is just another handler" framing
(below) is RETIRED — it was the seed of every wart we hit. The two
machines:

```
   a2kit.log  — TRACE (commentary, live, ephemeral)
   ─────────────────────────────────────────────────
   genuinely stdlib logging. author narrates. levels mean severity.
   → wire handler (async-inline ctx.log, streams to agent, INFO+)
   → stderr handler (operator, DEBUG+)
   foreign libs (httpx) excluded by NOT being under a2kit.*
   THIS is where stdlib logging + per-handler levels earn their keep.

   a2kit  journal — RECORD (call I/O, durable, queryable)
   ─────────────────────────────────────────────────
   NOT logging. a transport-neutral DISPATCH-PIPELINE STAGE writes a
   structured CallRecord. No Logger, no level, no formatter. Auto-
   captured at the boundary (before the formatter — raw return value).
   Consumer enriches the record (not by logging). Queried by DuckDB.
```

Why the split is *more* faithful to the project's own principles, not
less:

- **"Same side-effects regardless of interface"** (the stated invariant):
  the journal being a NEUTRAL DISPATCH STAGE makes the record identical
  *by construction*. A journal-as-handler would be config-wired per
  transport and could drift — the exact thing the invariant forbids. The
  split strengthens it.
- **The warts dissolve.** Each was a symptom of over-unification:
  - kind-by-logger-name (`a2kit.call` vs `a2kit`) — only needed to tell
    call-io from commentary *inside one logging pipe*. Separate systems →
    the hack is unnecessary (call-io is a record, not a log line).
  - the "don't emit data where already visible" routing rule — only
    needed to de-dup two kinds sharing one pipe. Separate pipes → no rule.
  - "byte-identical across handlers" fragility — the record is owned by
    one neutral stage, not reconstructed by N handlers.
  - the namespace-squat question (where does a2web log to be journaled?)
    — moot: the journal captures at the dispatch boundary, it does not
    subscribe to a consumer's logger.

The ADR headline becomes **"split logging from recording"** — stdlib
`logging` for ephemeral commentary, a dispatch-stage record store for
durable call-I/O. (The "## The unifying mechanism" section below is kept
for history but superseded by this one.)

### CallRecord is span-shaped (OTel data model, NOT the OTel SDK)

Two agents converged: shape the record like an OTel span *now*, without
importing the SDK (the SDK's cold-start cost is rejected on the same
ADR-0020 grounds as structlog). The record carries `trace_id` /
`span_id` / `parent_span_id` alongside `call_id`. Costs ~nothing today
and buys three things the flat-`call_id` design lacks:

- **call NESTING** — a tool that dispatches another tool. The current
  design never addressed it; flat `call_id` can't express parent/child.
  `parent_span_id` makes it a non-breaking field, not a future migration.
- the existing `otel_sink` becomes a *real* exporter for opt-in consumers.
- "migrate to OTel" becomes a config flag, not a rewrite.

### Verified: per-call isolation holds (eval use-case safe)

The red-team flagged a possible FATAL concurrency bug (parallel calls
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

### "byte-identical" relaxed; fetch_result.json claim scoped down

- The invariant is **"identical CAPTURED FIELDS across interfaces,"** not
  byte-identical wire output. The capture stage snapshots the raw return
  *value* (pre-formatter) + args + principal + timing. Error cases
  (no return value → captured as typed error), streaming/generator
  returns (captured as the materialized value or a marker), and
  transport-injected ids are defined explicitly in the spec rather than
  assumed away.
- The journal subsumes **call-I/O capture**, NOT the eval-scoring layer.
  The consumer agent found a2web's `fetch_result.json` carries
  harness-computed metadata (`cost_usd`, `cache_hit`, `extraction_model`)
  that is NOT a tool arg/return — it is synthesized by the eval harness.
  That stays consumer enrichment (logged into the record by `call_id`),
  not auto-capture. Honest scope: journal replaces the I/O dump, not the
  scoring metadata.

### event(instance) STAYS (reverses an earlier lean)

The consumer agent found a2web has 28 sites passing typed dataclasses
(`TierEnded(step=..., verdict=...)`). Forcing `info("msg", **kwargs)`
loses construction-time type-checking, IDE autocomplete, and adds
boilerplate at every site — a usability cliff. So `a2kit.log.info`
accepts `info(instance | msg, **fields)`: the instance IS the structured
payload. No separate `event()` verb (that name dies), but instance-
logging as the shape survives under `info`/`debug`/etc.

## The unifying mechanism: one record → many handlers

This is stdlib `logging`'s architecture, and it collapses every stated
requirement into one diagram:

```
   author emits ONCE          ┌─────────────────────────────────────┐
   event(TierEnded(…))   ───► │  LogRecord                          │
   info("…", k=v)             │  level + msg + structured payload    │
                              │  + call_id + tool_name + elapsed_ms  │ ← contextvar Filter
                              └──────────────┬──────────────────────┘   injects these
              ┌───────────────────────┬──────┴───────────────────────┐
              ▼                       ▼                               ▼
   ┌──────────────────┐   ┌────────────────────┐    ┌──────────────────────────┐
   │ CLI / stderr      │   │ serve / MCP wire    │    │ JOURNAL (new)             │
   │ handler           │   │ handler             │    │ handler                   │
   │ CONDENSED fmt     │   │ CONDENSED fmt       │    │ FULL-FIDELITY fmt          │
   │ (TEXT_CAP line)   │   │ (token-saving)      │    │ (NO cap; raw HTML/MD ok)  │
   │ SYNC              │   │ ASYNC ← the catch    │    │ jsonl + blob sidecar,     │
   │                   │   │                     │    │ call_id-correlated         │
   └──────────────────┘   └────────────────────┘    └──────────────────────────┘
        STDOUT                 streaming                  review-later
```

Condensing is a property of the **LLM-facing** handlers (CLI, wire); the
journal deliberately does not condense. "Same record, different
formatter" is the entire answer to "STDOUT vs streaming vs token-saving
vs full-fidelity."

## Mapping: what LDD has → where it goes

| LDD today | stdlib logging home | fate |
|---|---|---|
| `LDD_LEVEL_RANK` (`levels.py`) | logging levels | fold |
| sinks + `_dispatch_sinks` fan-out | `logging.Handler`s | re-express |
| `wire.py` / `TEXT_CAP` / `format_ldd_line` | a `logging.Formatter` | fold |
| ambient `_LddState` / `ldd_state_for_call` | a `logging.Filter` reading a contextvar | re-express + mint `call_id` |
| `event(Typed)` | logger call with `extra={payload}` | **keep as ~20 LOC sugar** |
| `info/debug/warning/error` | thin logger wrappers | keep (cheap) |
| `otel_sink` / `live_sink` / stderr sinks | handlers | re-express, behaviour preserved |
| `report()` / `@reports` / `report_type` | — | **DELETE** (0 callers) |
| `EventRegistry` / `emit_typed` / progress | — | **DELETE** (0 callers) |
| most of `lint/rules/ldd.py` (147 LOC) | — | **DELETE** (nothing bespoke to police) |

## The journal handler

```
   journal/2026-05-29.jsonl              bodies/  (content-addressed)
   ──────────────────────────────        ──────────────────────────
   {call_id, ts, tool:"ask",             ab3f…html   ← raw HTML
    domain:"x.com", ask:"…",             9c1e…md     ← extracted MD
    principal:"…", elapsed_ms,
    result_hash:"9c1e",
    html_hash:"ab3f"}        ← scan-light, query-fast (DuckDB over jsonl)
```

- **Why content-address the bodies**: inlining 100KB+ HTML into every
  jsonl row makes "filter by domain" scan megabytes per record. Hash →
  sidecar keeps the row tiny; the heavy body is fetched only when a
  record is opened. `domain` / `tool` / `principal` / `ts` stay columnar.
- **Auto-capture at the boundary** (new `DISPATCH_PIPELINE` stage, per
  ADR 0025): the framework records `args` + `result` + `timing` +
  `principal` for every tool, with no author cooperation. A
  framework-level interceptor is the *only* layer that can do this
  uniformly — and it is exactly the opposite of LDD's "author narrates"
  grain, which is why it belongs in a stage, not in a `log` call.
- **Consumer enrichment** (ADR 0022 — consumer owns its payload): the
  boundary interceptor cannot see `raw_html` / `extracted_md` —
  intermediate values that never cross the dispatch boundary. a2web opts
  in to `journal.record(...)` them onto its own record under the same
  `call_id`. Clean
  split: framework gets correlation + persistence for free; consumer
  adds the domain-rich blobs.

## The async wire boundary — RESOLVED: live streaming is mandatory

**Decision (2026-05-29): the wire path streams live, inline.** Live,
mid-call log appearance is the *whole point* of LDD as a dev technique:
when an MCP call takes 30 minutes, you must see what it is doing *as it
runs* — not wait for a terminal dump. This is a hard requirement, not a
preference.

The load-bearing fact: **this already works today**, and it works
*because* `event()` / `log()` are `async` and `await ctx.log()` **inline**
in the tool body. MCP ships that as a log notification over the open
stream immediately, mid-call. So the requirement is not "add streaming"
— it is **"do not regress streaming."**

That reframes the stdlib-logging caveat. stdlib `logging.Handler.emit()`
is **synchronous** and cannot `await` a network send. The danger is
therefore the *opposite* of a missing feature: naively routing the MCP
wire through a sync stdlib `Handler` would **destroy** the streaming we
already have. So the binding rule:

```
   The MCP wire emission MUST remain an inline `await ctx.log()` inside
   the async emission primitive. It MUST NOT be deferred behind a sync
   stdlib Handler, a buffer, or an end-of-call flush.

   Sync stdlib Handlers are used ONLY where "now" already means
   "write now": stderr and the journal jsonl row. Those are real-time
   as-is. The wire is the one channel where "now" means "await a send,"
   so the wire stays async-inline.
```

Mechanism: **inline async await, no queue.** A per-request
`asyncio.Queue` + drainer was considered and rejected — it *adds*
latency versus inline await and only earns its keep if a slow client
must be prevented from throttling the tool, which is not a concern for
dev logging. Inline await is both the simplest and the most real-time
option.

Honest consequence for the "pure stdlib logging" thesis: it is
**qualified, not abandoned.** The emission primitives stay `async`
(they already are); the *wire* fan-out is an async inline await, not a
sync stdlib `Handler`. stdlib `logging` still owns levels, the filter
(`call_id` injection), the formatter (condensed line), and the sync
handlers (stderr, journal). We keep stdlib's mental model and delete the
bespoke verbs — we just do not pretend the awaited wire is a sync
handler. This is strictly less bespoke machinery than today (which hand
-rolls levels, formatter, and contextvar plumbing *as well as* the async
fan-out).

## Why not structlog (recorded so it is not relitigated)

| axis | stdlib shim | structlog | bespoke (today) |
|---|---|---|---|
| owned LOC after change | ~300–400 | ~250–350 | ~1,300 |
| new dependency | none | **+structlog on hot path** | none |
| import cost | free (stdlib) | **~80ms+ (10× a2kit's whole import)** | free |
| new concepts for authors | none (universal) | a learned API | a learned API |
| wire byte-stability | kept for free | costs a custom renderer | kept |
| deletes the 147-LOC lint rule | yes | partly | no |

structlog's value is the *delta over stdlib* (processor-chain
ergonomics ≈ 50 LOC you'd write once). It deletes the *same* plumbing
stdlib deletes, then charges a hot-path dependency, a ~80ms import
(violates the ADR 0020 cold-start guarantee; cf. ADR 0001 reluctantly
accepting 70ms for Typer), and a custom renderer to preserve the wire
format — to land where stdlib already puts us. It also does **not** solve
the one hard thing: its async support runs *sync* handlers off-thread,
not native `await` of `ctx.log()` — B2 still needs our own
queue+drainer. Net-negative on code size, cold-start, and deps.

Consumer-side, structlog is fine: ADR 0022 makes app-logging
presentation a consumer-owned concern. a2web may add a structlog handler
in its own composition root if it wants a pretty dev console; a2kit core
neither forces the dep nor eats the import.

## Naming: "LDD" retired, surface sorted into DELETE / RENAME / SPLIT

"LDD" (Logging / Data / Diagnostics) named a bespoke channel this change
deletes. With no backward-compat redundancy, the name goes with it — no
`ldd = trace` alias, no shim, no kept-for-stability path. The whole
surface sorts three ways:

```
   DELETE (stdlib logging replaces — renaming dead code = redundancy)
   ──────────────────────────────────────────────────────────────────
   report / @reports / EventRegistry   → gone (zero callers)
   LddEmission                         → stdlib logging.LogRecord
   LddSink                             → stdlib logging.Handler
   LDD_LEVEL_RANK / levels.py          → stdlib logging levels
   format_ldd_line / TEXT_CAP          → a logging.Formatter
   A2K-LDD-REPORT-TYPE lint rule       → gone (report deleted)
   _LddState per-runtime fields        → stdlib logger/filter/handlers

   RENAME (genuine survivors — clean break, no alias)
   ──────────────────────────────────────────────────────────────────
   a2kit.ldd            → a2kit.log         (emission namespace)
   packages/ldd/        → packages/log/
   LddConfig            → LogConfig
   A2KIT_LDD__*         → A2KIT_LOG__*
   ldd_state_for_call   → bind_call_scope    (dispatcher SPI)
   _LddState            → _CallScope         (per-call context)
   specs ldd-*          → log-* / call-journal

   SPLIT (un-conflate the two public faces fused under "LDD")
   ──────────────────────────────────────────────────────────────────
   a2kit.log       — LIVE emission   (info/debug/warning/error; msg OR instance)
   a2kit.journal   — DURABLE record  (record(Payload) + CallRecord)
   _CallScope      — per-call context (internal)
```

Why split `log` from `journal`: the session established the live-vs-
durable axis as the core distinction (ephemeral wire stream vs persisted
analyzable record). Two namespaces make that axis visible at the call
site — `a2kit.log.info(...)` is fire-and-forget; `a2kit.journal.
record(...)` persists. Folding them back into one namespace would re-
conflate exactly what we separated.

Why `log` not `trace` for the live surface: the record is now span-shaped
(`trace_id` / `span_id`), so "trace" already names the *durable* span
spine. Naming the *live* surface `a2kit.trace` would double-book the one
word across both halves of the very axis we just split. `log` says what
the surface literally is (genuinely stdlib logging), frees "trace" to mean
only the span concept, and matches the project owner's stated lean. Three
words, three concepts: **log** (live narration) / **trace_id** (span spine)
/ **journal** (the store).

Why `journal` not `ledger`: accounting metaphor. A **journal** is the
chronological as-it-happened record (a2kit core, the observe stage); a
**ledger** is where posted/categorized entries land (the future
a2ledger policy gate, the gate stage). Same `call_id` spine; the names
reinforce "two stages, one record."

"trace" usage after this choice: the only surviving "trace" tokens are
the span fields (`trace_id` / `span_id` / `parent_span_id` on `CallRecord`)
and the optional `trace` *level* alias in `levels.py` — both deliberate
and non-overlapping with the `a2kit.log` namespace. The earlier
`a2kit.trace`-namespace collision caveat is moot now the surface is
`a2kit.log`.

## _LddState dissolves into a thin per-call `_CallScope`

Field-by-field, `_LddState` splits along the per-call / per-runtime line —
and the per-runtime half is exactly what stdlib logging provides natively,
so it evaporates:

```
   _LddState field    per-call?    fate
   ────────────────   ─────────    ─────────────────────────────────
   ctx                PER-CALL     SURVIVES — the awaited wire endpoint
   start_monotonic    PER-CALL     SURVIVES — basis for elapsed_ms
   (call_id)          PER-CALL     ADDED    — journal correlation
   (record)           PER-CALL     ADDED    — journal accumulation (rides here,
                                              per the shared-spine decision)
   ────────────────────────────────────────────────────────────────
   events_enabled     per-runtime  DIES  → stdlib logger level
   reports_enabled    per-runtime  DIES  → report() deleted
   report_type        per-runtime  DIES  → @reports deleted
   tool_name          per-runtime  MOVES → injected on LogRecord by a Filter
   sinks              per-runtime  DIES  → logging.Handlers
   level_threshold    per-runtime  DIES  → stdlib logger level
```

The root problem with `_LddState` was conflation: it mixed *per-call
identity* (who am I, where's my wire, when did I start) with *per-runtime
config* (levels, sinks, flags) — and the config half duplicated stdlib
logging. After the refound, only the per-call identity is left, and it's
a legitimately-needed contextvar object (the async wire path needs `ctx`
without threading it through every signature; the journal needs `call_id`).

So `_LddState` → **`_CallScope`**: `{call_id, ctx, start_monotonic,
record}`. The per-runtime fields move to stdlib logging (a `Filter`
injects `call_id` / `tool_name` / `elapsed_ms` onto each `LogRecord`; the
logger's level owns the threshold; handlers own fan-out). This is *less*
bespoke code, and the new name describes what it is — the per-call scope,
sibling to `request_scope`.

## The call record is a shared spine (journal + future gates)

The `DISPATCH_PIPELINE` is an ordered tuple of self-skipping stages
(`AuthorizeGateStage` is the shipped precedent for a stage that can
*refuse* the body). Two distinct future riders sit on this boundary, and
they are **two stages, one record**:

```
   verb        stage                  failure mode          owner
   ────────    ──────────────────     ─────────────────     ────────────
   observe     JournalStage (this)    swallow (never break)  a2kit core
   gate        policy-ledger (P131)   refuse (that's the     a2ledger pkg
                                        point)
```

A single fused "call observer" hook was rejected: it would have to be
both swallow-on-failure (journal) and refuse-on-failure (ledger) at once
— contradictory, and it couples a safety-critical "never break the tool"
path to a deliberately-blocking one. Different verbs, different failure
modes, different owners → different stages.

What they SHARE is the `call_id`-keyed record: the journal writes
args/result/timing/principal; a future ledger gate writes its
verdict/evidence under the *same* `call_id` via the same enrichment
primitive (exactly like a2web recording `raw_html`). a2ledger's evidence
model (ADR 0004: `codebase_marker | llm_evidence | hybrid`) becomes
`extra`-bag fields on this record, not a core concept.

> **OPEN (placement, governance call — defer to implementation):** does
> core own a **thin record** (`call_id` + args/result/timing/principal +
> open `extra` bag) with enrichers defining their own typed fields inside
> `extra`, OR a **richer typed record contract** that a2ledger conforms
> to? Lean: **thin record + open bag** — keeps a2kit core ignorant of
> a2ledger's domain vocabulary (evidence/stamps/receipts are P131's, not
> a2kit's) while still giving both features the shared `call_id` spine.
> This is a CONSTITUTION substrate/product placement decision; settle it
> when the journal record schema is implemented, not before.

## Author surface after the change

```python
# LIVE emission — a2kit.log (the 26-site a2web surface, renamed from a2kit.ldd)
# A level method takes a message+fields OR a typed instance (no event() verb).
await a2kit.log.info(TierEnded(step="extract", verdict=ok, dur_ms=300))
await a2kit.log.info("cache warm", host="x.com")

# DURABLE record — a2kit.journal. Framework auto-captures
# args+result+timing+principal+call_id at the dispatch boundary;
# the consumer enriches its own record (a2web) with a TYPED payload —
# same grammar as log.info(instance), different destination + lifetime:
a2kit.journal.record(FetchArtifacts(raw_html=html, extracted_md=md, strategy="trafilatura"))

# out-of-dispatch enrichment (eval harness; no active call scope) takes call_id:
a2kit.journal.record(EvalScore(cost_usd=x, cache_hit=h), call_id=cid)
```

No `report`. No `EventRegistry`. No `event()` verb. No `a2kit.ldd`. The
live/durable split is visible at the call site: `a2kit.log.*` is
fire-and-forget commentary (async, severity-ranked, streamed); `a2kit.
journal.record(...)` persists a typed payload (sync, full-fidelity,
content-addressed). One typed-payload grammar, two destinations.
`record()` is sync — it mutates the active `_CallScope.record`, signalling
it is *not* logging. Live destinations are config-wired per mode at
app-build; the journal is a dispatch stage you switch on.
