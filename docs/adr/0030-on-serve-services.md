---
id: "0030"
status: accepted
date: 2026-06-20
last_reviewed: 2026-06-20
supersedes: []
superseded_by: null
tags: [serve, lifecycle, surface, architecture, jobs, async]
deciders: [Denis Tomilin]
---

# ADR 0030: On-serve background services and the serve supervisor

## Status

Accepted, 2026-06-20. Delivered by the OpenSpec change `add-serve-services`
(applied; full suite green, 1602 passed); confirmed by the human (Constitution
Phase A). Adds a Tier-1 public export (`a2kit.ServeContext`) and an `App`
authoring axis (`serve_services`), so it **extends ADR 0004**'s tier list; it
does not supersede it. Same co-evolution lineage as **ADR 0029** (a2kay needs a
serve primitive, a2kit grows the minimal generic hook).

## Summary

In one sentence: an a2kit `App` may register **on-serve services** — background
coroutines that `serve` runs as concurrent tasks inside its one
`async with runtime:`, each handed a `ServeContext` carrying the bound
`--internal-uds` path — and along the way the three divergent `serve_process`
branches collapse into a single supervised engine whose shutdown is correct for
non-terminating services.

## The problem

a2kay (`a2kay-job-scheduler`) adds an in-`serve` job scheduler that must start
eagerly at serve start, live for the whole serve lifetime on the one runtime,
never fire during a plain CLI verb, and learn the bound `--internal-uds` path to
dial the spoke (ADR 0029). a2kit 0.44 exposes no mechanism that satisfies all
four:

- `App(lifespan=)` / `Router.lifespan` were removed in 0.43; the only remaining
  hook, `Router.__aenter__`, is **lazy and dispatch-scoped** — it fires on first
  tool dispatch, so it runs in CLI mode and not at serve start. Wrong trigger.
- The bound `internal_uds` is threaded into `_serve_with_spoke` and stored on no
  object app code can read.

This is substrate: any a2kit app with a co-resident worker or a periodic in-serve
task hits it identically.

## The decision

1. **`ServeContext`** — a frozen value object (`internal_uds: str | None`,
   `transport: str`), exported as `a2kit.ServeContext`. Minimal on purpose:
   serve-only facts stay off the always-on runtime/config surface, and a service
   reaches the live core over the **loopback spoke**, never the container — so
   the context needs only the loopback address and the transport.

2. **`serve_services`** — an `App` ClassVar tuple of `async def (ctx) -> None`
   coroutine functions, symmetric with `routers=` / `providers=`. `build()`
   carries it onto the `AppRuntime`; `serve_process` reads it there (serve never
   sees the `App`). Launched **only** inside the serve engine, so CLI verbs never
   run services. No-op default when empty.

3. **Collapse to one supervised engine.** `serve_process`'s three branches
   disagreed on who owns `async with runtime:`. The spoke path
   (`_serve_with_spoke`) was already the general form; grounding confirmed
   FastMCP's `run("stdio")` is just `anyio.run → run_stdio_async()` and that the
   spoke path already runs `run_stdio_async()` under our own `asyncio.run`. So the
   bare branches are deleted (no shim, AGENTS.md §1) and serve always runs the
   public listener (+ optional spoke) + services under one runtime.

4. **The supervisor is `asyncio.wait(FIRST_COMPLETED)`, not `TaskGroup`, not a
   flat gather.** Background services do not self-terminate. A flat
   `gather(*listeners, *services)` hangs on shutdown; `TaskGroup` (wait-for-all)
   hangs the same way; `FIRST_COMPLETED` over the union single-shot wrongly tears
   down on a service that returns cleanly. The correct rule is asymmetric: a
   **listener** exiting (clean or error) ends serve; **any** task raising tears
   serve down and propagates; a **service** finishing cleanly is a non-event. A
   small `asyncio.wait(FIRST_COMPLETED)` loop that drops cleanly-finished
   services and cancels-and-drains the rest on teardown expresses exactly that.

## Consequences

- New Tier-1 surface (`ServeContext`) and authoring axis (`serve_services`);
  `AppRuntime` carries one more field.
- a2kit gains a generic "background service during serve" primitive (health
  beacons, cache warmers, metrics pushers), not just the scheduler.
- One serve path instead of three — less to reason about, no redundant branches.
- The pure bare path (plain stdio MCP) now flows through `asyncio.run` +
  `own_app_lifecycle=False`; equivalent in principle and to the spoke path, but
  gated on a smoke test (the one thing read-only grounding could not close).
- a2kay registers exactly one service and stays ignorant of serve internals; it
  gates on the release carrying this change.

## Deferred

- Service ordering / inter-service dependencies — v1 launches unordered and
  independent; add only on a second forcing consumer.
- Direct container access from a service — loopback covers the v1 consumer; a
  context-carried runtime handle is an additive extension if ever forced.
- A decorator registration form (`@app.serve_service`) for non-subclass authoring.

## Alternatives considered

- **a2kay owns its own `serve` wrapping `serve_process`** — rejected: it
  reimplements serve dispatch and couples a2kay to a2kit's private
  `_serve_with_spoke` / gather. Since the same owner holds a2kit, the hook
  belongs in a2kit (reusable by any app). Mirrors ADR 0029's same call.
- **Expose `internal_uds` on the runtime/config instead of a `ServeContext`** —
  rejected: pushes a serve-only concern onto the always-on surface; a value
  object is explicit, immutable, and extensible.
- **`asyncio.TaskGroup`** — rejected: wait-for-all semantics hang on a
  non-terminating service after the listener exits (see decision 4).
