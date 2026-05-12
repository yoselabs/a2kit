# a2kit Operational Contracts

Documented behaviors for the runtime concerns consumers need to reason about
in production: cancellation, timeouts, multi-App, error handling, dev workflow,
and streaming. Each section answers one of the open questions raised in
a2web's feedback (round 1, items Q1–Q6).

## Q1. Cancellation propagation

**Current behavior.** `asyncio.CancelledError` flows through the dispatcher
unchanged. Transport disconnect (MCP) and SIGINT (CLI) cancel the running task;
the cancellation propagates to the tool body at its next `await`.

**Tool author's responsibility.** Tool bodies MUST handle `CancelledError`
cleanly — typically via `try / finally` for resource cleanup. a2kit does not
catch the exception and does not run any cleanup hooks for you. Examples of
resources that need explicit close on cancel:

- Browser pages (Playwright, Camoufox) — close in `finally`.
- Hedged request groups (anyio.create_task_group) — `CancelledError`
  cancels the group cleanly; user code typically needs nothing extra.
- Sockets, file handles — context-manager forms (`async with`) handle this
  for free.

**Future plans.** None. The current "bubble unchanged" contract is the right
default — wrapping cancellation in framework-level "cleanup hooks" would hide
the failure mode from authors.

**Regression test.** `tests/test_cancellation.py` — a tool body with a
`try/finally` is invoked through the in-process test client; the wrapping task
is cancelled mid-await; the test asserts the `finally` block ran and
`CancelledError` reached the dispatcher.

## Q2. Per-tool timeouts

**Current behavior.** No built-in timeout flag on `@a2kit.read` / `@a2kit.write`.
Tools cooperate with structured concurrency directly.

**Why no built-in.** A decorator-level timeout suggests every tool has one
budget; in practice the right number depends on the stage. Network ≠ extraction
≠ format-routing. A blanket `@a2kit.read(timeout=60)` would either kill
post-network processing or force authors to inflate the budget. Per-region
`anyio.fail_after` is the honest tool.

### Prescribed patterns

**Single-budget network call** — the common case:

```python
import anyio

@a2kit.read()
async def fetch(*, url: str) -> FetchResponse:
    async with anyio.fail_after(60):
        return await fetcher.fetch(url)
```

**Multi-stage with nested budgets** — overall cap + per-stage sub-budget:

```python
@a2kit.read()
async def fetch(*, url: str) -> FetchResponse:
    async with anyio.fail_after(60):              # overall cap
        async with anyio.fail_after(10):
            conn = await pool.acquire(url)         # connect budget
        async with anyio.fail_after(30):
            raw = await conn.read_all()            # read budget
    return extract_markdown(raw)                  # not under the cap
```

The outer `fail_after` guarantees the tool returns within 60s. The inner
budgets carve that up; if either fires, the outer hasn't yet, and the
caller sees a single `TimeoutError`.

**Silent degrade** — when a missing budget is recoverable:

```python
@a2kit.read()
async def fetch_with_cache(*, url: str) -> FetchResponse:
    cache_hit: FetchResponse | None = None
    async with anyio.move_on_after(2.0):           # no raise on timeout
        cache_hit = await cache.get(url)
    if cache_hit is not None:
        return cache_hit
    async with anyio.fail_after(60):
        return await fetcher.fetch(url)
```

`move_on_after` exits the block silently when its budget fires — useful
for "best effort" stages where a slow path should fall through to the
next strategy rather than crash.

**Cleanup on timeout** — interaction with Q1:

```python
@a2kit.read()
async def fetch(*, url: str) -> FetchResponse:
    handle = await pool.acquire()
    try:
        async with anyio.fail_after(30):
            return await fetcher.fetch(url, handle)
    finally:
        await pool.release(handle)                 # always runs, even on TimeoutError
```

`TimeoutError` propagates like any other exception; `try/finally` is the
canonical cleanup mechanism per Q1's cancellation contract.

**Future plans.** None planned. The `fail_after` idiom is more expressive
than a decorator kwarg can be; if a strong consumer ask emerges for
advertising the budget in MCP annotations, that becomes a separate concern
(metadata, not enforcement).

## Q3. Multi-App in production

**Current behavior.** Each `a2kit.App` instance has fully isolated state:

- Singleton cache (`app._singletons`) — per-App.
- Lifecycle handlers (`@app.on_startup` / `@app.on_shutdown`) — fire per-App.
- Dispatch hook (`app._dispatch_hook`) — per-App; built lazily on first
  `provide(...)`.
- LDD state (events/reports kill-switches) — per-App.
- Health registry (`app._health`) — per-App.
- Typed event registry (`app.ldd.events`) — per-App.

Production-supported. Two App instances in one process do not share state.
The MCP server build (`build_mcp_server(app)`) is App-scoped; you can run two
FastMCP servers from one process if you really want to.

**Tool author's responsibility.** Don't reach across App boundaries inside a
tool body. Pass dependencies through DI (`provide`/`singleton`) so tools see
the right App's instances.

**Future plans.** None. Multi-App composition (one process aggregating tools
from several apps under a meta-MCP) is a possible future direction but not
in the current scope.

**Regression test.** `tests/test_multi_app_isolation.py` — two `App`
instances each with their own singleton factory + lifecycle handlers; the
test asserts `peek` returns distinct instances and lifecycle hooks fire
per-App with no crossover.

## Q4. Dev-mode auto-reload

**Current behavior.** Not a framework concern. `a2kit.run(app)` runs the CLI
or MCP server once per process.

**Tool author's responsibility.** Use external tools for the
edit-save-restart loop:

- `watchexec --restart -- python -m my_app.server serve` — file-change
  restart for MCP servers.
- `entr` — minimal alternative.
- Process managers: `honcho`, `procfile-style` runners, etc.

**Future plans.** None. Auto-reload is a tooling concern that varies wildly
by transport (HTTP frameworks like FastAPI handle this differently than MCP
servers); a2kit shouldn't pick a single answer.

## Q5. Error envelope for unhandled tool exceptions

**Current behavior.** Unhandled exceptions in tool bodies bubble to the
dispatcher.

- **MCP path.** FastMCP wraps the exception as a `ToolError` on the wire.
  By default (`App(debug=False)`) a2kit passes `mask_error_details=True` to
  FastMCP, so the wire message is a generic `f"Error calling tool {name!r}"`
  with no detail. With `App(debug=True)`, a2kit passes
  `mask_error_details=False` AND wraps every tool with a debug helper that
  appends the full traceback to the exception's `str()`. FastMCP's
  unmasked path then emits `f"Error calling tool {name!r}: {message}"`
  where `message` includes the traceback. Use `debug=True` only in
  development — tracebacks expose internal paths.
- **CLI path.** The process exits with a non-zero status code; the error
  message goes to stderr as ``error: <message>``. When `App(debug=True)`,
  the full traceback follows the error line on stderr; otherwise only the
  one-line message appears.

`asyncio.CancelledError` is treated specially (see Q1) — it bubbles unchanged
without being wrapped in an envelope, since cancellation is not an error.

**Tool author's responsibility.** Either:

- Catch domain-level failures inside the tool and return a structured
  response (e.g. `FetchResponse(status="failed", reason=...)`). This is
  the recommended pattern for predictable failure modes.
- Let unexpected exceptions bubble — they'll surface as JSON-RPC errors /
  CLI tracebacks with no extra work.

**Future plans.** None for the envelope shape. The `debug=True` traceback
toggle is the relevant lever; `App(debug=True)` is the documented contract.
A structured `data.traceback` field (rather than message-embedded text) would
require sub-classing `ToolError` upstream in FastMCP — deferred.

**Regression test.** `tests/test_error_envelope.py` — covers the in-process
client raising path (dispatcher does not swallow), and the `debug` flag's
effect on the wire output.

## Q6. Streaming output for large responses + visibility during long phases

**Current behavior.** Tool returns are atomic. The dispatcher receives the
full return value, formats it, and emits one response. There is no
chunked-output API.

**Workaround for mid-flight visibility — heartbeat events.** When a tool
has a long-running phase (slow network tier, browser render, batch
extract) and a caller needs to see *where* it is — especially before a
timeout fires — emit periodic heartbeat events from inside the phase:

```python
from dataclasses import dataclass
import anyio

@dataclass
class TierHeartbeat:
    step: str
    elapsed_s: float
    status: str

# At router setup:
app.ldd.events.register(TierHeartbeat)

@router.read()
async def fetch(*, url: str, ctx: a2kit.ToolContext) -> FetchResponse:
    async with anyio.create_task_group() as tg:
        tg.start_soon(_heartbeat_loop, ctx, "browser")
        async with anyio.fail_after(60):
            return await browser_fetch(url)

async def _heartbeat_loop(ctx, step: str) -> None:
    start = anyio.current_time()
    while True:
        await anyio.sleep(5)
        await app.ldd.events.emit_typed(
            ctx,
            TierHeartbeat(step=step, elapsed_s=anyio.current_time() - start, status="…")
        )
```

If the `fail_after` fires at 60s, the caller (and any attached sinks) has
seen 11 heartbeats and knows the tool died in the `browser` phase, not
the extraction that comes after.

**In-process observation — `app.ldd.add_sink`.** OTel exporters, Datadog
adapters, audit-log writers, and any other in-process consumer that wants
to observe every emission (events and reports, on every transport)
register an async sink:

```python
from a2kit.ldd import LddEmission

async def otel_sink(emission: LddEmission) -> None:
    span = tracer.start_span(f"a2kit.{emission.name}")
    try:
        span.set_attribute("kind", emission.kind)
        span.set_attribute("elapsed_ms", emission.elapsed_ms)
        if emission.tool_name:
            span.set_attribute("tool", emission.tool_name)
        for k, v in emission.payload.items():
            span.set_attribute(k, v)
    finally:
        span.end()

app.ldd.add_sink(otel_sink)
```

Sinks receive every LDD emission after the wire emit (CLI stderr or MCP
notification). Fan-out is sequential and best-effort: a sink exception
is caught and logged on `a2kit.ldd.sinks`, never breaking tool dispatch.

**Cancellation contract.** When the surrounding `anyio.fail_after`
expires (or the tool is otherwise cancelled), every emission that
**completed** before cancellation arrived has landed — on the wire and
on every sink that already ran. An emission in flight at the moment of
cancellation may be dropped at the sink that was mid-await (and any
sinks queued after it in the fan-out). This is intentional: sinks
shouldn't block tool cancellation. For guaranteed delivery, write
synchronous-fast sinks that push to a queue and process out-of-band;
use `app.on_shutdown` to flush at shutdown.

See `docs/SPIKE_LDD_CANCELLATION.md` for the spike that established
this contract.

**Future plans.** Streaming output (e.g. `AsyncIterator[Chunk]` returns
translating to MCP chunked notifications) is **deferred**. It would
require material design work on the dispatcher (return-type detection,
chunk serialization, backpressure) and on the MCP transport layer.
For visibility-during-execution use cases, the heartbeat + add_sink
pattern above is the canonical answer.

## Q7. The `_meta.*` tool namespace

The `_meta.*` tool-name prefix is **closed** — reserved for
framework-internal protocol tools (currently `_meta.health`,
registered via `App(name, health_tool=True)`). User-registered
tools with this prefix are rejected, both at decoration time
(`@a2kit.read(name="_meta.foo")`) and at server-build time
(metadata-mutation paths); the error names the reserved namespace.

The namespace is split deliberately across transports:

- **MCP transport.** `_meta.*` tools are excluded from default
  `list_tools` AND not callable via `call_tool`. FastMCP 3's
  visibility transform (`server.disable(tags={"_meta"})`) hides
  them on both axes. Agent-facing clients see a clean tool
  surface and cannot accidentally invoke diagnostic tools.
- **CLI transport.** `_meta.*` tools surface under a `_meta`
  subcommand group in `<app> --help` and are callable
  (`<app> _meta health`, or the shorthand `<app> health`).
  The CLI runner iterates `app.tools()` directly and never
  consults the MCP visibility filter, so this is the supported
  surface for human operators driving health checks and
  diagnostics.

To extend the framework's `_meta.*` surface, add the tool name
to `_BUILTIN_RESERVED_TOOL_NAMES` in `src/a2kit/tool.py` and
register it through an internal builder (see
`packages/health/` for the pattern).

## See also

- `CHANGELOG.md` — release-by-release history of behavioral changes.
- `ANTIPATTERNS.md` — patterns that fail at decoration / lint time.
- `examples/streaming_logger/` — LDD primitives in action.
- `examples/elicitation/` — `await ctx.elicit(...)` portability between
  CLI (stdin) and MCP (client elicitation handler).
- `examples/sampling/` — `await ctx.sample(...)` works on MCP, raises
  `MCPOnlyError` on CLI.
