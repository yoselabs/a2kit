## Context

`serve_process` (`packages/serve.py:161`) is the single serve entry point. It
branches three ways on `internal_uds`, and the three branches disagree on who
owns `async with runtime:`. ADR 0029 added the spoke path
(`_serve_with_spoke`, line 212): it enters the runtime **once**, builds the
listeners with `own_app_lifecycle=False` / `enter_runtime=False`, and runs them
under one `asyncio.gather`. That path is already the general form; this change
generalizes it into the only form and threads app-registered background services
through it.

Spikes that ground the decisions below:

- **S1 — concurrency idiom.** a2kit has **zero** `asyncio.TaskGroup` and exactly
  **one** `asyncio.gather` (the spoke). No supervisor exists; we are free to pick
  the correct primitive rather than honor a convention.
- **S2 — listeners self-terminate.** `uvicorn.Server.serve()` returns on
  `should_exit` (signal); `run_stdio_async()` returns on stdin EOF. The current
  spoke gather works *only* because both coros are self-terminating listeners.
- **S3 — bare paths are not load-bearing.** FastMCP `run("stdio")` is
  `anyio.run(run_async)` → `run_stdio_async()` (banner aside, no signal/setup).
  The spoke path already proves `run_stdio_async()` under our own `asyncio.run`
  + `async with runtime:` works. So the two bare branches can be deleted, not
  preserved.

## Goals / Non-Goals

**Goals:**
- An `App` can register `serve_services` that `serve` runs as concurrent tasks
  inside the one serve runtime lifecycle, each handed a `ServeContext`.
- Serve-scoped (never on a CLI verb), eager (at serve start, not first dispatch),
  path-exposed (`ctx.internal_uds`), shared-runtime, lifecycle-safe.
- Collapse the three serve branches into one supervised engine.

**Non-Goals:**
- Service ordering / dependencies; direct DI from a service; the scheduler and
  any job semantics (all a2kay-side or deferred — see proposal "Out of scope").

## Decisions

### D1 — `ServeContext` is minimal (`internal_uds` + `transport`)

A frozen dataclass in `packages/serve.py`, re-exported as `a2kit.ServeContext`.
The forcing consumer (a2kay) closes over its `LeaseRegistry` / `VaultLayout` /
history store at **compose** time and reaches the live core over the **loopback
spoke**, going through the same auth + dispatch path as any caller. So the
context does **not** expose the runtime/container: the only serve-bound facts a
service cannot get any other way are the bound socket path and the transport.

Consequence to state plainly: under `serve` **without** `--internal-uds`,
`ctx.internal_uds is None` and a spoke-driving service is functionally inert
(a2kay's scheduler returns immediately). The shared `async with runtime:` buys
*lifecycle and event-loop co-residence*, not DI access. The earlier ask's
"services can use the same store handles / DI" is therefore aspirational for v1
and intentionally **not** delivered by `ServeContext`; loopback is the supported
route to the store.

### D2 — `serve_services` rides on `AppRuntime`, carried by `build()`

`serve_cmd` does `runtime = build(app)` then `serve_process(runtime, ...)` —
serve never sees the `App`. So `serve_services` must be a carried field on
`AppRuntime`, set by `build()` from the App's `serve_services` ClassVar, joining
`cli_extras` / `dispatch_hook` / `mcp_middlewares` in the snapshot. Authoring
stays subclass-ClassVar for symmetry with `routers=` / `providers=`; a service is
`async def (ctx: ServeContext) -> None` (a coroutine **function**, not a
pre-awaited coroutine — serve calls `svc(ctx)` to inject the context).

A method/decorator registration form (`@app.serve_service`) is deliberately not
added in v1: the subclass-ClassVar covers the only consumer and matches the
existing axes. Add the decorator only if a non-subclass authoring path forces it.

### D3 — The supervisor is `asyncio.wait(FIRST_COMPLETED)`, not `TaskGroup`, not a flat gather

This is the load-bearing, counter-intuitive decision. Three semantic facts:

1. Listeners self-terminate (S2). Services may loop forever (a2kay's `while True`)
   **or** return immediately (a2kay's `internal_uds is None` early return).
2. Serve's lifetime is the **listener's** lifetime: first listener to stop ⇒ shutdown.
3. Any task **raising** — listener, spoke, or service — must tear serve down and
   surface non-zero, like a listener crash.

Therefore the union of {listeners, services} must be supervised
**asymmetrically**:

| event | action |
|---|---|
| a listener exits (clean or error) | serve is over → cancel the rest, teardown |
| any task raises | tear down, re-raise (nonzero exit) |
| a service exits **cleanly** | non-event → drop it, keep serving the listeners |

Why the obvious tools are wrong:

- **flat `gather(*listeners, *services)`** — hangs on shutdown: the listener
  returns on signal, `gather` still awaits the never-returning service. (This is
  what the original ask and a2kay's D1 sketch both wrote; both are wrong here.)
- **`asyncio.TaskGroup`** — *wait-for-all, cancel-on-error*. A listener returning
  while a service loops forever still hangs the group. 3.11's new toy is the
  wrong tool.
- **`asyncio.wait(FIRST_COMPLETED)` over the union, single-shot** — a
  cleanly-returning service (a2kay's `None` case) fires FIRST_COMPLETED and tears
  down the listeners at startup. Wrong.

The correct shape is a small loop that keeps the listener/service distinction:

```python
async def _supervise(listeners, services, *, on_teardown):
    l = [asyncio.create_task(c) for c in listeners]
    pending = set(l) | {asyncio.create_task(c) for c in services}
    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                if (exc := t.exception()) is not None:
                    raise exc            # any crash → finally cancels the rest, propagates
                if t in l:
                    return               # a listener stopped → shutdown
                # a service finished cleanly → ignore, keep serving
    finally:
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)  # best-effort drain
        on_teardown()                    # _cleanup_uds(uds) when a spoke is present
```

The spoke listener is classified as a listener (its unexpected exit ends serve,
matching today's symmetric gather). There is always ≥1 listener (stdio or http),
so the loop never spins on an empty listener set.

### D4 — One engine; the three branches deleted

`serve_process` becomes: compose args, build `ServeContext`, and
`asyncio.run(_serve(...))`. `_serve` (the generalized `_serve_with_spoke`):

```
async with runtime:
    ctx = ServeContext(internal_uds=uds, transport=transport)
    listeners = [ _public_listener(transport, host, port, runtime, mcp_options) ]
    if uds:
        listeners.append(_spoke_listener(runtime, uds))
    services = [ svc(ctx) for svc in runtime.serve_services ]
    await _supervise(listeners, services, on_teardown=lambda: _cleanup_uds(uds))
```

- `_public_listener` for `stdio` = `build_mcp_server(runtime, own_app_lifecycle=False,
  **mcp_options).run_stdio_async()`; for `http` =
  `uvicorn.Server(Config(build_parent_app(runtime, enter_runtime=False,
  mcp_options=...), host, port)).serve()`.
- The bare `internal_uds is None` branches in `serve_process` are removed
  outright — no compatibility shim (AGENTS.md §1).

### D5 — How a2kay consumes it (downstream contract, informational)

```python
class _Kay(a2kit.App):
    routers = (...)
    providers = (...)
    serve_services = (make_scheduler_service(c),)   # closes over c.leases / c.layout / history
```

The scheduler returns immediately if `ctx.internal_uds is None`; otherwise it
polls due jobs and dispatches them via `JobSpawner.run(name,
spoke_uds=ctx.internal_uds)` off the loop. See `a2kay-job-scheduler` design
D1/D2. a2kay bumps its a2kit pin to the release carrying this change.

## Risks / Trade-offs

- **[collapsing the bare stdio path]** → the pure `serve` case (stdio, no spoke,
  no services) now runs through `asyncio.run` + `own_app_lifecycle=False` instead
  of FastMCP's `.run()`. Proven by the spoke path *in combination with the
  spoke*, but the pure case needs a smoke test (one MCP `initialize` /
  `tools/list` round-trip) to confirm `anyio`-on-`asyncio.run` and banner/EOF
  behavior are identical. This is the one item the read-only spikes cannot close;
  it is task 5.1 and the verification gate.
- **[supervisor subtlety]** → the listener/service asymmetry is easy to get wrong
  (and the ask / a2kay's sketch did). The two regression tests in task 4 (clean
  service return must NOT kill serve; crashing service MUST) pin it.
- **[no service ordering]** → services launch unordered/independent; acceptable
  for the single-service consumer; revisit on a second consumer.

## Open Questions

- Should a crashing service's traceback be logged distinctly from a listener
  crash before propagation? v1 propagates uniformly (nonzero exit); add a
  log line if operational noise warrants.
