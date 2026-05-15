## Why

a2web round-10 Friction B closure. The user-visible pain: every tool
in an LDD-emitting router declares `ctx: a2kit.ToolContext` and then
`del ctx` because the body never uses it. The ceremony exists purely
to make ambient `ctx` non-None so LDD primitives don't raise
`AmbientContextMissing` Mode B.

The earlier proposal (`add-router-ldd-marker`) addressed this with a
per-router opt-in flag. That was the wrong shape — patching a problem
the framework created for itself. Re-examination revealed:

1. **LDD = Log-Driven Development.** The primary audience for LDD
   output is a post-hoc reader (an AI agent diagnosing what happened
   by reading structured logs), not a live wire observer. The
   sink-side emission (logs persisted, OTEL spans, test capture) is
   the core value; wire emission is a secondary live-UX nicety.

2. **Today's Mode B raise is actively wrong for log-driven
   debugging.** A tool that emits valuable diagnostic events crashes
   because wire emission isn't possible, even though sink emission
   would have worked. The framework forces a failure where degraded
   success was correct.

3. **Ambient state already binds unconditionally on every dispatch
   today** (verified at `packages/mcp/server.py:55-99` and
   `packages/cli/runtime.py:61-82`). The only thing the
   ctx-in-signature gate controls is the *value* of ambient ctx
   (non-None vs None). Mode B is a self-inflicted gate.

The fix is to align the framework with LDD's purpose: emit always,
wire-emit when possible, fail loud only when there's genuinely no
dispatch.

## What Changes

### Implementation — three small, coordinated edits

1. **MCP wrapper** (`packages/mcp/server.py`):
   `_ensure_ctx_in_rewritten_signature` is called unconditionally for
   every tool whose body is wrapped, not only when `ctx_param_name`
   is set. fastmcp introspects the rewritten signature and injects
   ctx for every tool. The wrapper extracts ctx from kwargs into
   ambient state, then pops the kwarg before invoking the tool body
   unless the original signature declared it.

2. **CLI runtime** (`packages/cli/runtime.py`):
   `StderrToolContext()` is always synthesized for ambient binding
   even when the tool body doesn't declare `ctx`. The kwarg merge into
   the body remains gated on declaration (unchanged from today's
   behaviour for declared-ctx tools).

3. **LDD primitives** (`packages/ldd/__init__.py`):
   `_require_ambient_state` retires the second-mode check. Today:

   ```python
   if state is None:
       raise AmbientContextMissing(... mode=MODE_NO_DISPATCH)
   if state.ctx is None:
       raise AmbientContextMissing(... mode=MODE_MISSING_CTX_PARAM)
   ```

   After:

   ```python
   if state is None:
       raise AmbientContextMissing(... mode=MODE_NO_DISPATCH)
   # state.ctx is guaranteed non-None inside any dispatch
   # (post-change to wrapper + runtime above).
   ```

   `AmbientContextMissing.MODE_MISSING_CTX_PARAM` becomes
   unreachable. We keep the constant for any external callers but
   document it as historical.

### Spec — `mcp-context-passthrough`

- **MODIFIED**: existing "ctx-in-signature ⇒ ambient binds" wording
  in `mcp-context-passthrough` and `operational-contracts`
  simplifies to "ambient ctx is non-None inside any framework
  dispatch" — invariant rather than conditional.
- **ADDED**: scenarios pinning the new behaviour (LDD emission with
  no ctx in tool signature, wire-side wire format still fires under
  MCP, sink-side fires under both).

### Tests

- New BDD scenarios under `tests/packages/mcp/` and `tests/packages/cli/`:
  - Tool with no ctx param emits `await a2kit.ldd.event(...)` under
    real MCP transport — `client.events` captures the event with
    correct payload + `elapsed_ms`.
  - Same on CLI runtime — emission renders to stderr.
  - Mode B raise no longer fires inside a dispatch (regression test).
- Update or retire tests that currently assert Mode B's raise
  (find via `grep -rn "MODE_MISSING_CTX_PARAM\|missing_ctx_param"`).

## Out of scope

- Promoting `a2kit.ToolContext` to a Protocol. Separate proposal
  (`context-as-protocol`); independent of this change.
- Feature Protocols / capability system. Parked.
- Any new public surface symbol. This change adds no consumer API.
- Touching `Resource.warm_up()`, `Router.emits_ldd`, or any other
  earlier-considered patch shape. All abandoned.

## Impact

- **Migration**: a2web (and anyone else with `del ctx` ceremony)
  drops the param after upgrading. No code breakage.
- **Spec**: `mcp-context-passthrough` simplifies; one capability
  becomes uniform rather than conditional.
- **Surface**: no new symbols; one error mode (Mode B) becomes
  unreachable but the class isn't removed.
- **Cold start**: unchanged.
- **Cross-transport parity**: improved — both MCP and CLI now
  uniformly bind non-None ambient ctx.

## Why this is correct (not just convenient)

The "ctx-in-signature gates ambient ctx" rule was an artifact of how
the wrapper was wired, not a design principle. LDD's
log-driven-development purpose makes sink-side emission the primary
contract; gating it on wire-side availability is incidental
complexity. Removing that gate aligns behavior with intent.
