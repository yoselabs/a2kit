# Tasks — add-serve-services

## 1. `ServeContext` + the authoring axis

- [x] 1.1 Add `ServeContext` (frozen dataclass: `internal_uds: str | None`,
      `transport: str`) in `packages/serve.py`. Add type alias
      `ServeService = Callable[[ServeContext], Awaitable[None]]`.
- [x] 1.2 Re-export `ServeContext` from the `a2kit` facade (Tier-1 public
      surface). Confirm cold-start: the export must not pull serve/uvicorn at
      `import a2kit` (lazy, like the rest of `packages.serve`).
- [x] 1.3 Add `serve_services: ClassVar[tuple[ServeService, ...]] = ()` to
      `App` (`app.py`), documented alongside `routers` / `providers`.

## 2. Carry services onto the runtime

- [x] 2.1 `AppRuntime.__init__` gains `serve_services: tuple[ServeService, ...]
      = ()`; add a `serve_services` read property.
- [x] 2.2 `build()` reads the App's `serve_services` ClassVar and passes it into
      `AppRuntime(...)` (next to `cli_extras` / `dispatch_hook`). Idempotent-on-
      `AppRuntime` path unaffected.
- [x] 2.3 Tests: `build(app).serve_services` round-trips the registered tuple; an
      App with none yields `()`.

## 3. Collapse `serve_process` to one supervised engine

- [x] 3.1 Generalize `_serve_with_spoke` → `_serve(runtime, *, transport, host,
      port, uds_path: str | None, services, mcp_options)`: build the public
      listener (stdio `run_stdio_async` / http `build_parent_app(enter_runtime=
      False)`), the optional spoke listener (only when `uds_path`), and the
      service coroutines `svc(ServeContext(internal_uds=uds_path,
      transport=transport))`, then `await _supervise(...)`.
- [x] 3.2 Add `_supervise(listeners, services, *, on_teardown)` per design D3:
      `asyncio.wait(FIRST_COMPLETED)` loop; listener-exit or any-raise ends serve,
      clean service-return is a non-event; `finally` cancels + drains pending and
      runs `on_teardown` (`_cleanup_uds` when a spoke is present). **Not**
      `TaskGroup`, **not** a flat gather.
- [x] 3.3 Rewrite `serve_process` to compose args and `asyncio.run(_serve(...))`
      for every case. **Delete** the two bare `internal_uds is None` branches
      (no shim — AGENTS.md §1). `services = runtime.serve_services`.

## 4. Tests — behavior + supervisor edges

- [x] 4.1 CLI verb (`--help`, a real verb) → zero services invoked.
- [x] 4.2 `serve --internal-uds PATH` → a registered service runs with
      `ctx.internal_uds == PATH`; `serve` without the flag → service runs with
      `ctx.internal_uds is None`.
- [x] 4.3 Service + listeners resolve through the same entered runtime /
      `SINGLETON` (no second runtime entered).
- [x] 4.4 **Supervisor edge — clean return:** a service that returns immediately
      does NOT stop serve (listeners keep serving).
- [x] 4.5 **Supervisor edge — crash:** a service that raises tears serve down
      (listeners cancelled, run exits nonzero).
- [x] 4.6 **Supervisor edge — forever loop:** a `while True` service is cancelled
      on listener stop and serve does not hang.
- [x] 4.7 Rewrite/refresh the affected suites: `tests/packages/test_serve.py`,
      `tests/packages/test_spoke.py`,
      `tests/capabilities/serve_topology/test_internal_spoke.py` (the spoke path
      is now a special case of the one engine).

## 5. Verification gate (must run, not read)

- [x] 5.1 Smoke-test the collapsed pure path: plain `serve` (stdio, no spoke, no
      services) now via `asyncio.run` + `own_app_lifecycle=False` — one MCP
      `initialize` / `tools/list` round-trip, confirming `anyio`-on-`asyncio.run`
      + banner/EOF behavior match the old `.run("stdio")`. Repeat for http
      (one request to the multiplex).

## 6. Docs + gates

- [x] 6.1 ADR 0030 (`docs/adr/0030-on-serve-services.md`) recording: the
      serve-services primitive, the collapse-to-one-engine reform, and the
      `asyncio.wait(FIRST_COMPLETED)`-not-`TaskGroup` supervisor decision.
      Extends ADR 0004 (new Tier-1 export `ServeContext`); lineage from ADR 0029.
      Run `make adr-index`.
- [x] 6.2 Constitution Phase A: human confirms (substrate surface change).
- [x] 6.3 a2kit lint / `ty check src/` / `a2kit lint static` / full suite green.
- [ ] 6.4 Release (manual: bump pyproject + CHANGELOG header + tag + push);
      a2kay bumps its a2kit pin and lands `a2kay-job-scheduler`.
