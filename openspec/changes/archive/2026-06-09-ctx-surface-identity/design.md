# Design — ctx-surface-identity

Short note: this is an additive extension to an existing seam, so design
is mostly "where, exactly, does the stamp go." Recorded to prevent
re-litigation (ADR 0005) on the one real choice.

## The seam: extend `_CallScope`, not the ctx object

ADR 0027 (`refound-ldd-on-stdlib-logging`) created `_CallScope` — the
neutral per-call identity published on `request_scope`, bound by the
transport-neutral `CallScopeStage`. It already carries `ctx`, `call_id`,
`tool_name`, and the span fields. Surface identity is *exactly* this kind
of per-call fact, so it goes here as two more fields rather than onto the
ctx object.

Why not stamp it on the ctx object?

- The CLI's `StderrToolContext` and a future surface's stub may be
  type-indistinguishable; the ctx type is not a reliable surface oracle.
- The durable call-record and other dispatch stages read the *scope*, not
  the ctx. Putting surface on the scope makes it free for the record and
  the `_CallScopeFilter` (one injection point).
- It keeps ctx as the pure transport-emission endpoint (ADR 0027's
  framing) — surface is metadata about the call, not part of the wire.

## Resolve at the dispatching surface (not by sniffing)

ADR 0028's resolution line is "each Surface stamps its own name as it
dispatches." The authoritative source is the bind path:

- the MCP wrapper knows it is MCP (and can read `ctx.client_id`);
- the HTTP route knows it is `"api"` (and can read a request id);
- the CLI runtime knows it is `"cli"`.

`CallScopeStage` is transport-neutral, so the identity is threaded *into*
it from the per-surface dispatch entry (today: a small per-path argument;
post-Wave-1 when the CLI is a `Surface`, simply `surface.name`). This is
the same extensibility the `Surface` protocol already gives every other
per-surface concern: a new A2A/gRPC surface stamps its own `name` with no
core change.

## Backward compatibility

- New `_CallScope` fields default `None`.
- New `bind_call_scope(...)` kwargs default `None`; existing callers are
  untouched.
- The `_CallScopeFilter` injects `surface` unconditionally (value `None`
  outside a dispatch) — same shape as the existing `call_id` / `tool_name`
  / `elapsed_ms` injection, so no handler or formatter needs to change to
  *not* break; formatters that want the field opt in.

## Dependency boundary

This change does not redefine any `refound-ldd-on-stdlib-logging`
requirement. It adds fields to that change's `_CallScope`, kwargs to its
`bind_call_scope`, an injection to its `_CallScopeFilter`, and a column to
its access-log row — all via the new `surface-identity-context` capability
plus ADDED requirements on `mcp-context-passthrough`. It must merge after
(or with) the refound change.
