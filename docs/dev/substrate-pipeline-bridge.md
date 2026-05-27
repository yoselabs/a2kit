# Substrate-to-pipeline bridge

> Reference: ADR 0025, change `dispatch-pipeline-parity-on-http` (2026-05-27).

## Picture

```
Wire request
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│  Substrate adapter (HTTP / MCP / CLI / future)          │
│  - opens wire (Starlette ASGI, FastMCP middleware,      │
│    Click invoke, ...)                                   │
│  - extracts Principal from substrate-native auth        │
│  - PUBLISHES Principal into `request_scope`  ─────┐     │
│  - calls into the folded pipeline                  │    │
│                                                    │    │
│   ┌──────────────────────────────────────────┐    │    │
│   │  DISPATCH_PIPELINE (transport-neutral)   │    │    │
│   │  Timeout > Enricher > ErrorEnvelope >    │    │    │
│   │  RouterLazyEnter > DispatchHook >        │    │    │
│   │  AuthorizeGate > LddState > ErrorCapture │ ◄──┘    │
│   │                                          │         │
│   │  ErrorEnvelopeStage WRITES rendered      │         │
│   │  prose+envelope into `_render_state` ────┐         │
│   │                                          │         │
│   │  tool body                               │         │
│   └──────────────────────────────────────────┘         │
│                                                    │   │
│  - READS `_render_state` on CapturedError ◄────────┘   │
│  - renders to substrate-native wire (JSONResponse,     │
│    ToolError, exit code, ...)                          │
└─────────────────────────────────────────────────────────┘
   │
   ▼
Wire response
```

## The contract — two named ContextVars

The dispatch pipeline is transport-neutral: it never imports `fastapi`,
`starlette`, or `fastmcp`. Substrates never inspect dispatch-internal
state. The only communication is through two named ContextVars:

| ContextVar | Direction | Module | Owner-of-publish | Reader |
|---|---|---|---|---|
| `a2kit.packages.context.request_scope` | inbound (substrate → pipeline) | `packages/context/request_scope.py` | substrate adapter (per call) | `DispatchHookStage`, `AuthorizeGateStage`, any future stage needing per-call seeds |
| `a2kit.packages.dispatch._render_state` | outbound (pipeline → substrate) | `packages/dispatch/_render_state.py` | `ErrorEnvelopeStage` (writes); the per-substrate error-render stage (opens/closes the slot) | per-substrate error-render stage (reads via `get_rendered_error(exc)`) |

The first is for **typed seeds** the pipeline needs from the wire
(today: `Principal`; tomorrow possibly `RequestId`, `Tenant`). The
second is for the **rendered error envelope** the pipeline produces and
each substrate converts to its own wire shape.

## What each substrate MUST do

For every registered substrate that exposes tool calls:

1. **Before folding the pipeline** for a tool call, publish every typed
   seed the substrate owns onto `request_scope`:

   ```python
   token = request_scope.publish(principal)
   try:
       result = await chained(**kwargs)  # the folded pipeline + tool body
   finally:
       request_scope.reset(token)
   ```

2. **Open `_render_state` around the call** so `ErrorEnvelopeStage` has
   somewhere to write:

   ```python
   token = open_render_state()
   try:
       ...
   finally:
       close_render_state(token)
   ```

3. **On a `CapturedError` whose wrapped exception is an `AppError`**,
   read the rendered envelope from `_render_state` and convert it to
   substrate-native wire shape:

   ```python
   rendered = get_rendered_error(exc)  # RenderedError | None
   if rendered is not None:
       return JSONResponse(status_code=..., content={"error": rendered.envelope})
   ```

4. **Never re-derive** `AppError → kind → wire-shape`. That mapping
   lives once in `ErrorEnvelopeStage` (for prose + envelope dict) plus
   one substrate-side helper for the substrate-specific code (e.g.
   `packages/http/_error_render_stage.http_status_for`). Substrates do
   NOT carry their own copy of the kind→shape map.

## Why ContextVars, not a Protocol class

The brainstorm that produced this design (2026-05-27, four parallel
agents on framework-precedent / first-principles / a2kit-deep-read /
anti-pattern axes) considered extracting a `SubstrateBridge(Protocol)`
with `seed_scope(...)` / `render_error(...)` methods. We **rejected** it
as premature: HTTP is the only consumer being migrated to the bridge;
MCP and CLI already comply organically. With one user, the Protocol
adds API surface without buying clarity.

The contract is enforced by capability tests under
`tests/capabilities/substrate_pipeline_bridge/` — those tests are the
regression net. When a third substrate (gRPC, AGNTCY, queue consumer)
lands and exercises the bridge three times, the change that introduces
it should evaluate whether to promote to a Protocol.

## Why TWO ContextVars, not one

`request_scope` carries typed seeds INTO the pipeline. `_render_state`
carries rendered output OUT of the pipeline. They have different
lifetimes, different ownership (substrate vs `ErrorEnvelopeStage`), and
different access patterns (typed-key lookup vs `id(exc)` lookup). One
ContextVar mixing both would conflate two concerns and obscure the
contract; two ContextVars makes the substrate-vs-pipeline boundary
explicit.

## Pipeline-side helpers

| Reader | Helper |
|---|---|
| Read a typed seed | `request_scope.get(T)` (raises) or `request_scope.try_get(T)` (returns None) |
| Read all seeds (e.g. to thread into `Container.call_scope`) | `request_scope.all_seeds()` |
| Read rendered error for an `AppError` | `get_rendered_error(exc)` |

Pipeline stages SHALL use these exclusively. Direct ContextVar
manipulation outside the helpers is a bug.

## Substrate-side seams (today)

| Substrate | Principal-publish seam | Error-render stage |
|---|---|---|
| HTTP (`packages/http/`) | `install_substrate_signature` wrapper (FastAPI Security → kwarg → publish before pipeline runs). API-key middleware (`packages/auth/api_key.py`) also publishes for that auth path. | `HttpErrorRenderStage` (`packages/http/_error_render_stage.py`) — opens/closes `_render_state`, reads on `CapturedError`, returns `JSONResponse` |
| MCP (`packages/mcp/`) | `PrincipalMiddleware` (`packages/mcp/principal_middleware.py`) — FastMCP middleware that reads `context.principal` / `context.access_token` and publishes | `McpErrorRenderStage` (`packages/mcp/_wrappers.py`) — raises `ToolError(prose) from exc`; the paired `TypedErrorEnvelopeMiddleware` reads `_render_state` to patch `structured_content`. |
| CLI (`packages/cli/`) | CLI runs as a single process; Principal extraction is handled at the entry point if at all (CLI auth is not first-class today). | `CliErrorRenderStage` (`packages/cli/`) — reads `get_rendered_error(exc)`, writes prose to stderr, exits with mapped code via `_cli_exit_for(exc)`. |

## What does NOT live in the pipeline

Some concerns are legitimately wire-layer and SHALL stay substrate-side:

- **Format / render of success path** — FastMCP's `FormatRoutingMiddleware`
  manipulates the `content` channel post-call; HTTP relies on FastAPI's
  content negotiation. Pipeline can't see substrate-native return types
  (`StreamingResponse`, MCP `Content` blocks).
- **List-view meta-tool rewriting** — MCP's `ListViewMiddleware` is an
  MCP-protocol concern.
- **Tool-call shape guards** — MCP's `GuardsMiddleware` inspects raw
  argument dicts before substrate hydration.
- **CORS, content negotiation, streaming framing** — substrate-native by
  construction.

If a concern touches the wire shape, it stays wire-side. If a concern
operates on the parsed tool call (fn, args, container, principal), it
goes in the pipeline.

## See also

- ADR 0019: split app/runtime; dispatch pipeline is the neutral seam.
- ADR 0020: substrate signature splitting (parameter classification).
- ADR 0025: substrate-to-pipeline bridge (this contract — Y-statement).
- Change `dispatch-pipeline-parity-on-http`: the proposal + design that
  landed this contract on HTTP.
- `STRUCTURE_ISSUES.md` S11, S13: the audit smells closed by this work.
