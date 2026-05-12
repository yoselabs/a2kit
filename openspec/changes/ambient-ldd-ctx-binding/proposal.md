## Why

The LDD primitives (`a2kit.ldd.event`, `a2kit.ldd.report`, `a2kit.ldd.log`) currently require every caller to thread `ctx` through the call chain. Round-5/round-6 a2web feedback flags ~30 LOC of pure `ctx`-threading inside phase functions whose only job is to reach a single `ldd.event` deep in the workflow — a parameter that adds no logic, only plumbing.

The per-call `_LddState` is already carried in a `ContextVar` (see `ldd_state_for_call`), and dispatch sites (CLI `_invoke_tool_in_process`, MCP `_wrap_with_ldd_state`, the in-process test client) already enter that contextmanager around tool bodies. Binding the live `ctx` into the same context-scoped state lets callers drop the parameter entirely.

## What Changes

- **BREAKING**: `a2kit.ldd.event`, `a2kit.ldd.report`, `a2kit.ldd.log`, `a2kit.ldd.debug`, `a2kit.ldd.info`, `a2kit.ldd.warning`, `a2kit.ldd.error` drop their leading `ctx` positional argument. Callers invoke `await a2kit.ldd.event("name", count=30)` etc.
- **BREAKING**: `EventRegistry.emit_typed(ctx, evt)` drops `ctx`, becomes `emit_typed(evt)`.
- `ldd_state_for_call` gains a required keyword `ctx` — the live `fastmcp.Context` / `StderrToolContext` for the call. The active `_LddState` carries it.
- Dispatch sites pass `ctx` into `ldd_state_for_call`: `_wrap_with_ldd_state` (MCP), `_invoke_tool_in_process` (CLI), `TestClient` (testing).
- Calling any LDD primitive outside an active `ldd_state_for_call` (no ambient `ctx`) raises `AmbientContextMissing` (new, subclass of `RuntimeError`) with a message naming the function and pointing at the dispatch contract. No silent no-op.
- Explicit-ctx form is removed entirely (option b in design.md). One way to call.
- `OPERATIONAL_CONTRACTS.md` gains a note: LDD primitives MUST be called from inside a tool body (or a sub-coroutine of one). Lifecycle hooks (`on_startup` / `on_shutdown`) are not tool calls and have no ambient ctx; they may not use LDD primitives.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `mcp-context-passthrough`: the "LDD event and report primitives are protocol-neutral functions" requirement changes signature (no `ctx`); a new requirement covers ambient binding via the dispatch contextvar and the "called outside a tool body" failure mode. The typed event registry requirement loses its `ctx` argument.
- `operational-contracts`: add a clause that LDD primitives require an ambient tool dispatch.

## Impact

- All in-tree call sites of `event`/`report`/`log`/`info`/`warning`/`error`/`debug` (~ check `grep -rn "ldd\.event\|ldd\.report\|ldd\.log\|ldd\.info\|ldd\.warning\|ldd\.error\|ldd\.debug"`) update mechanically: drop the first positional.
- Dispatch sites: `src/a2kit/packages/mcp/server.py::_wrap_with_ldd_state`, `src/a2kit/packages/cli/runtime.py::_invoke_tool_in_process`, `src/a2kit/packages/testing/client.py::TestClient.call_tool` all pass `ctx=` into `ldd_state_for_call`.
- a2web and downstream apps: one-time mechanical migration. The user has stated explicitly: no backward-compat shim.
- Cold-start: unchanged. Same contextvar already in place; we add one field.
