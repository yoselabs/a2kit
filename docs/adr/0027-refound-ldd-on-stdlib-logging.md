---
id: "0027"
status: accepted
date: 2026-05-29
last_reviewed: 2026-05-29
supersedes: []
superseded_by: null
tags: [ldd, logging, observability, architecture, surface, journal, dependency]
deciders: [Denis Tomilin]
---

# ADR 0027: Refound LDD on stdlib logging; add a durable call journal; reject structlog for core

## Status

Accepted, 2026-05-29. Implemented by change
`refound-ldd-on-stdlib-logging`. This is the first ADR to own LDD's
shape — prior LDD design lived only in change records
(`reshape-ldd-operator-wire-fanout`, archived 2026-05-27) and the
BACKLOG.

## Summary

In the context of LDD — a bespoke realtime emission channel that
independently reinvented stdlib `logging` (levels, handlers, formatter,
contextvar binding) and whose `report()` / `EventRegistry` verbs have
zero callers (census 2026-05-27) — facing the durable-journal use-case
that the BACKLOG pre-registered as the trigger to execute "Path A"
(logging tool calls + payloads for later review, driven concretely by
a2web call logging: ask, returned value, raw HTML, extracted MD,
filterable by domain), we decided to **re-found the emission surface on
Python's stdlib `logging` (one record → many handlers, each with its own
formatter and filter), delete the dead verbs, keep `event()` as thin
sugar, add a durable call-journal handler with dispatch-boundary
auto-capture and a consumer-enrichment seam, and reject structlog for
core**, and against (a) keeping the bespoke four-verb channel, (b)
adopting structlog, and (c) deferring the journal further, to achieve a
smaller owned-code surface (deletes ~800 LOC plumbing + ~147 LOC lint
rule, adds ~300–400), zero new hot-path dependencies, the preserved
ADR 0020 cold-start guarantee, and a framework-owned reviewable record
of every tool call — accepting a BREAKING removal of `report` /
`@reports` / `EventRegistry` (no external callers) and one genuinely-hard
sub-problem (the async MCP-wire boundary) that concentrates into a single
handler.

We **also retire the "LDD" name with no backward-compat redundancy**
(superseding the reshape change's cost-motivated "keep `ldd` for surface
stability" concession — cost is no longer the deciding constraint, and a
clean surface carries no aliases). The name is replaced, not aliased, and
the rename rides this change because the refound already rewrites these
files (renaming later would be a second breaking release). The surface
sorts into DELETE (dead bespoke machinery the refound replaces), RENAME
(`a2kit.ldd` → `a2kit.trace`, `LddConfig` → `TraceConfig`, `A2KIT_LDD__*`
→ `A2KIT_TRACE__*`, `ldd_state_for_call` → `bind_call_scope`, `_LddState`
→ `_CallScope`), and SPLIT — the two public faces that "LDD" conflated
become **`a2kit.trace`** (live emission) and **`a2kit.journal`** (durable
record), the live/durable axis made visible at the call site. The
per-call context (`_CallScope`) stays internal. `_LddState` dissolves:
its per-runtime fields (levels, sinks, flags) move to stdlib logging; only
the per-call identity (`call_id`, `ctx`, `start_monotonic`, journal
`record`) remains. Tier-2 gate `expected_tier_ldd.txt` is replaced by
`expected_tier_trace.txt` + `expected_tier_journal.txt` (ADR 0004 amends).
The `journal`/`ledger` naming is deliberate: journal = chronological
record (a2kit core, observe stage); ledger = posted entries (future
a2ledger, gate stage); shared `call_id` spine.

## The problem

`levels.py` states it plainly: *"Rank spacing of 10 mirrors stdlib
logging."* LDD is ~85% a re-implementation of a stdlib module — sinks
are handlers, `wire.py`/`TEXT_CAP` is a formatter, ambient `_LddState`
is a contextvar filter. It carries that bespoke weight at real cost: a
147-LOC lint rule exists mostly to police the custom surface, and
layer-cycle workarounds (`_ldd_wire` shoved below L0, `ambient →
request_scope` under `# noqa: A2K-LAYER`) exist to keep the bespoke
package importable.

Two of the four verbs are dead. `report()` not only has zero callers —
it validates payload types *even when disabled* "to keep tests
deterministic" (`emission.py:160-165`), i.e. production API shaped by a
test concern. `EventRegistry`'s progress path is unused
(`report_progress` count: 0).

Meanwhile the requirement that actually exists — persist each call for
later analysis — has no home. a2web hand-writes `fetch_result.json` /
`answer.txt` outside the framework: unowned, uncorrelated, per-consumer.

## What we decided

1. **Re-found on stdlib `logging`.** One `LogRecord` → many handlers.
   Condensing (CLI line, token-saving wire) is a per-handler
   `Formatter`; full fidelity (journal) is another. `call_id` /
   `tool_name` / `elapsed_ms` injected by a `Filter` reading the
   request-scope contextvar. Levels/sinks/wire fold into stdlib
   equivalents.
2. **Delete dead surface.** `report()`, `@reports`, `report_type`,
   `ReportTypeNotDeclared/Mismatch`, `EventRegistry`, `emit_typed`, the
   progress path, and the bulk of `lint/rules/ldd.py`.
3. **Keep `event()`** as ~20 LOC of sugar over a logger call with the
   payload in `extra=` — the entire 26-site a2web surface, unchanged.
4. **Add the call journal.** A `call_id` per dispatch; a durable handler
   writing jsonl rows + content-addressed blob sidecars (so domain
   filtering stays a columnar scan); a `DISPATCH_PIPELINE` stage that
   auto-captures args/result/timing/principal at the boundary; a
   `journal_attach` primitive for consumer-owned blobs (raw HTML,
   extracted MD) the boundary cannot see.

## Why not structlog (recorded to prevent relitigation, per ADR 0005)

structlog's value is the delta over stdlib (processor-chain ergonomics,
~50 LOC you'd write once). It deletes the *same* plumbing stdlib
deletes, then charges: a hot-path third-party dependency; a ~80ms+
import (10× a2kit's whole current import budget — violating the ADR 0020
cold-start guarantee; cf. ADR 0001 reluctantly accepting 70ms for
Typer); a learned API (vs stdlib `logging`, which every Python dev
already knows); and a custom renderer to preserve the byte-stable wire
line. It also does not solve the one hard thing — its async support runs
*sync* handlers off-thread, not native `await` of `ctx.log()`. Net
negative on the axis we care about most (owned code size) once the
custom renderer is counted, and negative on cold-start and deps.

structlog remains available to **consumers** for their own app logging
(ADR 0022: app-logging presentation is consumer-owned). a2web may add a
structlog handler in its composition root; core neither forces the dep
nor eats the import.

## The async wire boundary (resolved)

Live, mid-call log streaming is **mandatory**, not optional: the purpose
of LDD as a dev technique is seeing what a long-running MCP call is doing
*while it runs* (a 30-minute call must surface progress immediately, not
dump at the end). This already works today because `event()` / `log()`
are `async` and `await ctx.log()` **inline** in the tool body, which MCP
ships as a stream notification mid-call.

stdlib `logging.Handler.emit()` is synchronous and cannot `await` a
network send. The risk is therefore regression, not absence: routing the
MCP wire through a sync stdlib `Handler` would destroy the streaming we
already have. Decision:

- **The MCP wire emission MUST remain an inline `await ctx.log()`** in
  the async primitive — never deferred behind a sync handler, buffer, or
  end-of-call flush.
- **No queue.** A per-request `asyncio.Queue` + drainer was rejected: it
  adds latency over inline await and only matters if a slow client must
  not throttle the tool, which is not a dev-logging concern.
- **Sync stdlib `Handler`s are used only where "now" already means
  "write now"** — stderr and the journal jsonl row. The wire is the lone
  channel where "now" means "await a send," so it stays async-inline.

This *qualifies* the pure-stdlib thesis rather than abandoning it: stdlib
`logging` owns levels, the `call_id` filter, the condensed formatter, and
the sync handlers; the emission primitives stay `async` (as today) and
the wire fan-out is an awaited inline call, not a sync handler. Still
strictly less bespoke machinery than today.

## Consequences

- **Positive**: owned code shrinks; zero new deps; cold-start guarantee
  intact; first framework-owned reviewable call record; likely dissolves
  the LDD layer-cycle workarounds; one universally-known mental model
  (stdlib logging) replaces a bespoke one.
- **Negative / accepted**: BREAKING removal of `report` / `@reports` /
  `EventRegistry` (no external callers — census-confirmed); a coordinated
  lockstep release across the solo consumer repos; the async-wire
  boundary remains a real (if localized) bespoke piece under B2.
- **Follow-up (a2web, separate change)**: adopt `event()` unchanged; add
  `journal_attach` for `raw_html`/`extracted_md`; retire the hand-rolled
  `fetch_result.json` writers in favour of the journal.
