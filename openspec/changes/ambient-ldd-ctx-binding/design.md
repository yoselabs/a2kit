## Context

LDD primitives (`event`, `report`, `log` and its `info`/`warning`/`error`/`debug` shorthands) are free functions in `a2kit.packages.ldd` that fan out to either the MCP transport (`fastmcp.Context.log`) or the CLI stub (`StderrToolContext._emit`). Per-call state (kill-switches, declared report type, tool name, elapsed-ms basis, in-process sinks) already flows via `contextvars.ContextVar` — `ldd_state_for_call` sets it on tool entry and resets on exit. The three dispatch sites that enter that scope are the MCP wrapper (`_wrap_with_ldd_state`), the CLI runtime (`_invoke_tool_in_process`), and the test client (`TestClient.call_tool`).

Today, `ctx` is the one piece NOT carried in that state. Every caller threads it through positional argument 1. Round-5/round-6 a2web feedback (`docs/history/A2KIT_FEEDBACK.md` gap 2) reports ~30 LOC of pure plumbing inside phase functions whose only role is to reach a leaf `ldd.event` call — no other use of `ctx` at any layer in between. The asymmetry is unmotivated: every other piece of per-call state is ambient.

## Goals / Non-Goals

**Goals:**
- Make `a2kit.ldd.{event,report,log,info,warning,error,debug}` and `EventRegistry.emit_typed` callable WITHOUT a `ctx` argument. The ambient `ctx` is the one bound by the active `ldd_state_for_call`.
- One way to call. No explicit-ctx overload.
- Fail loudly when called outside an active dispatch: raise `AmbientContextMissing` with a message naming the function and pointing at the dispatch contract. No silent drop, no fake `ctx`.
- Preserve concurrency isolation: `contextvars.copy_context()` semantics already isolate per-task; nothing changes for `asyncio.gather`, `asyncio.TaskGroup`, etc.
- Preserve cold-start budget. No new imports on the hot path.

**Non-Goals:**
- Backwards compatibility. The user has explicitly stated "remove any backward compat, we should not care about it." No shim, no deprecation period, no two-signature overload.
- Allowing LDD primitives from lifecycle hooks (`on_startup` / `on_shutdown`). Those don't have a tool ctx; if a hook needs to emit, that's a separate proposal.
- Adding new `ctx`-shaped helpers (e.g. `a2kit.ldd.current_ctx()`). Not in scope; revisit if a real user need surfaces.

## Decisions

### D1: Bind `ctx` into `_LddState` and remove the explicit `ctx` parameter from all LDD primitives (option b, not option a)

**Decision.** `_LddState` gains a `ctx: Any` field (typed `Any` to keep CLI stub + `fastmcp.Context` shapes both fitting without an import). `ldd_state_for_call` gains a required `ctx=` kwarg. All LDD primitive signatures drop their first positional. There is no explicit-ctx overload.

**Alternative considered (option a — keep both forms).** Accept `ctx` optionally as a first positional; fall back to ambient if omitted. Rejected because:

1. The user has explicitly asked for no back-compat. A dual signature is back-compat-by-overload.
2. Two ways to call doubles the cognitive surface and produces inconsistent code (some files thread ctx, others don't, no rule for which). One-way is cleaner.
3. The leaf-call-site value of explicit-ctx is near zero: every legitimate call is inside a tool body where ambient ctx is set. The only place explicit-ctx might matter is a unit test that wants to bypass dispatch — and those tests should use `ldd_state_for_call` directly (it's already the test seam).

**Why option b is bolder and right here.** It treats ambient ctx the same way every other piece of LDD state is treated. It removes ~30 LOC per phase chain in a2web. It collapses two signatures to one. The migration cost (one mechanical sweep) is paid once.

### D2: Failure mode when called outside an active dispatch

Calling an LDD primitive when `_LDD_STATE.get()` is `None` (i.e. outside `ldd_state_for_call`) raises `AmbientContextMissing(RuntimeError)`. The message names the function (`a2kit.ldd.event`) and says: "call this from inside a tool body; lifecycle hooks and module-level code are not tool dispatches". This replaces today's silent fallback to a default `_LddState` for emit time — that fallback was harmless when `ctx` was a parameter, but now there's no ctx to emit through.

Alternative considered: silent no-op. Rejected — silent no-op hides bugs (a forgotten `await` inside a tool, a `print`-equivalent leaking from a lifecycle hook). Loud failure is preferred.

Alternative considered: emit to stderr without a ctx. Rejected — the LDD wire contract carries `elapsed_ms` basis-stamped at dispatch start and a `tool_name`. Both are dispatch concepts. Synthesizing them produces misleading telemetry.

### D3: ContextVar lifecycle and concurrency isolation

The dispatch site enters `ldd_state_for_call(ctx=ctx, ...)` as a `contextmanager`. The set/reset pair is already correct (uses a token, resets on exit). Concurrency:

- `asyncio.gather(coro1(), coro2())` — both coroutines inherit the same Context (the dispatcher's). Both see the same ambient ctx. Correct: they're running inside the same tool call.
- `asyncio.create_task(coro())` — captures the current Context at task creation. The task sees the dispatcher's ctx. Correct.
- Nested tools (a tool that invokes another tool via `TestClient` or the App's container): the inner dispatch re-enters `ldd_state_for_call` with its own ctx, the outer one is shadowed for the duration, restored on exit via the token. Correct — this is exactly what `ContextVar.set/reset` is designed for.

No new locking, no new task-local storage.

### D4: Lifecycle hooks remain LDD-free

`on_startup` / `on_shutdown` do not have a tool ctx. They run outside `ldd_state_for_call`. Today's primitives silently use a fallback state in that case; after this change, they raise. This is acceptable: nothing in the codebase or the docs currently encourages LDD use from lifecycle. The `operational-contracts` spec gains a clause making this explicit.

### D5: `EventRegistry.emit_typed` loses its `ctx` argument

`emit_typed` delegates to `event(...)` and then calls `ctx.report_progress(...)` if a progress callback is registered. The `report_progress` call needs the ambient ctx too — pull it from `_current_state().ctx`. Signature becomes `async def emit_typed(self, evt: Any) -> None`.

## Risks / Trade-offs

- **[Risk]** A caller invokes an LDD primitive from a `loop.call_soon`-scheduled callback that ran after the dispatch returned. The token has been reset and the call raises. **Mitigation:** This is the desired behaviour. Such callbacks are running outside the tool body's lifetime — emitting on behalf of a finished tool is itself a bug. The error message points at the dispatch contract.
- **[Risk]** Background `asyncio.create_task(...)` started inside a tool body, expected to outlive the tool. Once the dispatcher exits, the background task's captured Context still holds the (now-reset) token's prior value via `_LDD_STATE.set`'s saved state — but `contextvars` copies the snapshot, so the background task continues to see the per-call state even after the outer reset. **Mitigation:** This is correct `contextvars` semantics. Users who want telemetry from background tasks can `asyncio.create_task` while the tool is still alive; the task's copy keeps the LDD state until the task ends. Document this in design.md only; not a spec requirement.
- **[Trade-off]** One-way callsite. Some tests that previously called `await event(ctx, "x", k=1)` directly without a dispatcher now need to use `with ldd_state_for_call(ctx=fake_ctx, ...):` to set ambient state. The test seam already exists and is used by `TestClient`. Test-only ergonomics cost is small; correctness gain is large.
- **[Trade-off]** Cross-cutting mechanical sweep across the repo and a2web. One commit per package is fine; the user accepts this in exchange for losing 30 LOC of plumbing per phase chain.

## Migration Plan

1. Update `_LddState` dataclass: add `ctx: Any = None`. Update `ldd_state_for_call` to take `ctx=` (required kwarg).
2. Update `event`, `report`, `log`, `info`, `warning`, `error`, `debug` signatures — drop `__ctx` positional, pull from `_current_state().ctx`. Raise `AmbientContextMissing` if `_LDD_STATE.get() is None`.
3. Update `EventRegistry.emit_typed` — drop `ctx` positional.
4. Update dispatch sites (`_wrap_with_ldd_state`, `_invoke_tool_in_process`, `TestClient.call_tool`) to pass `ctx=ctx` into `ldd_state_for_call`.
5. Mechanical sweep of in-tree callers (grep + edit).
6. Update `OPERATIONAL_CONTRACTS.md`: LDD primitives must be called from inside a tool body.
7. Bump version. Release notes call out the breaking change.

Downstream (a2web): same mechanical sweep — drop the first positional. Roughly -30 LOC per phase chain.

## Open Questions

- Should `AmbientContextMissing` live in `a2kit.exceptions` (next to `ReportTypeMismatch`) or in `a2kit.packages.ldd`? Lean toward `a2kit.exceptions` for symmetry with the other LDD exceptions. Tasks file picks one.
