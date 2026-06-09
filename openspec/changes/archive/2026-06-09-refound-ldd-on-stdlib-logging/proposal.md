## Why

The BACKLOG entry **"LDD reshape (Path A — primitive fusion)"** named its
own trigger:

> **Trigger**: a third surface wants structured emission, OR the
> durable-journal use-case lands (logging tool calls + payloads for
> later review). Until then, the four-verb surface stays.
> Census (2026-05-27): `report()` 0 callers, `log/info/warning/error/debug`
> 0 callers, `event()` a2web-only.

**The durable-logging trigger has fired.** The concrete driver: a2web call
logging — persist each `ask` + what we returned, plus the raw HTML body
and extracted MD body, keyed per call, so the records can later be
analysed (by AI and by hand) to assess extraction quality, structure,
and per-domain performance. a2web already does a degraded version of
this by hand-writing `fetch_result.json` / `answer.txt` / `row.json`
outside the framework — unowned, uncorrelated, ad-hoc.

The prior change (`reshape-ldd-operator-wire-fanout`, archived
2026-05-27) deliberately picked Path B (keep the four verbs, promote
operator sinks) and deferred Path A. This change **executes Path A**,
now that the named trigger condition holds, and folds in durable call
logging as the forcing use-case.

Two findings from re-reading the code sharpen the scope:

1. **`report()` / `@reports` / `EventRegistry` are dead surface.** Census
   confirms zero callers across a2web. Worse, `report()` validates its
   payload type *even when reports are disabled* "to keep tests
   deterministic" (`emission.py:160-165`) — production API carrying a
   test concern. The 147-LOC lint rule `packages/lint/rules/ldd.py`
   exists largely to police this bespoke surface.

2. **LDD independently reinvented stdlib `logging`.** `levels.py` says it
   outright: *"Rank spacing of 10 mirrors stdlib logging."* Sinks =
   handlers, wire/`TEXT_CAP` = a formatter, ambient `_LddState` =
   a contextvar filter. LDD is ~85% a re-implementation of a module
   already in the stdlib, at zero import cost.

The unifying model that satisfies every requirement (STDOUT in CLI,
streaming in serve mode, token-condensed for the LLM, full-fidelity and
queryable for durable review) is **one record → many handlers, each with
its own formatter, filter and level** — which is exactly stdlib
`logging`'s architecture. The durable call record is **not a new concept**:
it is an *access log* — one structured record per tool call, auto-emitted
on a dedicated logger, written to its own file, never streamed — the same
pattern every web server uses for `access.log`.

## What Changes

**BREAKING.** Re-found the emission surface on stdlib `logging`; delete
the unused verbs; add a durable, queryable call access-log. **One author
concept survives: `a2kit.log`.** There is no second public namespace — no
`journal`, no `record()` verb.

- **Delete** (zero callers, census-confirmed):
  - `report()`, the `@reports(T)` decorator, `report_type` plumbing on
    `_LddState`, `ReportTypeNotDeclared` / `ReportTypeMismatch`.
  - `EventRegistry` class + the `events.register` / `emit_typed`
    progress-callback path (0 callers).
  - The `event()` and loose `log()` *verbs* — the typed-payload ergonomic
    survives on the level methods (`info(instance)`), so no capability is
    lost; only the extra verb names go.
  - The `_AppLdd` report-related members.
  - The bulk of `packages/lint/rules/ldd.py` (nothing bespoke left to
    police once the surface is stdlib `logging`).
- **One author surface — `a2kit.log`** with the stdlib level methods
  (`debug` / `info` / `warning` / `error`), each accepting a message +
  fields OR (optionally) a typed instance:
  - `a2kit.log.info("fetching", url=u)` — commentary; streams.
  - `a2kit.log.debug("html", html=h)` — bulky diagnostic detail; file-only
    by level (the wire/terminal are `INFO+`).
  - `a2kit.log.info(TierEnded(...))` — the typed instance still rides the
    level method (a2web's 26 sites migrate `event(x)` → `info(x)`).
- **Re-home onto stdlib `logging`**:
  - levels → logging levels; sinks → `logging.Handler`s; wire/`TEXT_CAP`
    → a `logging.Formatter`; ambient `_LddState` → a contextvar-reading
    `logging.Filter` that injects `call_id` + `tool_name` + `elapsed_ms`.
  - `otel_sink` / `live_sink` / stderr sinks become handlers (behaviour
    preserved; `live_sink` stays a sync stdout handler).
- **Add the call access-log** (the new capability):
  - A `call_id` minted per dispatch on the request scope (the correlation
    seam — the thing raw STDOUT logs lack).
  - A **dispatch-boundary stage** auto-emits ONE structured record per
    tool call — `call_id`, `tool`, `domain`, args, result, timing,
    `principal` — span-shaped (`trace_id`/`span_id`/`parent_span_id`) for
    nesting. Author writes nothing.
  - That record is emitted on a **dedicated internal logger `a2kit.calls`
    with `propagate=False`** — only the call-log file handler is attached.
    The MCP wire and stdout handlers are NOT attached to it, so call
    records **structurally cannot stream to the agent or print to stdout**
    (the redundancy guard — the agent already has the return value).
  - A **call-log file handler**: opt-in, full-fidelity, JSONL-per-day +
    content-addressed blob sidecars (hash → `bodies/<hash>`) so large
    bodies don't bloat the scannable rows. DuckDB queries the jsonl
    directly; columns `call_id`, `ts`, `tool`, `domain`, `principal`,
    `elapsed_ms`, `*_hash`.
  - **Enrichment is just logging.** Domain blobs the boundary can't see
    (raw HTML, extracted MD) are logged at `debug` with the same
    `call_id` auto-injected (`a2kit.log.debug("html", html=h)`); the file
    captures them, correlated to the call by `call_id`. No enrichment
    verb, no merged-record API — correlation by `call_id`, the access-log
    ⨝ app-log pattern.
- **Reject structlog for core** — recorded as a first-class decision so
  it is not relitigated (ADR 0005 drift prevention). Rationale: ~80ms+
  import on the hottest path (10× a2kit's whole current import budget;
  violates the ADR 0020 cold-start guarantee), a new hot-path
  dependency, and a learned API — all to re-acquire capabilities stdlib
  `logging` already provides. structlog remains available to *consumers*
  for their own app logging (ADR 0022: app-logging framework is a
  consumer-owned concern).

## Capabilities

### New Capabilities
- `log-emission-surface` — the refounded author surface: stdlib level
  methods (`debug`/`info`/`warning`/`error`), each accepting a message +
  fields OR a typed instance; the removed-verb contract
  (`report`/`EventRegistry`/`event()`/loose `log()` gone).
- `call-log` — `call_id` correlation, the dispatch-boundary auto-capture
  stage, the dedicated non-streaming `a2kit.calls` access-logger, and the
  opt-in JSONL call-log file handler (content-addressed bodies,
  DuckDB-queryable). No public enrichment verb; enrichment is `debug`
  logging correlated by `call_id`.

### Modified Capabilities
- `log-handlers` — operator sinks re-expressed as stdlib
  `logging.Handler`s with per-handler levels + formatters; failure
  isolation preserved; the call-log file handler joins the set (attached
  only to `a2kit.calls`).
- `ldd-level-threshold` — RETIRED as a bespoke capability: the gate folds
  into stdlib per-handler logging levels — no longer a capability a2kit
  owns.

## Impact

- **BREAKING** for any consumer importing `report` / `@reports` /
  `EventRegistry` / `event` from `a2kit.ldd` — census says only the
  framework's own tests do. a2web's 26 `event(instance)` sites migrate
  to `a2kit.log.info(instance)` (mechanical one-line rewrite each).
- Affected code: `packages/ldd/emission.py` (gutted to the level-method
  wrappers + stdlib bridge), `packages/ldd/ambient.py` (becomes a filter +
  `call_id` mint), `levels.py` / `wire.py` (fold into a formatter),
  `sinks/*` (become handlers), `packages/lint/rules/ldd.py` (mostly
  deleted), new call-log file handler, new dispatch stage.
- Likely **dissolves the layer-cycle gymnastics** (`_ldd_wire` shoved
  below L0, `ambient → request_scope` under `# noqa: A2K-LAYER`): stdlib
  `logging` is dependency-free, so the emission surface stops needing
  bespoke layer contortions.
- Net code size: deletes ~800 LOC of bespoke plumbing + ~147 LOC of lint
  rule; adds ~300–400 LOC (stdlib shim + call-log handler + boundary
  stage). Owned-LOC goes **down**.
- a2web follow-up (separate change, that repo): migrate `event(x)` →
  `a2kit.log.info(x)`; log `raw_html`/`extracted_md` at `debug`; turn on
  the call-log; delete the hand-rolled `fetch_result.json` writers.
- Coordinated breaking release across a2web / a2atlassian / a2db (solo
  repos, lockstep per `feedback_no_prs`).

## Full rename — "LDD" is retired (no backward-compat redundancy)

The prior reshape change kept the `ldd` name "for surface stability" — a
*cost-motivated* deferral. Cost is no longer a constraint, and a clean
codebase carries no redundant aliases, so the deferral is reversed and
the rename rides THIS change (the refound already rewrites every one of
these files; renaming later would be a second breaking release —
exactly the churn we are avoiding). **No `ldd = log` aliases, no
deprecation shims, no kept-for-stability paths.** "LDD" (Logging / Data /
Diagnostics) named a bespoke channel that this change deletes; the name
goes with it.

The surface sorts into two buckets — and the durable record is *not* a
third namespace, it collapses into logging as an access-log case:

- **DELETE** (the refound replaces these with stdlib logging — renaming
  dead machinery would itself be redundancy): `report` / `@reports` /
  `EventRegistry`, `event()` / loose `log()` verbs, `LddEmission`
  (→ stdlib `LogRecord`), `LddSink` (→ stdlib `logging.Handler`),
  `LDD_LEVEL_RANK` / `levels.py` (→ stdlib levels), `format_ldd_line` /
  `TEXT_CAP` (→ a `Formatter`), the `A2K-LDD-REPORT-TYPE` lint rule, and
  `_LddState`'s per-runtime fields (→ stdlib logger / filter / handlers).
- **RENAME** (genuine survivors, clean break): `a2kit.ldd` →
  **`a2kit.log`** (the sole author surface); `packages/ldd/` →
  `packages/log/`; `LddConfig` → `LogConfig`; `A2KIT_LDD__*` →
  `A2KIT_LOG__*`; `ldd_state_for_call` → `bind_call_scope` (dispatcher
  SPI); `_LddState` → `_CallScope`; capability specs `ldd-*` → `log-*` /
  `call-log`. Wire keys move `a2kit_*` (kind/name/payload/elapsed_ms) —
  re-baselined, not aliased.

There is **no `a2kit.journal` public concept** and **no `record()` verb**.
An earlier draft of this change split emission and recording into two
public namespaces (`a2kit.log` + `a2kit.journal`); a 2026-05-30 design
turn collapsed that — the durable record is an **access log** (a dedicated
internal `a2kit.calls` logger + an opt-in file handler), which is a
*logging* case, not a second concept the author must learn. The only
public name is `a2kit.log`.

Why `log` not `trace` for the surface: the call record is span-shaped, so
`trace_id` / `span_id` already name the durable span spine; `a2kit.trace`
would double-book "trace". `log` names what the surface literally is
(stdlib logging); `a2kit.logging` stays rejected (shadows the stdlib
module). The only surviving "trace" tokens are the span fields and the
optional `trace` level alias — both deliberate.

Tier-2 snapshot gate: `expected_tier_ldd.txt` is **replaced** by
`expected_tier_log.txt` (the sole public surface; there is no separate
journal surface to snapshot). ADR 0004's tier-gate requires the snapshot
regen + this change as the recorded ADR. a2web's `a2kit.ldd.event(...)`
sites migrate to `a2kit.log.info(...)` in lockstep.

## Non-goals

- **Not** adopting structlog in core (rejected; see ADR + design).
- **Not** building a query UI for the call-log — jsonl + DuckDB-over-it
  is the analysis path (matches the existing health-pipeline pattern);
  ad-hoc for now.
- **Not** a second public namespace for durable records — the access-log
  is internal plumbing + a config toggle, surfaced only through
  `a2kit.log` + levels.
- **Not** changing the live-streaming property of the MCP wire. Mid-call
  log streaming is mandatory (the point of LDD as a dev technique) and
  already works via the async level-method → inline `await ctx.log()`
  path. This change MUST preserve it: the wire stays async-inline, never
  routed through a sync stdlib `Handler`. (Resolved 2026-05-29 — see
  `design.md` and ADR 0027.)
