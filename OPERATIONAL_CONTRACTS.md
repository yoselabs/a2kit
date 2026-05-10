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

**Tool author's responsibility.** Use `anyio.fail_after(seconds)` inside the
tool body for per-call budgets, or scope at the resource layer (e.g. a sqlite
client with its own statement timeout).

```python
import anyio

@a2kit.read()
async def fetch(*, url: str) -> FetchResponse:
    async with anyio.fail_after(60):
        return await fetcher.fetch(url)
```

**Why no built-in.** A framework-level timeout flag suggests every tool has
one budget; in practice the right number depends on the tier (browser tier
vs cache lookup vs DNS). Per-tool flags would force authors to pick a
worst-case number; per-call `fail_after` is more honest.

**Future plans.** None planned. If a strong consumer ask emerges, the
mechanism would be a `@a2kit.read(timeout=...)` kwarg that wraps the body
in `anyio.fail_after` — straightforward to add.

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

- **MCP path.** The exception becomes a JSON-RPC error response. `code`
  follows MCP/JSON-RPC convention (`-32603` for internal errors); `message`
  is `str(exception)`. When `App(..., debug=True)` is set, the response's
  `data.traceback` field carries the full Python traceback string for
  diagnosis. In production (`debug=False`, the default) tracebacks are
  not included.
- **CLI path.** The process exits with a non-zero status code; the
  traceback is printed to stderr. The exception is not caught.

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

**Regression test.** `tests/test_error_envelope.py` — covers the in-process
client raising path (dispatcher does not swallow), and the `debug` flag's
effect on the wire output.

## Q6. Streaming output for large responses

**Current behavior.** Tool returns are atomic. The dispatcher receives the
full return value, formats it, and emits one response. There is no
chunked-output API.

**Workaround.** Mid-flight communication uses LDD primitives:

- `await event(ctx, "name", **payload)` — narrative events.
- `await report(ctx, payload)` — typed result chunks (declared via
  `@reports(T)`).
- `await ctx.report_progress(current, total)` — numeric progress.

Tools with large content (>100KB) typically still return a single payload;
agents and humans see the LDD stream during execution and the full result
at the end.

**Future plans.** Streaming output (e.g. `AsyncIterator[Chunk]` returns
translating to MCP chunked notifications) is **deferred**. It would require
material design work on the dispatcher (return-type detection, chunk
serialization, backpressure) and on the MCP transport layer. Track via a
future change proposal once a consumer has a concrete need.

## See also

- `CHANGELOG.md` — release-by-release history of behavioral changes.
- `ANTIPATTERNS.md` — patterns that fail at decoration / lint time.
- `examples/streaming_logger/` — LDD primitives in action.
- `examples/elicitation/` — `await ctx.elicit(...)` portability between
  CLI (stdin) and MCP (client elicitation handler).
- `examples/sampling/` — `await ctx.sample(...)` works on MCP, raises
  `MCPOnlyError` on CLI.
