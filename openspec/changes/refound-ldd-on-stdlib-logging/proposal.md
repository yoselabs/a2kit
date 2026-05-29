## Why

The BACKLOG entry **"LDD reshape (Path A — primitive fusion)"** named its
own trigger:

> **Trigger**: a third surface wants structured emission, OR the
> durable-journal use-case lands (logging tool calls + payloads for
> later review). Until then, the four-verb surface stays.
> Census (2026-05-27): `report()` 0 callers, `log/info/warning/error/debug`
> 0 callers, `event()` a2web-only.

**The journal trigger has fired.** The concrete driver: a2web call
logging — persist each `ask` + what we returned, plus the raw HTML body
and extracted MD body, keyed per call, so the records can later be
analysed (by AI and by hand) to assess extraction quality, structure,
and per-domain performance. a2web already does a degraded version of
this by hand-writing `fetch_result.json` / `answer.txt` / `row.json`
outside the framework — unowned, uncorrelated, ad-hoc.

The prior change (`reshape-ldd-operator-wire-fanout`, archived
2026-05-27) deliberately picked Path B (keep the four verbs, promote
operator sinks) and deferred Path A. This change **executes Path A**,
now that the named trigger condition holds, and folds in the durable
journal as the forcing use-case.

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
streaming in serve mode, token-condensed for the LLM, full-fidelity for
the journal) is **one record → many handlers, each with its own
formatter + filter** — which is exactly stdlib `logging`'s architecture.

## What Changes

**BREAKING.** Re-found the emission surface on stdlib `logging`; delete
the unused verbs; add the durable journal.

- **Delete** (zero callers, census-confirmed):
  - `report()`, the `@reports(T)` decorator, `report_type` plumbing on
    `_LddState`, `ReportTypeNotDeclared` / `ReportTypeMismatch`.
  - `EventRegistry` class + the `events.register` / `emit_typed`
    progress-callback path (0 callers).
  - The `_AppLdd` report-related members.
  - The bulk of `packages/lint/rules/ldd.py` (nothing bespoke left to
    police once the surface is stdlib `logging`).
- **Keep** the one primitive authors actually use:
  - `event(TypedDataclass | "name", **fields)` — survives as ~20 LOC of
    sugar over a stdlib logger call with the payload carried in
    `extra=`. This is the entire 26-site a2web surface.
  - The loose channel (`info/debug/warning/error`) re-homed as a thin
    wrapper over a stdlib logger, kept for symmetry (cheap).
- **Re-home onto stdlib `logging`**:
  - levels → logging levels; sinks → `logging.Handler`s; wire/`TEXT_CAP`
    → a `logging.Formatter`; ambient `_LddState` → a contextvar-reading
    `logging.Filter` that injects `call_id` + `tool_name` + `elapsed_ms`.
  - `otel_sink` / `live_sink` / stderr sinks become handlers (behaviour
    preserved; live_sink stays a sync stdout handler).
- **Add the call journal** (the new capability):
  - A `call_id` minted per dispatch on the request scope (the
    correlation seam — the thing STDOUT logs lack).
  - A durable **journal handler**: full-fidelity (NO `TEXT_CAP`),
    `call_id`-correlated, writing jsonl-per-day + content-addressed
    blob sidecars (hash → file) so large bodies (raw HTML, extracted
    MD) don't bloat the scannable record. Columns: `call_id`, `ts`,
    `tool`, `domain`, `principal`, `elapsed_ms`, `*_hash`.
  - **Auto-capture at the dispatch boundary**: args + result +
    timing + principal, for every tool, without author cooperation —
    a new stage in `DISPATCH_PIPELINE` (per ADR 0025 the pipeline is a
    foldable stack; this is a new stage, not new machinery).
  - **Consumer enrichment** (ADR 0022 — consumer owns its payload):
    a2web opts in to attach `raw_html`, `extracted_md`, `strategy` to
    its own journal record under the same `call_id`. The framework
    captures the boundary; the consumer adds the domain-rich blobs.
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
- `ldd-emission-surface` — the refounded author surface: one `event()`
  primitive + loose log shorthands, built on stdlib `logging`; the
  removed-verb contract (`report`/`EventRegistry` gone).
- `ldd-call-journal` — `call_id` correlation, the durable journal
  handler (jsonl + blob sidecars), dispatch-boundary auto-capture, and
  the consumer-enrichment seam.

### Modified Capabilities
- `ldd-operator-sinks` — sinks are re-expressed as stdlib
  `logging.Handler`s; the failure-isolation contract is preserved; the
  journal is a built-in handler alongside otel/live/stderr.
- `ldd-level-threshold` — the single gate becomes a stdlib logging
  level + filter; semantics (one gate, both channels) unchanged.

## Impact

- **BREAKING** for any consumer importing `report` / `@reports` /
  `EventRegistry` from `a2kit.ldd` — census says only the framework's
  own tests do. a2web's 26 `event()` sites are source-compatible (the
  `event()` sugar is preserved).
- Affected code: `packages/ldd/emission.py` (gutted to the `event()`
  sugar + stdlib bridge), `packages/ldd/ambient.py` (becomes a filter +
  `call_id` mint), `levels.py` / `wire.py` (fold into a formatter),
  `sinks/*` (become handlers), `packages/lint/rules/ldd.py` (mostly
  deleted), new `sinks/journal.py`, new dispatch stage.
- Likely **dissolves the layer-cycle gymnastics** (`_ldd_wire` shoved
  below L0, `ambient → request_scope` under `# noqa: A2K-LAYER`): stdlib
  `logging` is dependency-free, so the emission surface stops needing
  bespoke layer contortions.
- Net code size: deletes ~800 LOC of bespoke plumbing + ~147 LOC of lint
  rule; adds ~300–400 LOC (stdlib shim + journal handler). Owned-LOC
  goes **down**.
- a2web follow-up (separate change, that repo): adopt `event()`
  unchanged; add the journal-enrichment call for `raw_html`/`extracted_md`;
  delete the hand-rolled `fetch_result.json` writers in favour of the
  journal.
- Coordinated breaking release across a2web / a2atlassian / a2db (solo
  repos, lockstep per `feedback_no_prs`).

## Non-goals

- **Not** adopting structlog in core (rejected; see ADR + design).
- **Not** renaming the public `a2kit.ldd` import path or the `ldd`
  package — surface stability; the prose rebrand ("emission channel")
  from the prior change stands.
- **Not** building a query UI for the journal — jsonl + DuckDB-over-it
  is the analysis path (matches the existing health-pipeline pattern);
  ad-hoc for now.
- **Not** changing the live-streaming property of the MCP wire. Mid-call
  log streaming is mandatory (the point of LDD as a dev technique) and
  already works via the async `event()` → inline `await ctx.log()` path.
  This change MUST preserve it: the wire stays async-inline, never routed
  through a sync stdlib `Handler`. (Resolved 2026-05-29 — see `design.md`
  and ADR 0027.)
