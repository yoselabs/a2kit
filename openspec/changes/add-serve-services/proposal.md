# add-serve-services

## Why

An a2kit app must sometimes run a **long-lived background coroutine for the
whole lifetime of `serve`** — a scheduler, a health beacon, a cache warmer, a
metrics pusher — sharing the one runtime (and its `SINGLETON` store handle) with
the listeners, and starting **only** under `serve`, never for a one-shot CLI
verb.

The forcing consumer is the a2kay change `a2kay-job-scheduler` (gated on this
landing): it adds an in-`serve` job scheduler that must (a) start eagerly when
`serve` starts, (b) live for the whole serve lifetime on the one runtime, (c)
never fire during a plain CLI verb like `entity read`, and (d) learn the bound
`--internal-uds` path so it can dial the internal spoke (ADR 0029) to drive jobs
as loopback subprocesses.

a2kit 0.44 satisfies **none** of these. The two concrete gaps (verified against
source):

1. **No serve-scoped, eager lifecycle hook.** `App(lifespan=)` and
   `Router.lifespan` were removed in 0.43. The only remaining hook,
   `Router.__aenter__`, is **lazy and dispatch-scoped** — it fires on the first
   dispatch of one of that router's tools (`runtime.py::_ensure_router_entered`).
   A plain CLI verb *is* a dispatch, so a service hung off a router would run in
   CLI mode; and in serve mode it would not start until some tool was called.
   Wrong trigger.
2. **The bound `internal_uds` is not exposed to app code.** It is threaded
   CLI → `serve_cmd` → `serve_process(internal_uds=...)` →
   `_serve_with_spoke(uds_path=...)` and stored on no object app code can read.

This is **substrate**, not product: the same co-evolution shape as ADR 0029 —
a2kay needs a serve primitive, a2kit grows the minimal generic hook, a2kay
consumes it. Any a2kit app with a single-writer store + co-resident workers (or
any periodic in-serve task) hits this identically. If consumers hand-roll it,
each one re-implements serve's private `_serve_with_spoke` / gather topology and
couples to it — exactly the drift a2kit's no-redundancy doctrine forbids.

## What Changes

### 1. `ServeContext` — a serve-only value object

```python
@dataclass(frozen=True)
class ServeContext:
    internal_uds: str | None   # the bound --internal-uds path, or None when no spoke
    transport: str             # "stdio" | "http"
```

Exported as `a2kit.ServeContext`. Kept deliberately minimal: serve-only concerns
stay off the always-on runtime/config surface, and a service reaches the live
core through the **loopback spoke** (over `internal_uds`), never the container —
so the context needs only the loopback address and the transport, not a DI
handle. (If a future consumer needs direct DI from a service, that is an additive
extension, not a v1 gap.)

### 2. `serve_services` — an `App` registration axis

A service is `async def (ctx: ServeContext) -> None`. The App declares them with
the same subclass-ClassVar style as `routers=` / `providers=`:

```python
class MyApp(a2kit.App):
    serve_services = (my_service,)   # tuple of service coroutine-functions
```

`build()` carries the tuple onto the `AppRuntime` (alongside `cli_extras`,
`dispatch_hook`); `serve_process` reads it off the runtime. An App with no
`serve_services` behaves exactly as today (no-op default).

### 3. `serve_process` collapses to one supervised engine

Today `serve_process` has **three** divergent paths that disagree on who owns
`async with runtime:`:

- stdio, no spoke → `build_mcp_server(rt).run("stdio")` (FastMCP owns loop + runtime),
- http, no spoke → `uvicorn.run(build_parent_app(rt))` (uvicorn owns loop, parent owns runtime),
- spoke → `asyncio.run(_serve_with_spoke(...))` (a2kit owns loop + runtime + gather).

The spoke path is already the general form. Grounding confirmed (a) FastMCP's
`run("stdio")` is just `anyio.run(run_async)` → `run_stdio_async()` with no
signal/setup of its own, and (b) the spoke path **already** runs
`run_stdio_async()` under our own `asyncio.run` + `async with runtime:` in
production. So the bare paths are an un-generalized special case, not load-bearing.

Per a2kit's no-redundancy / no-backward-compat doctrine, **delete the three
branches and serve through one engine** that always runs under one
`async with runtime:`, composes the public listener (+ optional spoke) +
registered services into one supervised task set, and tears down cleanly.

### 4. A real supervisor, not a flat gather

Background services do not self-terminate (a2kay's scheduler is a `while True`
poll loop). A symmetric `asyncio.gather(*listeners, *services)` would **hang on
shutdown** — the listener returns on signal, the gather still blocks on the
never-returning service. And the naive fix (`asyncio.wait(FIRST_COMPLETED)` over
the union) is also wrong: a2kay's service *returns immediately* when
`internal_uds is None`, which under FIRST_COMPLETED would tear down the listeners
at startup.

So serve treats the two kinds **asymmetrically**: a listener exiting (clean or
error) ends serve; any task raising tears serve down and propagates; a service
finishing **cleanly** is a non-event. The primitive is
`asyncio.wait(..., return_when=FIRST_COMPLETED)` in a small loop that drops
cleanly-finished services and keeps serving — **not** `asyncio.TaskGroup` (which
waits-for-all and would hang on the forever-loop). See `design.md` D3.

### 5. CLI verbs never run services

Services are launched **solely** inside the serve engine, so ordinary verb
dispatch (`run()` → `cli.main(...)`) never touches them. Falls out of (3).

## Out of scope (this change)

- The scheduler itself, job metadata, run history, cron — all a2kay-side
  (`a2kay-job-scheduler`).
- Any change to the public MCP/API edge auth or the spoke's `TokenAuth`.
- Service ordering / inter-service dependencies — v1 launches them unordered and
  independent; add ordering only if a real second consumer forces it.
- Direct container access from a service (loopback covers the v1 consumer).
