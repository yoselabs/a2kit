## Context

a2web's feedback (`A2KIT_FEEDBACK.md`) catalogues 11 pain points; v0.24 (`fastmcp-context-passthrough`, `app-lifecycle-and-di-ergonomics`, `tool-return-type-discipline`) addressed items 1, 2, 3, 4 (partial), 5, 6. Six items remain — five concrete asks (7, 8, 9, 10, antipattern-#1 widening) plus six open questions (Q1–Q6) that need documented answers, and the disputed item 11 (builder hygiene) which is deferred.

This change picks up the unaddressed Tier-1 + Tier-2 items from the consumer's prioritization. Item 11 is excluded because it's a meaningfully larger surface change and no consumer is currently blocked on it; it deserves a wider survey before commitment.

The repo is a v0.24 release candidate (pyproject + CHANGELOG done, awaiting tag). This change targets v0.25 — additive surface, one strict tightening (antipattern #1 broadening) acceptable pre-1.0.

## Goals / Non-Goals

**Goals:**
- In-process test client that runs the **full** dispatch path (DI resolve, decorator processing, return rendering, ctx wiring) so consumers can assert behaviors that today require subprocess or live MCP server.
- MCP `ToolAnnotations` are settable per-tool through the verb decorators with conservative defaults — no existing tool changes wire output unless it opts in.
- Built-in health probe that ops/MCP-clients can rely on without re-inventing it. Hidden from `list_tools` so it doesn't pollute the agent-facing tool surface.
- Documented docstring → description contract that lets consumers write rich descriptions and know exactly where they render.
- Antipattern #1 lint widened beyond `-> str` to all primitive returns and `None`.
- Open questions Q1–Q6 turned into either documented contracts or explicit "deferred to N+1" notes.

**Non-Goals:**
- Restructuring the fluent builder API (item 11). Out of scope for this round.
- Streaming output for large responses (Q6). Documented as deferred.
- Per-tool timeouts as a built-in (Q2). Documented as recommended pattern using `anyio.fail_after`, not a built-in flag.
- Auto-reload (Q4). Documented as a tooling concern, not a framework concern.
- Test-client request/response recording / golden snapshots — basic capture only; snapshot infra stays in user code.

## Decisions

### Decision 1: Test client surface — `a2kit.testing.client(app)` async-context-manager

```python
async with a2kit.testing.client(app) as c:
    result = await c.invoke("tasks.create_project", name="P1")
    assert any(e["name"] == "ProjectCreated" for e in c.events)
    assert c.progress[-1] == (1.0, 1.0)
    assert c.render_as("json", result)["id"]
```

**Why an async context manager:** Lifecycle hooks fire inside `__aenter__` / `__aexit__`. Mirrors `fastmcp.Client` shape so the mental model carries over. `c.invoke(...)` is the only required call; everything else is introspection.

**Why no transport:** No MCP or HTTP layer between test and tool — the same dispatcher that runs in production runs here. The test client *is* the production code path with capture hooks bound to `ctx` instead of a real transport.

**Capture surfaces:**
- `c.events: list[dict]` — every `await event(ctx, name, **payload)` and structured-event emission, payload + elapsed_ms.
- `c.progress: list[tuple[float, float | None]]` — every `await ctx.report_progress(...)`.
- `c.logs: list[dict]` — every `ctx.info/warning/error/debug` and `ctx.log` call (level + message + fields).
- `c.reports: list[Any]` — every `await report(ctx, payload)` value.
- `c.render_as(format, value)` — synchronous render of a return value through `a2kit.packages.formatter`.
- `c.tools()` — returns the list of tool descriptors the dispatcher would expose, matching what the MCP schema would advertise.

**Implementation:** `a2kit.packages.testing.client.TestClient` wraps an `App`. `__aenter__` runs `dispatch_startup(app)`. `invoke(tool_name, **kwargs)` looks up the descriptor, builds a captured `ctx`, runs the resolved tool, returns the value. `__aexit__` runs `dispatch_shutdown(app)`.

The captured `ctx` is a subclass of `StderrToolContext` whose `_emit` writes into the capture buffers instead of stderr. `_is_fastmcp_context` continues to short-circuit it as not-a-fastmcp-context, so `a2kit.ldd.event` / `report` route through `_emit`. Cold-start invariant preserved (no fastmcp pull when only invoking through the test client).

**Alternatives:**
- Subprocess-based test client (run real CLI). Rejected: slow, brittle, doesn't capture in-process state.
- Mock-everything fixture pattern. Rejected: re-implements the dispatcher and skips the very thing we want to test.
- Borrow `fastmcp.Client` over an in-memory transport. Rejected: pulls fastmcp for everyone who imports the test client; we want CLI-shape capture too.

### Decision 2: MCP tool annotations — kwargs on existing decorators

```python
@a2kit.read(idempotent=True, open_world=True, title="Fetch Web Page")
async def fetch(...) -> FetchResponse: ...

@a2kit.write(destructive=False, idempotent=True, title="Mark Task Complete")
async def complete_task(...) -> Task: ...
```

**Why expand the existing decorators rather than a separate `@annotate(...)`:** the annotations are tightly coupled to the read/write distinction. `destructive=` only makes sense on `@write`; rejecting it on `@read` at decoration time keeps the API self-documenting.

**Conservative defaults:**
- `@read`: `readOnlyHint=True`, `idempotentHint=False`, `destructiveHint=False`, `openWorldHint=False`.
- `@write`: `readOnlyHint=False`, `idempotentHint=False`, `destructiveHint=True`, `openWorldHint=False`.

`openWorldHint` defaults False — apps that touch the network must opt in. This matches a2web's diagnosis that the silent default was wrong.

**Title vs name:** `title` is a display string forwarded to MCP `ToolAnnotations.title`; the tool's `name` (e.g. `web.fetch`) remains the protocol identifier. CLI ignores `title` (uses the docstring first line for the click subcommand short-help).

**Implementation:** the verb decorators already build a `fastmcp.types.ToolAnnotations`. Add the new kwargs, pass through. No change at the MCP server build site (`a2kit.packages.mcp.server` already forwards `meta.annotations`).

### Decision 3: Health probe — `App(..., health_tool=True)` + `@app.health_check`

```python
app = a2kit.App("a2web", health_tool=True)

@app.health_check
async def _check_sqlite(state: AppState) -> a2kit.HealthResult:
    if state.sqlite is None:
        return a2kit.HealthResult.fail("sqlite not opened")
    return a2kit.HealthResult.ok()
```

**Tool naming and visibility:** the tool name is `_meta.health` — the `_meta` namespace prefix flags it as protocol-meta and keeps `list_tools` filtering clean. By default the tool is **excluded from `list_tools`** unless the client passes `?include_meta=true` or equivalent — agents shouldn't see it in their tool picker. CLI surface stays — `<app> health` is the canonical ops invocation.

**Result aggregation:** any registered probe returning `HealthResult.fail(reason)` flips overall status to `degraded`. The tool returns `{"status": "ok"|"degraded", "version": app.version, "checks": [{name, status, reason?}]}`. CLI exits non-zero on degraded.

**Why opt-in via constructor:** apps without ops needs shouldn't pay a tool slot they don't use. Default `False` keeps the surface clean.

**Why `HealthResult` and not bool/str:** future-proofing — we want to add `latency_ms`, `last_checked`, etc. without breaking the API.

**Alternatives:**
- Always-on health tool. Rejected: pollutes the tool list for apps that don't want it.
- HTTP `/health` endpoint. Rejected: a2kit has no HTTP transport surface; would require a new dependency.

### Decision 4: Docstring contract — first-line description, body as long help

**Rule (documented in README + the new tool-description-contract spec):**
- The docstring's **first non-empty line** becomes the tool `description` (MCP) and the click subcommand short-help (CLI).
- The **full body** (PEP-257 dedented) becomes:
  - MCP tool description's long form, sent verbatim (markdown supported; clients render).
  - CLI `<app> <tool> --help` body (markdown stripped to plain text via a small `_strip_md` helper — no full markdown→ANSI renderer; bold/italic markers removed, links rendered as `text (url)`).
- Per-parameter descriptions come from `Annotated[T, a2kit.Param(description="...")]` on the tool kwarg. Pydantic `Field(description=...)` continues to work for kwargs that *are* a model.

**Why first-line + body and not separate fields:** matches Python idiom (PEP 257). Lower friction than `description=` / `long_description=`. Agent-facing tools want richness; this gives consumers permission to write 30 lines of docstring without worrying where they go.

**`a2kit.Param` shape:**
```python
async def fetch(*, url: Annotated[str, a2kit.Param(description="Absolute http(s) URL to fetch.")]) -> ...
```
Stored as schema metadata; FastMCP-side translates to `parameters[i].description`. CLI builder reads it for click `--url HELP`.

### Decision 5: Antipattern #1 lint broadening

`_check_return` currently raises only when `ret is str`. Broaden to:
- Primitive types: `str`, `int`, `float`, `bool`, `bytes`.
- `None` (return type).
- The `inspect.Parameter.empty` sentinel (no annotation) — emit a warning, not an error, since untyped tools are still legal at runtime; lint enforces stricter.

The decoration-time check raises `InvalidToolReturnTypeError(name)` with a clear message: "tool returns must be a Pydantic model, dict, or list/Page of such — got `<primitive>`". Lint A2K-LOCAL-RETURN-MODEL stays as a paired static check.

**Why decoration-time, not lint-only:** consumer feedback was "antipatterns are folklore" — making them fail at import time is the loudest signal possible. Belt-and-suspenders with the lint catches stringified annotations.

### Decision 6: Open questions Q1–Q6 — `OPERATIONAL_CONTRACTS.md`

A new top-level doc captures the contracts. Each question gets a short section: "Current behavior", "Tool author's responsibility", "Future plans (if any)". Q-by-Q stance:

- **Q1 Cancellation:** anyio cancellation propagates from transport disconnect / SIGINT through `asyncio.CancelledError` to the tool body. Tools MUST handle `CancelledError` cleanly (close opened resources). a2kit does not catch — it bubbles. Tested via a new regression that cancels mid-tool-body and asserts cleanup ran.
- **Q2 Per-tool timeout:** not a built-in. Recommended pattern: `async with anyio.fail_after(60): ...` inside the tool body, or use `singleton`-cached infrastructure that enforces its own budget. Documented; no flag.
- **Q3 Multi-App:** production-supported. Each App has its own singleton cache, lifecycle handlers, container, and LDD state. The `dispatch_startup`/`dispatch_shutdown` functions are App-scoped. The two-App canary in a2web becomes a load-bearing test pattern, not overkill.
- **Q4 Auto-reload:** out of scope for a2kit core. Recommended tooling: `watchexec`, `entr`, or `uvicorn --reload`-style wrappers. Documented.
- **Q5 Error envelope:** unhandled exceptions in tool bodies bubble to the dispatcher. MCP path produces `JsonRpcError(code=-32603, message=str(exc))`; full traceback included when `app.debug=True` (new flag, defaults False). CLI path produces non-zero exit + traceback to stderr. Documented and regression-tested.
- **Q6 Streaming output:** deferred. Tools today return atomic responses. The path would be `AsyncIterator[Chunk]` returns translating to MCP chunked notifications — material design work; not in this round.

## Risks / Trade-offs

- **Test client surface drift** → mitigation: `a2kit.testing.client` reuses the production dispatcher (no parallel implementation). The capture surfaces are read-only views; if dispatcher behavior changes, the test client follows for free.
- **MCP annotations conservative defaults break consumer expectations** → mitigation: `idempotent=False` and `openWorldHint=False` are the spec's "safe" defaults; consumers who need the truth opt in. CHANGELOG calls this out.
- **Health tool name collision** (`_meta.health`) → mitigation: reserve `_meta.*` namespace; raise at registration if a user tool wants that prefix. Documented.
- **Antipattern #1 broadening fails at import time** for any consumer returning primitives → mitigation: rare in practice (the lint already shipped for #2 had near-zero hits in-tree); CHANGELOG calls it out as a strict tightening; pre-1.0 latitude.
- **Docstring markdown rendering on CLI** can mangle complex prose → mitigation: simple stripper; complex markdown already an antipattern for terminal text; document.
- **`a2kit.Param` adds a new public symbol** → mitigation: thin wrapper around pydantic-style metadata; no external dep. Lazy-importable.
- **Test-client capture buffers grow unbounded for long tools** → mitigation: document the buffer pattern; deferred-streaming option at `client.event_stream()` (deferred; bounded list is acceptable for v0.25).

## Migration Plan

- Additive surface; no migrations required for the test client, MCP annotations, health tool, or docstring contract.
- Antipattern #1 broadening: consumers returning `-> int` / `-> bool` etc. will fail at decoration time on first import. Migration: change return to `dict[str, int]` (or a typed model). CHANGELOG flags this.
- `App.debug` flag (new) defaults False — existing apps unaffected.

## Open Questions

- **Test client `connection=` plumbing.** For apps with connections, `client.invoke("...", connection="...")` needs to flow the wire `connection` value through the dispatcher exactly like the CLI/MCP paths do. Plan: same code path, no special case. Validate against `examples/tracker` (which has connections).
- **Health tool authentication.** If a future auth middleware lands, health should bypass it. Defer to that change; document the intent now so the hook point is reserved.
- **`a2kit.Param` vs `pydantic.Field`.** When the tool has a single body model, `Field(description=...)` already works. We add `Param` for direct kwargs only — diverging from the model case. Acceptable: covers the gap without forcing model wrapping.
