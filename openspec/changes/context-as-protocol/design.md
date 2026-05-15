## Context

Today's setup, factually:

- `a2kit.ToolContext` is a lazy re-export of `fastmcp.Context` (`a2kit/__init__.py:24`).
- `StderrToolContext` (`packages/cli/context.py:74`) is an a2kit-owned class with no base — explicitly described as "mimicking `fastmcp.Context`."
- `_is_tool_context` in `signature.py:84-102` matches by walking annotations and identity-checking against `fastmcp.Context`.
- Consumer tools annotate `ctx: a2kit.ToolContext` → type checker sees `fastmcp.Context` → at runtime CLI hands them a `StderrToolContext` (a duck-typed lie that Python doesn't enforce).
- A2kit's `_is_fastmcp_context` (`packages/ldd/__init__.py:211-228`) distinguishes real fastmcp.Context from CLI stub at runtime to pick the right wire format.

## The contract relationship

There's an implicit contract between fastmcp.Context and StderrToolContext. They share a public surface. a2kit's correctness depends on them staying in sync, but the contract has no canonical declaration.

```
                                  ┌─────────────────────────┐
                                  │  Implicit contract      │
                                  │  (today: undocumented)  │
                                  └────────────┬────────────┘
                                               │ shared surface
              ┌────────────────────────────────┼────────────────────────────────┐
              │                                                                  │
      ┌───────┴─────────┐                                          ┌────────────┴─────────┐
      │ fastmcp.Context │                                          │ StderrToolContext    │
      │ (third party)   │                                          │ ("mimicking" stub)   │
      └─────────────────┘                                          └──────────────────────┘
```

After the change:

```
                                  ┌─────────────────────────┐
                                  │  a2kit.ToolContext      │
                                  │  (explicit Protocol)    │
                                  └────────────┬────────────┘
                                               │ structurally satisfies
              ┌────────────────────────────────┼────────────────────────────────┐
              │                                                                  │
      ┌───────┴─────────┐                                          ┌────────────┴─────────┐
      │ fastmcp.Context │                                          │ StderrToolContext    │
      │ (third party)   │                                          │ (a2kit impl)         │
      └─────────────────┘                                          └──────────────────────┘
```

The contract gets a name. Both concrete classes continue to work unchanged.

## How wide should the Protocol be?

Two endpoints of the spectrum:

**Wide Protocol** — mirror fastmcp.Context's whole surface (~30 methods including MCP-only ones like `sample`, `list_resources`, etc.).
- Pro: tools annotated `ctx: a2kit.ToolContext` get full IDE autocomplete for everything.
- Con: the Protocol becomes a chasing target for fastmcp's evolution. CLI's StderrToolContext has to keep implementing MCP-only methods as raising stubs. Every fastmcp release that adds a method either adds it to the Protocol (we chase) or breaks the "all impls satisfy" invariant.

**Narrow Protocol** — only the cross-transport surface (log family, report_progress, request_id, client_id).
- Pro: small, stable, low maintenance. The contract is "what every transport actually provides." No chasing.
- Con: tools that want MCP-only methods (`sample`, `elicit`, `read_resource`) need to either annotate `ctx: fastmcp.Context` directly OR check `isinstance(ctx, Elicitable)` at runtime (using a feature Protocol — out of scope here).

**Decision: narrow.** Reasons:

1. **The implicit contract that actually held up across both transports** is the narrow surface. CLI's stub raises `MCPOnlyError` on `sample` etc. — those methods are documented as not portable. Promoting the actual cross-transport surface to a Protocol formalizes what was already true.

2. **MCP-only consumers stay MCP-typed.** Annotating `ctx: fastmcp.Context` for tools that need `await ctx.sample(...)` is fine — they're already in MCP territory, fastmcp is loaded, and the type annotation reflects reality.

3. **Future capability system grows from the narrow base.** Feature Protocols layer on top (`Elicitable`, `Samplable`) — natural composition when needed.

4. **Lower maintenance.** Narrow Protocol changes only when the cross-transport surface itself genuinely changes. fastmcp's evolution doesn't force Protocol churn.

### The exact narrow surface

Surveying consumer usage of `ctx.*` methods:

- Cross-transport (definitely in Protocol):
  - `log(message, level=..., logger_name=..., extra=...)`
  - `debug` / `info` / `warning` / `error` (signature-equivalent shortcuts)
  - `report_progress(progress, total=..., message=...)`
  - `request_id` / `client_id` (attributes)

- Cross-transport-ish (probably in Protocol):
  - `elicit(...)` — fastmcp does MCP elicitation; CLI does stdin prompt. Both legitimate impls. Useful enough to put in the base Protocol.
  - `set_state` / `get_state` / `delete_state` — per-instance dict on CLI, real state on MCP. Both legitimate. Probably in.

- MCP-only (NOT in Protocol):
  - `sample`, `sample_step` — pure MCP sampling. CLI raises MCPOnlyError.
  - `list_resources`, `list_prompts`, `get_prompt`, `list_roots` — MCP-only resource/prompt registries.
  - `send_notification`, `read_resource` — MCP-specific.

Final Protocol surface in this change ships:

```python
class ToolContext(Protocol):
    request_id: str
    client_id: str | None
    async def log(...): ...
    async def debug(...): ...
    async def info(...): ...
    async def warning(...): ...
    async def error(...): ...
    async def report_progress(...): ...
    async def elicit(...): ...
    async def set_state(...): ...
    async def get_state(...): ...
    async def delete_state(...): ...
```

Roughly 11 methods + 2 attributes. Audit at implementation time may add or remove one or two based on real usage patterns; the design.md surface is the starting point, not the final word.

## `@runtime_checkable` — why use it

Two reasons:

1. **Internal LDD wire-format dispatch.** `_is_fastmcp_context` exists today and continues to need to differentiate real fastmcp.Context from any other impl. That check is by identity (`isinstance(ctx, fastmcp.Context)`), unaffected by the Protocol. But future runtime checks against feature Protocols (parked for now) want `@runtime_checkable`.

2. **Consumer-side flexibility.** A consumer may want `isinstance(ctx, a2kit.ToolContext)` to assert at runtime that ctx satisfies the contract. `@runtime_checkable` enables this. Cost: O(method-count) check at isinstance time. Acceptable.

## Migration risk audit

Grepped repo (during proposal scoping) for risk patterns:

- `isinstance(_, fastmcp.Context)` — only inside `_is_fastmcp_context` (intentional, unchanged).
- `isinstance(_, StderrToolContext)` — zero hits.
- `a2kit.ToolContext is fastmcp.Context` identity checks — would need to be updated if any exist; grepped, none found.
- Tests asserting `isinstance(ctx, fastmcp.Context)` — found in two files (`test_field_logging_mcp_path.py`, `test_context_surface.py`). These tests are inside MCP-flow regression scenarios; they continue to work because the MCP wrapper delivers real fastmcp.Context instances. The isinstance check passes; the Protocol identity is irrelevant.

Net: low migration cost. Most internal references are docstrings that get rewritten over time.

## What we are NOT doing

- **No subclassing fastmcp.Context from StderrToolContext.** That would import fastmcp eagerly in CLI mode, defeating the cold-start budget. Hard no.
- **No removing `_is_fastmcp_context`.** It's still needed for wire-format dispatch (fastmcp's `ctx.log(extra=...)` vs a2kit's bespoke `_emit`). Internal runtime detail.
- **No feature Protocols / capability system.** Composing `Elicitable`, `Samplable`, etc. on top of the base Protocol is a future enhancement when a real motivator appears. The base Protocol design here is forward-compatible.
- **No generic parameterization** (`ToolContext[FastMCP]` vs `ToolContext[CLI]`). Plain non-generic Protocol now; can gain a TypeVar later without breaking consumers.
- **No transport-specific tool restriction** (registration-time validation that a tool requiring MCPToolContext only registers under MCP). Future capability system, not now.

## Naming bikeshed (not blocking)

- `_context_protocol.py` vs `_context.py` vs colocating in `a2kit/__init__.py`. Putting it in a private module keeps it discoverable but not crowded. Settling for `src/a2kit/_context_protocol.py`; rename later if needed.
- `StderrToolContext` vs `CliToolContext`. Today's name describes the output destination (stderr); the new contract identity is "CLI transport's ToolContext impl." `CliToolContext` is structurally more correct. **Defer the rename** — it's pure churn for a name change.

## Test coverage

- **Existing tests**: all should pass without modification. The Protocol is structurally satisfied by both concrete classes; tests that exercise `isinstance` against the Protocol via `@runtime_checkable` succeed.
- **New BDD scenarios** (under `tests/test_context_protocol.py` or similar):
  - `a2kit.ToolContext` is a Protocol (not `fastmcp.Context`).
  - `fastmcp.Context` satisfies the Protocol structurally.
  - `StderrToolContext` satisfies the Protocol structurally.
  - `isinstance(ctx, a2kit.ToolContext)` returns True under both transports.
  - Cold-start unaffected: bare `import a2kit; "fastmcp" not in sys.modules`.
