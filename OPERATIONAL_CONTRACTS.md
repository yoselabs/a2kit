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

**Current behavior.** Two complementary mechanisms:

1. **Built-in decorator kwarg** (`dispatcher-timeout-decorator`):
   `@a2kit.read(timeout=...)` accepts a number (seconds) or string with
   unit suffix (`"60s"`, `"2m"`, `"500ms"`). When set, the dispatcher
   wraps the tool body in `anyio.fail_after` at the innermost layer of
   the wrapper chain — inside the LDD scope and dispatch-hook DI, so
   neither counts against the budget. The same wrap fires on both MCP
   and CLI transports for transport parity. On timeout, Python's
   built-in `TimeoutError` is raised; the MCP envelope serializes it as
   `{"class": "TimeoutError", "message": ...}`. Use this when the tool
   has a single uniform timeout that callers should advertise to agents
   via `tool.meta.extras.timeout_seconds`.

2. **Per-region `anyio.fail_after`** inside the tool body. Use when the
   tool's stages need different budgets (network vs extraction vs
   format-routing) or when partial-failure modes (e.g.
   `anyio.move_on_after` for cache lookups) are part of the contract.

**Why both.** A decorator-level timeout suggests every tool has one
budget; in practice the right number sometimes depends on the stage.
Network ≠ extraction ≠ format-routing. For tools with a single budget
that callers should see, the decorator is the right knob (and surfaces
in `tool.meta` so agents can plan retries). For tools with stage-shaped
budgets or recoverable partial-timeouts, per-region `anyio.fail_after`
remains the honest tool. The two compose: a decorator-level overall
cap + inner per-region `fail_after` budgets that carve it up.

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

**Policy.** a2kit guarantees that any uncaught exception raised by a tool
body or its wrapper chain reaches the MCP wire as `isError: true` with a
JSON-encoded text payload of shape
`{"class": "<ExceptionClassName>", "message": "<str(exc)>"}`. When
`App(debug=True)`, the payload additionally includes
`"traceback": "<rendered traceback>"`. The contract is enforced by a2kit's
outermost tool wrapper (`_wrap_with_error_envelope` in
`packages/mcp/server.py`) which catches `Exception` and re-raises
`ToolError(json.dumps(payload))`. FastMCP's tool-dispatch path re-raises
`FastMCPError` subclasses (incl. `ToolError`) unchanged before any
masking — so the JSON payload reaches the wire verbatim regardless of
FastMCP's `mask_error_details` flag. a2kit treats `mask_error_details`
as an internal implementation detail subject to upstream change; the
envelope shape is owned here.

**Unwrapped propagation.** The envelope does NOT wrap:

- `fastmcp.exceptions.FastMCPError` (incl. author-raised `ToolError`) —
  passes through unchanged so author-shaped messages reach the wire on
  FastMCP's own path. Double-wrapping would corrupt the author's message.
- `asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit` —
  `BaseException` siblings, naturally outside `except Exception`.
- `BaseExceptionGroup` containing only `CancelledError`s — anyio
  task-group cancellation per Q1.

**CLI path.** Unchanged from prior behavior. The process exits with a
non-zero status code; the error message goes to stderr as
`error: <message>`. When `App(debug=True)`, the full traceback follows
the error line on stderr; otherwise only the one-line message appears.
The structured-envelope guarantee is an MCP-transport contract only.

**Tool author's responsibility.** Either:

- Catch domain-level failures inside the tool and return a structured
  response (e.g. `FetchResponse(status="failed", reason=...)`). This is
  the recommended pattern for predictable failure modes.
- Let unexpected exceptions bubble — they'll surface on the MCP wire as
  the structured envelope `{class, message, [traceback]}` and on the
  CLI side as `error: <message>` + traceback under `debug=True`.

**Why owned by a2kit, not delegated.** The pre-v0.33 implementation
relied on FastMCP's `mask_error_details` semantics to surface the
exception message. Those semantics have shifted across FastMCP minor
versions and as of v0.32 collapsed unmasked responses to the bare
string `"Error calling tool 'X'"` regardless of `mask_error_details`,
leaving downstream consumers with no diagnostic signal. The envelope
wrapper bypasses the masking path entirely.

**Regression test.** `tests/test_wire_error_envelope.py` — covers the
`{class, message}` shape under `debug=False`, the `traceback` field
addition under `debug=True`, author-raised `ToolError` passthrough,
`CancelledError` propagation, special-character round-trip, and the
FastMCP-independence assertion (same payload shape regardless of
`mask_error_details`).

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

## Q8. LDD primitives require an active tool dispatch

`a2kit.ldd.event`, `report`, `log`, and the `info` / `warning` /
`error` / `debug` shorthands (plus `EventRegistry.emit_typed`) read
their `ctx` from an ambient `ContextVar` set by the dispatcher for the
duration of one tool invocation. They take NO `ctx` argument.

"Active dispatch" is the conjunction of two conditions: a tool body
is currently running under an `ldd_state_for_call(ctx=...)` scope
**and** the tool declared a `ctx: ToolContext` parameter that the
dispatcher bound. Either missing — calling from module-level code,
`@on_startup`, `@on_shutdown`, any other pre-dispatch context, or
from inside a tool that omitted its `ctx` declaration — raises
`a2kit.exceptions.AmbientContextMissing`.

Lazy singleton factories instantiated **during** a dispatch are
reachable from the active scope and may call LDD primitives. The
ContextVar is set before the dispatcher resolves DI kwargs, so a
factory whose first resolution happens on a tool's call inherits the
ambient ctx:

```python
async def make_pool() -> Pool:
    await a2kit.ldd.info("opening pool")  # legal: dispatch in flight
    return Pool(...)

app.singleton(Pool, make_pool)
```

What's still illegal is the same factory invoked from `@on_startup`
(pre-dispatch) or from a warm-up script (no dispatch in flight at all). The shorthands surface
their own name (`a2kit.ldd.info`, `…warning`, `…error`, `…debug`)
in the error so the trace points at the actual call site rather than
the delegated-to `a2kit.ldd.log`. The error names the primitive and
points at the test seam. **There is no silent no-op fallback**; fail
loud, fix the call site.

The failure mode is uniform across all three transports (MCP / CLI /
TestClient): none of them synthesize a fake context when the tool
omits `ctx`. A no-ctx tool that calls `await a2kit.ldd.event(...)`
raises identically on every dispatcher.

Tests that want to exercise LDD primitives directly (without a full
tool dispatch) wrap with the `ldd_state_for_call(ctx=stub, ...)`
context manager — same seam the framework uses internally.

`asyncio.gather`, `create_task`, and `TaskGroup` propagate the
ambient ctx via Python's `contextvars` copy-on-task semantics, so
sub-coroutines and background tasks spawned from a tool body inherit
the binding automatically. Background tasks outliving the outer
dispatch keep their captured snapshot until they themselves complete.

## Q9. Framework-internal introspection failures are observable, not silent

**Policy.** Any introspection performed by a2kit itself during tool
decoration or middleware dispatch (`typing.get_type_hints`,
return-annotation copy, FastMCP `server.get_tool` metadata lookup,
list-view payload projection / reconstruction, OTel span-metadata lookup)
SHALL emit one WARN-level log line per offender per process on failure
and proceed with the documented fallback for that site. Bare
`contextlib.suppress(Exception)` and `except Exception: pass` (or
equivalent `except Exception: return <fallback>` with no observability
hook) SHALL NOT be used on any code path reachable from tool decoration
or middleware dispatch.

**Dedupe key.**

- Decoration-time sites operating on a callable: `fn.__qualname__`.
- Middleware sites operating on a registered tool: the FastMCP
  `tool_name` string. When a single module has more than one distinct
  failure site naturally keyed by `tool_name`, the dedupe key is
  composed as `f"{tool_name}::{site_tag}"` (e.g.
  `f"{tool_name}::get_tool"` for the registry lookup site and
  `f"{tool_name}::project"` for the projection site) so a single
  module-level `_WARN_ONCE: set[str]` can hold keys for multiple sites
  without collision.

**Per-module dedupe set.** Each module owns its own `_WARN_ONCE` set at
module scope. No cross-module sharing.

**Semantic outcome unchanged.** Decoration / middleware does not raise;
the user-visible surface degrades the same way as before the policy
landed. Only the silence is replaced with one observable WARN line per
offender per process.

**Sites covered today** (in commit order):

- `src/a2kit/signature.py:resolve_hints` — five-call collapse for the
  `get_type_hints` fast path (cleanup-round-5-6-code-shape, reference
  implementation).
- `src/a2kit/packages/mcp/server.py:_wrap_with_dispatch_hook` —
  return-annotation copy onto the dispatch-hook wrapper (L1).
- `src/a2kit/tool.py:_resolve_return_annotation` — return-annotation
  resolution for PEP 563 stringified annotations (L2).
- `src/a2kit/tool.py:_derive_selectable_fields` — outer
  `get_type_hints(fn)` call when walking `list[T]` return annotations
  (L3).
- `src/a2kit/packages/mcp/listview.py:ListViewMiddleware.on_call_tool` —
  registry lookup (`f"{tool_name}::get_tool"`) and result
  reconstruction (`f"{tool_name}::project"`) sites (L4).
- `src/a2kit/packages/otel/middleware.py:_meta_a2kit` — span-attribute
  metadata lookup via `server.get_tool` (L5).

**Regression test.** `tests/test_decoration_warn_once.py` — one test
per site asserts (a) the documented fallback still applies on failure,
(b) exactly one WARN line is emitted per offender, (c) a second failure
for the same offender in the same process does not emit a second line.
The signature-level test lives in `tests/test_resolve_hints.py`.

## Q-Ctx. Context binding invariants

**Policy.** When a tool function declares a parameter typed
`a2kit.ToolContext` (the re-export of `fastmcp.Context`), the dispatcher
SHALL bind it on every transport. Implementations and contributors
must honor three invariants:

1. **Always bound when declared.** On MCP, FastMCP injects the live
   `Context` at call time. On CLI, the runtime synthesizes a
   `StderrToolContext` at `cli/runtime.py:49`. There is no transport
   or test path where a declared `ctx` arrives as `None`.
2. **Optional annotation forms are rejected at decoration time.** A
   tool declaring `ctx: ToolContext | None`, `ctx: Optional[ToolContext]`,
   or `ctx: Union[ToolContext, None]` raises
   `A2KitInvalidContextAnnotation` from `find_context_param`. The
   Optional form is misleading typing — there is no runtime path
   producing `None`. Migration: drop `| None` from the annotation,
   or remove the `ctx` parameter entirely if the tool does not need
   it.
3. **The MCP wrapper chain's rewritten signature MUST contain `ctx`
   when the tool declares it.** `_wrap_with_dispatch_hook` re-appends
   the original `ctx` parameter onto the rewritten signature so
   FastMCP's introspection sees it and binds the live `Context` at
   call time. A decoration-time invariant inside
   `_wrap_with_dispatch_hook` raises `A2KitContextBindingBroken` if
   this is ever violated by a future wrapper-chain change — the App
   fails to build before serving any request.

**Why this matters.** v0.32 shipped a regression where the MCP
wrapper chain dropped `ctx` from the rewritten signature, breaking
every tool that combined `state: T` DI with `ctx: ToolContext` over
the MCP transport (CLI was unaffected). The bug surfaced as
`TypeError: missing 1 required keyword-only argument: 'ctx'` masked
by FastMCP into the bare wire string `"Error calling tool 'X'"`,
with no diagnostic signal for downstream consumers. The
`A2KitContextBindingBroken` decoration-time guard prevents this
class of regression from ever reaching production again.

**Regression test.** `tests/test_transport_parity.py` exercises the
full (state-DI, ctx-DI) declaration matrix across CLI and MCP
transports. The MCP leg uses
`fastmcp.Client(transport=build_mcp_server(app))` to drive the real
production wrapper chain (the in-process test client
`a2kit.testing.client` bypasses it by design — it is a unit-test
seam for tool bodies, not a substitute for transport-parity
testing). Future wrapper-chain refactors MUST keep this file green.

An opt-in stdio JSON-RPC subprocess smoke
(`tests/test_transport_parity_stdio.py`, gated on
`A2KIT_SLOW_TESTS=1`) provides one canary case covering the wire
framing layer below the dispatcher.

**Diagnostic classes.**

- `a2kit.exceptions.A2KitContextBindingBroken` — framework-internal
  invariant; raised from `_wrap_with_dispatch_hook` at App
  construction.
- `a2kit.exceptions.A2KitInvalidContextAnnotation` — user-facing;
  raised from `find_context_param` at decoration time when the
  annotation form is Optional/Union with `None`.

## Q-Teardown. Singleton teardown contract

**Policy.** `app.singleton(T, factory, *, teardown=fn)` registers a
shutdown callback the framework invokes on App lifespan exit. The
framework owns three guarantees:

1. **Topological order — dependents before dependencies.** When
   multiple singletons have registered teardowns AND their factories
   declare each other as parameters (forming a dependency edge),
   teardowns fire in reverse-topological order. A pool whose factory
   takes a sqlite handle is closed before sqlite, regardless of
   registration order. Reverse-of-registration is *not* the contract.
2. **Error isolation.** A teardown that raises `Exception` does NOT
   prevent sibling teardowns from running. The framework catches the
   exception, appends `(type, exc)` to `App.teardown_failures`,
   emits an `error`-level log line via the `a2kit.lifecycle` logger
   with class, message, and singleton type name, and continues. The
   framework does NOT re-raise teardown failures from `lifespan_cm()`.
3. **Cycles handled deterministically.** If the singleton
   factory-parameter graph contains a cycle (which the container's
   resolution-cycle detection should prevent in practice), the
   teardown walk breaks the cycle at the lowest-`id(type)` member
   and emits a `WARN`-level log line identifying the cycle.

**Composition with user / Router lifespans.** Framework teardowns run
**after** all user and Router lifespan `finally` blocks have fully
exited. User code can still hand-roll teardowns (which run first,
inside their own scope); the framework provides the safety net for
explicitly-registered `teardown=` callbacks (which run after).

**Async teardowns.** `teardown=` may be sync (`def`) or async
(`async def`); awaitable returns are awaited. Same convention as the
dispatch hook.

**Programmatic introspection.** `App.teardown_failures` is a list of
`(type, exc)` tuples, empty on clean shutdown. Tests pin this attribute
to assert shutdown ran clean. The `a2kit.exceptions.A2KitSingletonTeardownError`
class aggregates failures for callers who want to construct an
exception object from `app.teardown_failures` themselves — the framework
never raises it.

**Why owned by the framework.** Three problems with hand-rolled
shutdown patterns (`finally: for c in reversed(closers): try: ...`):
the boilerplate scales linearly with resource count; `try/except: pass`
silently masks failures; reverse-of-registration is *incorrect* when
the DI graph diverges from registration order (pool depending on
sqlite, registered second). Framework ownership centralizes correct
ordering, error isolation, and observability.

**Regression test.** `tests/test_singleton_teardown.py` — covers
topological ordering, error isolation, async teardown, cycle handling,
and composition with user lifespans.

## See also

- `CHANGELOG.md` — release-by-release history of behavioral changes.
- `ANTIPATTERNS.md` — patterns that fail at decoration / lint time.
- `examples/streaming_logger/` — LDD primitives in action.
- `examples/elicitation/` — `await ctx.elicit(...)` portability between
  CLI (stdin) and MCP (client elicitation handler).
- `examples/sampling/` — `await ctx.sample(...)` works on MCP, raises
  `MCPOnlyError` on CLI.
