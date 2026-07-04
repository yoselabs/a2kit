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
   the wrapper chain — inside the log scope and dispatch-hook DI, so
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

- App-scope DI instances (registered via `app.provide(T, factory)`) —
  cached per-App on that App's container.
- Resource lifecycle (`__aenter__` / `__aexit__` on app-scope
  instances) — entered and unwound per-App.
- Dispatch hook (`app._dispatch_hook`) — per-App; built lazily on first
  `provide(...)`.
- Health registry (`app._health`) — per-App.

Production-supported. Two App instances in one process do not share state.
The MCP server build (`build_mcp_server(app)`) is App-scoped; you can run two
FastMCP servers from one process if you really want to.

**Tool author's responsibility.** Don't reach across App boundaries inside a
tool body. Pass dependencies through DI (`app.provide(T, factory)`) so tools
see the right App's instances.

**Future plans.** None. Multi-App composition (one process aggregating tools
from several apps under a meta-MCP) is a possible future direction but not
in the current scope.

**Regression test.** `tests/test_multi_app_isolation.py` — two `App`
instances each with their own app-scope DI registration; the test asserts
each App resolves distinct instances with no crossover.

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
`app.config.debug` resolves `True` (env `A2KIT_DEBUG=true` or
`A2kitConfig(debug=True)` per ADR 0022), the payload additionally includes
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
`error: <message>`. When `app.config.debug` resolves `True`, the full traceback follows
the error line on stderr; otherwise only the one-line message appears.
The structured-envelope guarantee is an MCP-transport contract only.

**Tool author's responsibility.** Either:

- Catch domain-level failures inside the tool and return a structured
  response (e.g. `FetchResponse(status="failed", reason=...)`). This is
  the recommended pattern for predictable failure modes.
- Let unexpected exceptions bubble — they'll surface on the MCP wire as
  the structured envelope `{class, message, [traceback]}` and on the
  CLI side as `error: <message>` + traceback when `A2KIT_DEBUG=true`.

**Why owned by a2kit, not delegated.** The pre-v0.33 implementation
relied on FastMCP's `mask_error_details` semantics to surface the
exception message. Those semantics have shifted across FastMCP minor
versions and as of v0.32 collapsed unmasked responses to the bare
string `"Error calling tool 'X'"` regardless of `mask_error_details`,
leaving downstream consumers with no diagnostic signal. The envelope
wrapper bypasses the masking path entirely.

**Regression test.** `tests/test_wire_error_envelope.py` — covers the
`{class, message}` shape when debug is off, the `traceback` field
addition when debug is on, author-raised `ToolError` passthrough,
`CancelledError` propagation, special-character round-trip, and the
FastMCP-independence assertion (same payload shape regardless of
`mask_error_details`).

## Q6. Streaming output for large responses + visibility during long phases

**Current behavior.** Tool returns are atomic. The dispatcher receives the
full return value, formats it, and emits one response. There is no
chunked-output API.

**Workaround for mid-flight visibility — heartbeats.** When a tool has a
long-running phase (slow network tier, browser render, batch extract) and
a caller needs to see *where* it is — especially before a timeout fires —
emit periodic heartbeats from inside the phase. A heartbeat is a typed
instance passed to a level method; it streams to the wire as it is logged:

```python
from dataclasses import dataclass
import anyio
import a2kit

@dataclass
class TierHeartbeat:
    step: str
    elapsed_s: float
    status: str

@router.read()
async def fetch(*, url: str, ctx: a2kit.ToolContext) -> FetchResponse:
    async with anyio.create_task_group() as tg:
        tg.start_soon(_heartbeat_loop, "browser")
        async with anyio.fail_after(60):
            return await browser_fetch(url)

async def _heartbeat_loop(step: str) -> None:
    start = anyio.current_time()
    while True:
        await anyio.sleep(5)
        await a2kit.log.info(
            TierHeartbeat(step=step, elapsed_s=anyio.current_time() - start, status="…")
        )
```

If the `fail_after` fires at 60s, the caller has seen 11 heartbeats and
knows the tool died in the `browser` phase, not the extraction that comes
after. The heartbeat loop reads `ctx` from the ambient dispatch scope, so
it takes no `ctx` argument (see Q8).

**In-process observation — stdlib logging handlers.** Emissions are stdlib
`logging` records on the `a2kit` logger. Any in-process consumer (OTel
exporter, Datadog adapter, audit writer) observes them by attaching a
standard `logging.Handler`:

```python
import logging

logging.getLogger("a2kit").addHandler(my_handler)
```

For a durable, queryable record of every call's I/O (args, result, timing,
principal, plus any `debug`-logged bodies), enable the call-log
(`A2KIT_LOG__CALL_LOG`): it writes JSONL on the dedicated, non-streaming
`a2kit.calls` logger, structurally separate from the wire. See the
`call-log` and `log-handlers` capabilities.

**Cancellation contract.** When the surrounding `anyio.fail_after` expires
(or the tool is otherwise cancelled), every emission that **completed**
before cancellation arrived has landed — on the wire and on every attached
handler. An emission in flight at the moment of cancellation may be
dropped. This is intentional: logging must not block tool cancellation. For
guaranteed delivery, write a fast handler that enqueues and processes
out-of-band, and flush it from a resource's `__aexit__` (the per-scope
cleanup stack runs on dispatch / App teardown).

See `docs/SPIKE_LOG_CANCELLATION.md` for the spike that established
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
registered via the `@app.health_check` decorator). User-registered
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

**Liveness vs readiness.** `_meta.health` (above) is **readiness** —
opt-in, aggregates `@app.health_check` results, can report
`degraded`, and is reached over an MCP session / `POST
/api/_meta.health` / the CLI. Distinct from it, every HTTP serve
(`serve --transport=http`, MCP-only included) also exposes a
**liveness** route: a static `GET /health → 200 {"status": "ok"}` on
the multiplex parent (`packages/serve.py`). It is deliberately dumb —
resolves no DI, aggregates no surface health, needs no credentials
(it sits above the surface mounts, outside any auth middleware) — so a
Docker `HEALTHCHECK` / k8s liveness probe can `curl -f` it and a
wedged DI graph still answers. The FastAPI sub-app's `/api/health`
stays for REST deployments. Readiness answers "is the work healthy";
liveness answers "is the process alive and routing".

## Q8. Log primitives require an active tool dispatch

The `a2kit.log.info` / `warning` / `error` / `debug` level methods read
their `ctx` from an ambient `ContextVar` set by the dispatcher for the
duration of one tool invocation. They take NO `ctx` argument.

"Active dispatch" means: a tool body (or any helper / phase function
it transitively calls) is currently running under a
`bind_call_scope(ctx=...)` scope that the framework opened around
the dispatch. The dispatcher synthesizes a non-None ambient `ctx` for
**every** framework-dispatched tool, regardless of whether the tool's
body declares `ctx: ToolContext` in its signature. Calling the emission
primitives from module-level code, a warm-up script, or any other
pre-dispatch context raises
`a2kit.packages.context.request_scope.RequestScopeMissing` (a
`LookupError`). Calling from inside a tool that omitted its `ctx`
declaration **does not raise** — the framework's synthesized ambient ctx
handles it (relax-log-ambient-requirement, 2026-05-15).

The raise also fires for external misuse, e.g. manually constructing
`bind_call_scope(ctx=None)` and then calling a log primitive — that's
documented misuse, not a normal path.

Lazy singleton factories instantiated **during** a dispatch are
reachable from the active scope and may call log primitives. The
ContextVar is set before the dispatcher resolves DI kwargs, so a
factory whose first resolution happens on a tool's call inherits the
ambient ctx:

```python
async def make_pool() -> Pool:
    await a2kit.log.info("opening pool")  # legal: dispatch in flight
    return Pool(...)

app.provide(Pool, make_pool)
```

What's still illegal is the same factory invoked from module-level
code or a warm-up script (no dispatch in flight at all). The level
methods surface their own name (`a2kit.log.info`, `…warning`,
`…error`, `…debug`) in the error so the trace points at the actual call
site. The error names the primitive and points at the test seam.
**There is no silent no-op fallback**; fail loud, fix the call site.

The "active dispatch" behavior is uniform across all three transports
(MCP / CLI / TestClient): all of them synthesize a non-None ambient
ctx for every dispatched tool, so a no-ctx tool that calls
`await a2kit.log.info(...)` succeeds identically on every
dispatcher. The wire-side emission goes through whichever concrete
context the active transport provided (real `fastmcp.Context` for
MCP / TestClient, `StderrToolContext` for CLI); the handler-side
emission fires unconditionally inside any dispatch.

Tests that want to exercise log primitives directly (without a full
tool dispatch) have two paths:

1. **Wrap explicitly with `bind_call_scope(ctx=stub, ...)`** — same
   seam the framework uses internally. Fine for one-off tests that
   want bespoke flag combinations.
2. **Use one of the `a2kit.testing` ambient fixtures** — the 95%
   case. Both wrap the test in an log ambient with
   `ctx=null_context()`, `events_enabled=False`,
   `reports_enabled=False`. Decision rule:
   - **`ambient_for_tests`** — per-test opt-in. Declare it as a
     fixture parameter on tests that want ambient. Some tests in
     the same module can bind, others stay loud.
   - **`ambient_for_tests_autouse`** — project-wide binding. Import
     once in `conftest.py` and every test in scope binds ambient
     without declaring a fixture parameter. Pre-decorated peer of
     the bare fixture; behaviour identical.

   The historical `__wrapped__` re-export pattern (consumer's own
   `conftest.py` calling `pytest.fixture(autouse=True)(_a.__wrapped__)`)
   still works and remains valid for code already using it. New
   consumers should pick one of the two named fixtures above.

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

**Policy.** `a2kit.ToolContext` names the cross-transport ctx contract
as an `@runtime_checkable typing.Protocol` (in `a2kit._context_protocol`).
Concrete implementations satisfy it structurally: `fastmcp.Context` under
MCP, `StderrToolContext` under CLI. When a tool declares a parameter typed
`a2kit.ToolContext`, the dispatcher SHALL bind it on every transport.
Four invariants:

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
4. **Pydantic-friendly annotations.** The rewritten signature swaps
   `a2kit.ToolContext` for `fastmcp.Context` so FastMCP/pydantic
   schema generation has a concrete class to work with (Protocols
   cannot be schema-generated). `_install_rewritten_signature` syncs
   `__annotations__` with the rewritten params; the thin
   `_ctx_annotation_passthrough` wrapper handles the no-DI early-exit
   case. Tools needing MCP-only methods (`sample`, `list_resources`)
   annotate `ctx: fastmcp.Context` directly and pay the import cost
   themselves — they are in MCP territory anyway.

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

## Q-DI. Scoped DI lifecycle contract (v0.36)

**Policy.** `app.provide(T, factory, *, per_call=False)` is the single
registration API. Two scopes are recognized:

- **App-scope (default, `per_call=False`)** — one instance per App,
  cached on the root container. Enters lazily on first
  `Container.get(T)` (i.e. first dispatch that needs it). Unwinds
  on `async with app:` exit.
- **Per-call (`per_call=True`)** — fresh instance per dispatch,
  cached within that call's child container. Unwinds when the call
  returns or raises.

The framework owns five guarantees:

1. **Lazy first-use.** `async with app:` does NOT enter resources
   eagerly. The container's `__aenter__` runs the scope-graph
   validation and seals registration; resources warm at first
   `Container.get(T)`. Concurrent first-touches coalesce on a
   per-type `asyncio.Lock`; the factory is awaited at most once.
2. **LIFO cleanup with per-resource isolation.** Each scope (root
   container, child container) holds its own `CleanupStack`. Resources
   are recorded on the stack only after `__aenter__` succeeds
   (partial-entry safety). On scope exit, entries unwind in LIFO
   order; a failing `__aexit__` is logged at WARN on
   `a2kit.di.cleanup` and sibling cleanups still run. Body exception
   wins at the call site via standard async-with semantics.
3. **Single-protocol convention.** Only `__aenter__`/`__aexit__` is
   auto-detected. `aclose` / `close` are NOT honored — wrap such
   resources in a class with `__aenter__`/`__aexit__` or use
   `@asynccontextmanager`. Removing the multi-protocol detection
   eliminated three failure modes (sync `close` returning awaitable
   silently skipped, `aclose` on a class that also had `__aexit__`,
   etc).
4. **Scope graph validation.** App-scope factories MUST NOT depend on
   per-call types. Per-call types live for one dispatch; an app-scope
   instance would cache a stale per-call value. The framework rejects
   this at `async with app:` with a `TypeError` naming the violating
   types. Use `Lazy[T]` to defer per-call resolution into the call
   scope instead.
5. **Container sealed after enter.** `provide()` after `async with app:`
   raises `TypeError`. Test overrides land BEFORE entering the App,
   at the composition root; `provide()` is last-write-wins, so
   re-registration silently replaces the prior factory.

**Async factories.** `provide()` accepts both sync (`def`) and async
(`async def`) factories. The container awaits the result and the
returned instance's `__aenter__`. Class-as-factory introspects
`__init__` parameter annotations for chained DI.

**`Lazy[T]`** (`a2kit.packages.di.Lazy`) is
`Callable[[], Awaitable[T]]`. A parameter typed `Lazy[T]` receives a
zero-arg async closure that, when awaited, resolves `T` through the
current scope's resolver and records cleanup. Never awaited = `T` is
never built and its `__aenter__` never runs. The framework recognizes
both the alias and the raw `Callable[[], Awaitable[T]]` shape, in
**tool** parameters AND **factory** parameters — aggregates built by
a factory can carry `Lazy[T]` fields, populated via DI at construction.

Scope-graph guard: a SINGLETON factory declaring
`Lazy[per-call-T]` is rejected at `async with app:` time because
`_make_lazy_closure` captures the resolving container (root for
SINGLETON factories); a later `root.get(per-call-T)` would pin the
per-call type to root's cache for the app's lifetime. Migration: move
the inner type to app-scope, or make the outer factory per-call so
the closure captures the per-call child container.

**Per-call dispatch helper.** `Container.call_scope(fn, wire_kwargs)` is
an async context manager that opens a child resolver, resolves the
tool's params (Lazy[T]-aware), yields merged kwargs, and unwinds
per-call cleanup on exit with exception propagation through each
`__aexit__`. Both transports dispatch through it.

**`pydantic_settings.BaseSettings` auto-resolution.** A tool param
typed as a `BaseSettings` subclass auto-resolves without explicit
`provide()` registration. The container duck-types the subclass check
(no `pydantic_settings` import inside the container module) and
zero-arg-constructs at first use, picking up env values via pydantic's
standard machinery.

**Resolver protocol.** `app._resolver` is typed as the `Resolver`
protocol (`get` / `provide` / `child` / `aclose`) — consumer code
sees only the four-method surface, decoupled from the concrete
`Container`. The DI package at `src/a2kit/packages/di/` is
standalone-shippable (zero `from a2kit.*` imports outside the
package; gated by a static test).

**Regression tests.** `tests/packages/di/` covers lazy first-use,
per-call scope, `Lazy[T]` semantics, cleanup-stack LIFO + isolation +
partial-entry safety + three named upstream-bug regressions
(cpython #137517, MCP SDK #1213, trio #1243), single-protocol
convention, BaseSettings duck-typing, Resolver protocol conformance,
standalone-isolation gate, and the dispatch-helper contract.

The v0.35 `teardown=` / topological-ordering / `teardown_failures`
machinery is **retired in v0.36** — single-protocol `__aenter__`/`__aexit__`
on the resource itself + the per-scope cleanup stack subsume it.
Topological order is no longer guaranteed (insertion-order LIFO via
the stack replaces it); if a dependent needs to enter before its
dependency, declare the dependency as a constructor parameter and the
container's chain resolution enters them in dependency-first order
naturally.

## Q-HealthChecks. `@app.health_check` kwargs route through the DI resolver

**Policy.** `@app.health_check`-registered function kwargs resolve
through the same DI path as tool dispatch
(`Container.resolve_params` → `_construct` → `_enter_lifecycle`).
Resources passed as health-check kwargs are entered via `__aenter__`
on first resolution and exit follows the standard scope rules.

For singleton resources (the default for `app.provide(T, factory)`
without `per_call=True`), this means:

- **First reference anywhere in the app** — by a tool dispatch, an
  earlier health probe, anything — enters the resource exactly once.
  The instance is cached on the root container's `_singletons`.
- **Subsequent health probes** hit the cache and do NOT re-enter.
- **Exit fires at app shutdown** via `Container.aclose()`, NOT per
  probe.

For per-call resources (`per_call=True`), enter/exit fires per
health-probe invocation (each probe gets a fresh instance on the
per-call child container).

Concretely: by the time a check body runs, the resource has been
entered. Whether *this* probe did the entering or an earlier call
site did, the consumer's body sees a fully-initialised resource.

```python
@app.health_check
async def _probe(sqlite: SqliteResource) -> a2kit.HealthResult:
    # sqlite is entered. Do not call _ensure() or any other
    # consumer-internal "ready" method — the resolver already
    # entered the resource via __aenter__.
    if not await sqlite.ping():
        return a2kit.HealthResult.fail("sqlite ping failed")
    return a2kit.HealthResult.ok()
```

**What this rules out.** Calling consumer-internal helpers like
`await sqlite._ensure()` inside a health-check body to "make sure
the resource is ready" is redundant and pokes a private surface.
The framework's DI lifecycle is the public contract; rely on it.

**Why this matters for testing.** `tests/test_health_check_resource_entry.py`
pins this contract with a `SpyResource` exercising the four singleton
scenarios (first-probe-enters, second-probe-reuses, exit-at-lifespan,
shared-singleton-enters-once) plus the lower-level `run_checks(app)`
API used by the CLI `<app> health` subcommand. Any change to the
resolution path that breaks the resource-entry contract trips these
tests.

## Q-CodeMode. Code execution collapses the listed tool catalog

When an MCP server is built with code mode on — the default —
`build_mcp_server` installs the `A2kitCodeMode` transform
(`a2kit.packages.codemode`). This is a transport-surface contract,
not a dispatch-semantics change: the per-call dispatch hook,
connection resolution, and DI are untouched.

- **`list_tools` collapses.** The listed catalog becomes exactly
  `search` / `get_schema` / `execute`. Real tools are no longer
  enumerated but remain callable by name via `call_tool`.
- **The sandbox re-runs the full dispatch path.** `execute`'s
  `call_tool(name, params)` routes through `ctx.fastmcp.call_tool`,
  so a sandboxed call to a connection-scoped, DI-wired tool resolves
  its `connection` and dependencies exactly as a direct MCP call
  (proven by `docs/SPIKE_CODE_EXEC_DI.md`).
- **Capability gate.** Tools flagged `destructive` are absent from
  the sandbox catalog unless the server was built with
  `code_mode_allow_destructive=True` (operator-side; `serve
  --code-mode-allow-destructive`). `visibility != "all"` tools were
  never on the MCP surface and so are never sandbox-reachable.
- **Typed sandbox values.** A `call_tool` result crosses the monty
  boundary as a **dataclass**, not a dict — sandbox code uses attribute
  access (`page.items[0].title`). a2kit generates monty type-stubs from
  the tool descriptors and the `A2kitSandboxProvider` type-checks the
  LLM-authored code against them *before* executing it, retrying once
  via sampling on a type error. See ADR 0014.
- **Opt out.** `build_mcp_server(app, code_mode=False)` /
  `serve --code-mode-off` skips the transform; `list_tools` then
  returns the full real catalog and no `execute` tool exists.

The Monty runtime (`pydantic-monty`) is a lazy optional dependency;
`import a2kit` never loads it. See ADR 0013, ADR 0014, and
`docs/VISION.md`.

## Q-FormatRouting. The MCP surface compresses LLM-facing results

Rendering is consumer-aware (ADR 0014): the `render(value, consumer)`
seam in `a2kit.packages.formatter` serves three consumer profiles —
`llm` (compress), `code` (structured dataclasses), `machine` (plain
JSON). The consumer is fixed at `build_mcp_server` time by the
`code_mode` flag; it is never sniffed from call context.

- **MCP results format-route.** With `code_mode=False` real tools face
  the LLM: a tabular result is emitted as TSV / page-tsv in the MCP
  `content` channel, with the equivalent JSON in `structuredContent`.
  Emitting both is spec-aligned (MCP SEP-1624) — `content` is the
  token-efficient channel, `structuredContent` is delivered at zero
  model-token cost. A non-tabular result keeps JSON `content`.
- **The encoding plan is static.** `build_encoding_plan` walks each
  tool's return type once at registration; it marks a top-level
  `list` / `Page` *and* any flat-array field nested inside a
  `BaseModel` envelope as TSV-encoded. Cached on `ToolDescriptor`.
- **Code mode renders for `code`.** With `code_mode=True` real tools
  are sandbox-only — their results stay structured (uncompressed);
  only the `execute` output faces the LLM and is compressed by
  value-driven inference.
- **The CLI is unchanged** — it was already the `llm` consumer.
- **`--compact` escape hatch.** `build_mcp_server(app, compact=True)` /
  `serve --compact` drops the `structuredContent` channel entirely,
  for non-conformant MCP clients that mishandle dual channels. Leave
  it off for conformant clients.
- **The REST surface (future)** is bound to the `machine` consumer —
  plain JSON, never compressed, and never exposes code execution.

## Q-Dispatch. One dispatch pipeline, folded by both transports

Per-tool dispatch is a single ordered pipeline — `DISPATCH_PIPELINE` in
`a2kit.packages.dispatch` — that the CLI and MCP adapters both fold. It
exists because the two consumers have asymmetric constraints (the CLI is
cold-start-critical and must not import `fastmcp`; the MCP server carries
`fastmcp` by definition) yet run the same dispatch concerns. FastMCP's
own middleware is server-only, so it structurally cannot serve the CLI —
the shared concerns need a transport-neutral home.

- **The pipeline is fastmcp-free.** `a2kit.packages.dispatch` imports no
  `fastmcp` and is absent from the `A2K-IMPORT-DISCIPLINE` allowlist.
  This is the load-bearing constraint — the CLI consumer folds it.
- **Six neutral stages, innermost-first:** `timeout`, `enricher`,
  `router-lazy-enter`, `dispatch-hook` (hook + per-call DI scope),
  `log-state` (log ambient + ctx), `error-capture`. The order lives in
  exactly one module-level constant with its rationale documented.
- **Conditional stages self-skip.** A stage whose concern does not apply
  to a tool returns the body unchanged. The pipeline is never filtered
  or reordered per tool — `DISPATCH_PIPELINE` is a static tuple.
- **Error capture is neutral; rendering is per-transport.** The
  `error-capture` stage turns a tool-body exception into a neutral
  `CapturedError`. Each adapter appends its own render stage: MCP
  renders a `ToolError` JSON envelope, the CLI renders an `error:`
  stderr line plus a non-zero exit. One captured value, two wire shapes
  — the same seam shape as ADR 0014's `(value, consumer)` rendering.
- **The MCP signature rewrite stays MCP-side.** Rewriting a tool's
  `__signature__` so FastMCP introspects the agent-facing wire params
  (and injects `ctx`) is genuinely fastmcp-specific; it is applied by
  the MCP adapter after the fold, never inside a neutral stage.

## See also

- `CHANGELOG.md` — release-by-release history of behavioral changes.
- `ANTIPATTERNS.md` — patterns that fail at decoration / lint time.
- `examples/streaming_logger/` — log primitives in action.
- `examples/elicitation/` — `await ctx.elicit(...)` portability between
  CLI (stdin) and MCP (client elicitation handler).
- `examples/sampling/` — `await ctx.sample(...)` works on MCP, raises
  `MCPOnlyError` on CLI.
