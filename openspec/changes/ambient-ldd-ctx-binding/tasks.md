## 1. LDD core changes

- [ ] 1.1 Add `ctx: Any = None` field to `_LddState` dataclass in `src/a2kit/packages/ldd/__init__.py`
- [ ] 1.2 Make `ldd_state_for_call` take a required `ctx=` keyword and store it on `_LddState`
- [ ] 1.3 Add `AmbientContextMissing(RuntimeError)` exception in `src/a2kit/exceptions.py`
- [ ] 1.4 Add `_require_ambient_state(fn_name: str) -> _LddState` helper that returns `_LDD_STATE.get()` if non-None, else raises `AmbientContextMissing(fn_name)`
- [ ] 1.5 Rewrite `event` signature: drop `__ctx` positional; resolve `ctx = _require_ambient_state("a2kit.ldd.event").ctx`; keep both kwargs/typed forms intact
- [ ] 1.6 Rewrite `report` signature: drop `ctx` positional; resolve ambient ctx; keep type validation logic
- [ ] 1.7 Rewrite `log` signature: drop `__ctx` positional; resolve ambient ctx; update `info`/`warning`/`error`/`debug` shorthands accordingly
- [ ] 1.8 Rewrite `EventRegistry.emit_typed` signature: drop `ctx` positional; resolve ambient ctx for both the inner `event(...)` call and the `ctx.report_progress(...)` call
- [ ] 1.9 Update module docstring and per-function docstrings to reflect no-`ctx` signatures and the ambient binding contract
- [ ] 1.10 Update `__all__` exports to include `AmbientContextMissing` if it lives in the LDD module (otherwise re-export from `a2kit.exceptions`)

## 2. Dispatch site updates

- [ ] 2.1 Update `_wrap_with_ldd_state` in `src/a2kit/packages/mcp/server.py` to pass `ctx=` (the fastmcp Context from kwargs) into `ldd_state_for_call`
- [ ] 2.2 Update `_invoke_tool_in_process` in `src/a2kit/packages/cli/runtime.py` to pass `ctx=` (the `StderrToolContext` instance) into `ldd_state_for_call`
- [ ] 2.3 Update `TestClient.call_tool` in `src/a2kit/packages/testing/client.py` to pass `ctx=` (the test stub) into `ldd_state_for_call`
- [ ] 2.4 Audit any other entry into `ldd_state_for_call` in the repo and update each one to pass `ctx=`

## 3. In-tree caller sweep

- [ ] 3.1 `grep -rn "a2kit\.ldd\.\(event\|report\|log\|info\|warning\|error\|debug\)\|ldd\.events\.emit_typed" src/ tests/ examples/` to enumerate call sites
- [ ] 3.2 Mechanically drop the leading `ctx` positional argument from every call site
- [ ] 3.3 For tests that call LDD primitives directly without a dispatch, wrap with `ldd_state_for_call(ctx=<stub>, ...)` or move them to use `TestClient`

## 4. Spec doc + operational contract

- [ ] 4.1 Update `OPERATIONAL_CONTRACTS.md` with the new clause: LDD primitives require an active tool dispatch; lifecycle hooks / factories / module-level code must not use them
- [ ] 4.2 Update `a2kit.ldd` module README / public docs (if any) to show the new no-`ctx` call style

## 5. Tests

- [ ] 5.1 Add a test that calling each primitive (`event`, `report`, `log`, `info`, `warning`, `error`, `debug`, `emit_typed`) outside any dispatch raises `AmbientContextMissing` with a message naming the function
- [ ] 5.2 Add a test that an `on_startup` hook calling `a2kit.ldd.info` raises `AmbientContextMissing`
- [ ] 5.3 Add a test under MCP transport that `await a2kit.ldd.event("x", k=1)` (no ctx arg) delivers the event correctly
- [ ] 5.4 Add a test under CLI transport that the same call writes the expected stderr LDD line
- [ ] 5.5 Add a test under `TestClient` that the same call is captured correctly
- [ ] 5.6 Add a concurrency test: `asyncio.gather(sub_a(), sub_b())` inside a tool body — both sub-coroutines emit through the ambient ctx, both visible on the wire
- [ ] 5.7 Add a nested-dispatch test: tool A invokes tool B via `TestClient`; events from A and B end up on the correct respective ctxs
- [ ] 5.8 Add a background-task test: `asyncio.create_task` inside a tool body keeps the captured LDD state until the task ends, even after the outer dispatch resets

## 6. Release prep

- [ ] 6.1 Run `openspec validate ambient-ldd-ctx-binding --strict`
- [ ] 6.2 Bump version (minor or major per project convention for breaking changes)
- [ ] 6.3 Write CHANGELOG entry calling out the breaking signature change and the migration recipe (drop the first positional)
- [ ] 6.4 Notify a2web maintainer; coordinate the mechanical sweep on that side
