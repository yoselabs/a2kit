## Why

a2kit owns a narrow `ToolContext` Protocol that mirrors a strict subset of `fastmcp.Context` (5 of 15 methods today). Every time FastMCP ships a Context capability — elicitation, sampling, resources, session state — a2kit must extend the Protocol, the MCP passthrough adapter, and the CLI adapter, then update lint rules and docs. The MCP-side adapter is already a pure passthrough; the Protocol is pure ownership tax. Replacing `a2kit.ToolContext` with `fastmcp.Context` directly eliminates ~200 LOC of adapter code, deletes a parallel API, and gets new FastMCP features for free — including `ctx.elicit(...)` which the user wants to use today. The empirical context backing this decision is captured in K research R123 (FastMCP modernity audit).

## What Changes

- **BREAKING**: `a2kit.ToolContext` becomes a re-export of `fastmcp.Context` (single tier; no parallel Protocol). Tools annotate `ctx: a2kit.ToolContext` and receive the full FastMCP Context surface in both transports.
- **DELETE**: `src/a2kit/packages/mcp/context.py::FastMCPContextAdapter` and its test fixtures. The MCP path passes `fastmcp.Context` straight through.
- **REWRITE**: `src/a2kit/packages/cli/context.py::StderrToolContext` becomes a `fastmcp.Context`-shaped CLI stub — real where possible (logging → stderr, progress → stderr line), best-effort where reasonable (`elicit` → stdin prompts driven by the JSON schema, `set/get/delete_state` → in-memory dict, `read_resource` → `file://` handler), and an explicit `RuntimeError("requires MCP transport")` for genuinely MCP-only methods (`sample`, `send_notification`, `list_resources`, `list_prompts`, `get_prompt`).
- **NEW**: a2kit re-exports `fastmcp.Context` lazily via package `__getattr__` so `import a2kit` does not pull `fastmcp` (preserves the bare-package cold-start invariant).
- **RELAX**: cold-start invariant for *user apps* whose tools annotate `ToolContext`. `<my-app> --help` will import `fastmcp` while resolving annotations via `get_type_hints`. The bare `import a2kit` test stays. The user-app `--help` test moves from "no fastmcp imported" to "no fastmcp tool registry constructed" (server still lazy via `LazyGroup`).
- **CONSOLIDATE**: the four `try get_type_hints / except / fallback` sites (`signature.py::find_context_param`, `signature.py::wire_input_params`, `app.py::_build_descriptors`, `connections/container.py::_factory_params` + `_params_for_method`) collapse into one `signature.resolve_hints` helper with one fallback policy.
- **NEW EXAMPLES**: `examples/elicitation/` (works in both transports — CLI prompts on stdin, MCP forwards to client) and `examples/sampling/` (MCP works, CLI raises gracefully).
- **LINT**: existing rules referencing the narrow `ToolContext` Protocol (e.g., A2K-DI-PROVIDER allowlist) are updated to refer to `fastmcp.Context`. No new rules; the "two-tier" rule mentioned in earlier exploration is dropped — single tier means no enforcement gap.
- **NEW (absorbed from a2web feedback)**: CLI stub implements `send_log_message(level, logger, data)` as the structured-log primitive that backs `a2kit.ldd.event`'s CLI rendering. Honors the LDD events kill-switch. Both transports SHALL agree on the structured `data` payload key-for-key.
- **NEW (absorbed from a2web feedback)**: LDD wire-format invariants are pinned explicitly: every `a2kit.ldd.event` emission carries `elapsed_ms: int` (since process start or `App.on_startup` dispatch); CLI lines prefix `+s.mmm` zero-padded relative time; human-readable text is capped at 60 chars with `…` elision.
- **NEW (absorbed from a2web feedback)**: typed event registry on `app.ldd.events`. Consumers register Pydantic event models with optional `progress` callbacks via `app.ldd.events.register(EventModel, progress=fn)`; `await app.ldd.events.emit_typed(ctx, EventModel(...))` serializes via `model_dump(mode="json")`, dispatches to `a2kit.ldd.event`, and calls `ctx.report_progress(progress(event), 1.0)` if registered. One callback per event class; last-write-wins on re-registration.

## Capabilities

### New Capabilities

- `mcp-context-passthrough`: defines the requirement that a2kit re-exports `fastmcp.Context` as `a2kit.ToolContext`, that the MCP transport passes the real Context through unwrapped, and that the CLI transport supplies a `fastmcp.Context`-shaped stub with the documented method-by-method behavior matrix (real/stub/raise).

### Modified Capabilities

- `thin-core-surface`: the `ToolContext Protocol provides protocol-neutral logging + progress` requirement is replaced. The Protocol is no longer a2kit-defined; the surface is whatever `fastmcp.Context` exposes. Adapter selection happens at invocation, not via a custom Protocol.
- `request-scoped-di`: the always-provided allowlist requirement updates from "`ToolContext` and `App`" to "`fastmcp.Context` (re-exported as `a2kit.ToolContext`) and `App`". Behavior identical from the tool author's perspective.

## Impact

- **Code deleted**: `packages/mcp/context.py` (~200 LOC), corresponding tests, two `noqa` sites tied to the narrow Protocol.
- **Code rewritten**: `packages/cli/context.py` (~80 → ~150 LOC for the stub Context class).
- **Code added**: `signature.resolve_hints` helper consolidating four duplicated try/except sites.
- **Public API**: `a2kit.ToolContext` is now `fastmcp.Context`. Tools that only used `info/warning/error/debug/report_progress` are source-compatible. Tools or test doubles that implemented the old narrow Protocol manually (none in-tree; possible downstream) need to satisfy the wider surface or use the new CLI stub class.
- **Dependencies**: no new dependency. `fastmcp` is already required.
- **Cold start**: bare `import a2kit` stays clean (verified by an updated test). User apps whose tools annotate `ToolContext` will import fastmcp during `--help`. Documented as an explicit trade in CHANGELOG.
- **Downstream**: `a2web` and any other a2kit consumer pin `>=0.24` to pick this up. Source changes typically zero unless they were implementing a custom `ToolContext`.
- **Examples affected**: `examples/streaming_logger/` continues to work unchanged; `examples/elicitation/` and `examples/sampling/` are added.
- **Specs deleted/touched**: `thin-core-surface` and `request-scoped-di` get delta updates; new `mcp-context-passthrough` spec is added.
