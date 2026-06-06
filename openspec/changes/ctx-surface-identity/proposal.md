## Why

**Friction #5 (a2kay): tools and the call-journal cannot tell which
surface invoked them.** A tool dispatched over MCP, posted to `/api`, or
run from the CLI runs through the *same* body with the *same* ambient
context — there is no transport/surface kind on the ctx or the per-call
scope. So a tool that wants to behave differently for an operator at a
terminal versus an agent over the wire, and an audit record that wants to
say "this call came in over MCP from client X," both have nothing to read.

ADR 0028 (decision 5 / friction-resolution table) names the fix in one
line: *"each Surface stamps its own name as it dispatches."* The hole is
real precisely because the CLI was never a `Surface` — no component owned
"stamp my identity on the call." The per-call spine to stamp it on now
exists: ADR 0027 introduced `_CallScope` (the neutral per-call identity
published on `request_scope`, carrying `ctx` / `call_id` / `tool_name` /
span fields), bound by the transport-neutral `CallScopeStage` dispatch
stage. This change extends that scope with the dispatching surface's
identity.

This is **Wave 3, additive** (`docs/SURFACE_ARCHITECTURE.md` §7). It does
not need the Wave 1/2 surface unification to land: the dispatch boundary
already knows which surface drove the call (the MCP wrapper, the HTTP
route, and the CLI runtime each invoke the same dispatch chain from a
known transport), so the surface name and an optional client/transport id
can be resolved at the bind path and threaded into the call scope today.

## What Changes

Each Surface stamps its identity onto the per-call `_CallScope` as it
dispatches:

- **`surface`** — a short stable string identifying the invoking surface
  (`"mcp"` | `"api"` | `"cli"`), sourced from the dispatching surface's
  own `name` (the `Surface.name` ClassVar; the CLI runtime supplies
  `"cli"`).
- **`surface_client_id`** — an OPTIONAL transport/client correlation id
  (e.g. FastMCP's `ctx.client_id`, an HTTP request id), `None` when the
  surface has no notion of one.

Mechanically:

- Extend `_CallScope` (ADR 0027, owned by `refound-ldd-on-stdlib-logging`)
  with two new optional fields: `surface: str | None = None` and
  `surface_client_id: str | None = None`. Both default `None`, so the
  field set is backward-compatible.
- Extend `bind_call_scope(...)` with matching optional keyword args
  (`surface=`, `surface_client_id=`), defaulting `None`.
- The transport-neutral `CallScopeStage` resolves the surface identity
  from the dispatch path and passes it into `bind_call_scope`. The
  resolution is "the surface that is dispatching knows its own identity":
  the MCP path supplies `"mcp"` (+ `ctx.client_id` when present), the HTTP
  path `"api"` (+ request id when present), the CLI runtime `"cli"`.
- A read accessor — `a2kit.log.current_surface() -> str | None` (and the
  client id) — lets a tool body and other dispatch stages read the active
  surface from the scope without touching `request_scope` internals.
- The `_CallScopeFilter` (ADR 0027) injects `surface` onto every
  `LogRecord`, so app-log lines and the durable call-record carry the
  surface field for free (the call-record's access-log row gains a
  `surface` column).

The stamping is **resolve-at-the-dispatching-surface**, not sniffed from
the ctx object's type: the bind path is authoritative and the same
mechanism extends to future surfaces (A2A / gRPC / GraphQL) by passing
their `Surface.name`.

## Capabilities

### Added Capabilities

- `surface-identity-context` — the contract that every framework dispatch
  stamps the invoking surface's identity (`surface` + optional
  `surface_client_id`) onto the per-call scope, that it is readable by
  tool bodies and dispatch stages, that it rides every log record and the
  durable call-record, and that absence (no surface resolvable) is a clean
  `None`, never a crash.

### Modified Capabilities

- `mcp-context-passthrough` — the MCP and CLI dispatch paths, which today
  bind only `ctx` into the per-call ambient state, ALSO resolve and stamp
  the surface identity. (Delta expressed as ADDED requirements on this
  capability — the existing ctx-binding requirements are unchanged in
  behaviour; surface stamping is an addition to the same bind sites.)

## Impact

- **ADDITIVE, non-breaking.** Two new optional `_CallScope` fields, two
  new optional `bind_call_scope` kwargs, one new read accessor, one extra
  injected `LogRecord` attribute. A tool that does not read `surface` is
  completely unaffected; an existing `bind_call_scope` caller that does
  not pass `surface=` gets `None` (today's behaviour).
- **Dependency: `refound-ldd-on-stdlib-logging`.** That change owns
  `_CallScope`, `bind_call_scope`, the `_CallScopeFilter`, and the
  `call-log` / `CallRecord` capability. This change EXTENDS those — it
  does not redefine their requirements. It must land after (or co-merge
  with) the refound change so the scope it extends exists. The
  `call-log` access-log row spec (refound) is referenced, not modified;
  the `surface` column rides the existing record via the filter.
- Affected code (delivered by a sibling implementation change, not here):
  `src/a2kit/packages/log/scope.py` (fields + accessor + filter),
  `src/a2kit/packages/dispatch/stages.py` (`CallScopeStage` resolution),
  and the per-surface bind paths that supply the identity.
- Forward-compatible with the Wave 1/2 surface unification: once the CLI
  is a `Surface` (Wave 1) and all three satisfy one `bind()` protocol, the
  identity each stamps is exactly its `Surface.name` — this change defines
  the contract the unified surfaces will satisfy.

## Non-goals

- **Not** routing/authorization decisions keyed on surface. This change
  only makes the surface *legible*; any "deny operator-only tool over the
  network" policy is `tool-authorization` / the `surfaces` projection axis
  (Wave 2), not here.
- **Not** the `surfaces` projection matrix (ADR 0028 Wave 2). Surface
  *identity* on the call scope is orthogonal to a verb's declared surface
  *presence*.
- **Not** a new durable-record concept. The `surface` field rides the
  existing ADR 0027 `CallRecord` / access-log row via the
  `_CallScopeFilter`; no `journal.record(...)` / `attach(...)` API.
- **Not** sniffing the surface from the ctx object's runtime type. The
  identity is resolved from the dispatching surface (the bind path),
  which is authoritative and extensible to non-ctx surfaces.
