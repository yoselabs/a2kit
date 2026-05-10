## Context

a2kit ships an `a2kit.ToolContext` Protocol (`src/a2kit/runtime.py`) that defines five methods: `info`, `warning`, `error`, `debug`, `report_progress`. Tools annotate `ctx: a2kit.ToolContext` and the framework binds an adapter at invocation time:

- **MCP path** — `src/a2kit/packages/mcp/context.py::FastMCPContextAdapter` wraps `fastmcp.Context` and forwards the five Protocol methods. Pure passthrough.
- **CLI path** — `src/a2kit/packages/cli/context.py::StderrToolContext` implements the Protocol directly: stderr lines for logs, stderr `[ +s.mmm progress]` for progress.

Empirical audit (K research R123, conducted 2026-05-09 via FastMCP 3.x docs) showed:

| FastMCP `Context` method | a2kit Protocol covers? |
|---|---|
| `debug`, `info`, `warning`, `error` | yes |
| `report_progress` | yes |
| `elicit`, `sample` | **no** |
| `read_resource`, `list_resources` | no |
| `list_prompts`, `get_prompt` | no |
| `set_state`, `get_state`, `delete_state` | no |
| `send_notification` | no |

a2kit's surface is 5 of 15 methods. The 8 missing methods are MCP-shaped (state lives in a session, sampling needs a client LLM, resources need a registry). The user wants `ctx.elicit(...)` available now, and the cost of adding it via the current pattern (extend Protocol → extend adapter → extend lint rules → extend stub → extend docs) is materially the same as eliminating the Protocol entirely.

The user explicitly chose "minimize ownership surface" and is open to `ToolContext` *being* `fastmcp.Context` rather than mirroring it.

Adjacent constraints already in the codebase:

- `tests/test_cold_start.py::test_import_a2kit_under_100ms_and_no_fastmcp` enforces that `import a2kit` does not transitively import `fastmcp`. Preserving this for the bare package is feasible via lazy `__getattr__`. Preserving it for *user apps that annotate `ctx: ToolContext`* is not — `typing.get_type_hints` resolves the annotation at descriptor-build time, which is `add_router(...)` time, which is before `--help` renders.
- `App._build_descriptors` already swallows `get_type_hints` failures; the descriptor falls back to `format_hint="json"` and `return_type=None`. The Context detection has its own copy of the try/except in `signature.py::find_context_param`. Four such sites exist in core.

## Goals / Non-Goals

**Goals:**

- Replace `a2kit.ToolContext` with a re-export of `fastmcp.Context`. One tier; one type for tool authors.
- Delete `FastMCPContextAdapter` and its tests; the MCP path passes the real `fastmcp.Context` through unwrapped.
- Rewrite `StderrToolContext` as a `fastmcp.Context`-shaped CLI stand-in covering the full surface — real where it makes sense, best-effort where reasonable, explicit error where not.
- Make `ctx.elicit(...)` work in both transports: MCP forwards to the client; CLI prompts on stdin driven by the elicitation JSON schema.
- Make `ctx.set_state / get_state / delete_state` work in both transports: MCP forwards to the session; CLI uses an in-memory dict scoped to the process.
- Consolidate the four `try get_type_hints` sites into one `signature.resolve_hints` helper.
- Preserve bare `import a2kit` cold-start (no fastmcp import).
- Preserve `<my-app> serve` lazy-loading of the MCP server (LazyGroup intact).

**Non-Goals:**

- Building first-class a2kit decorators for resources, prompts, or roots. The passthrough makes those usable; first-class wrapping is a later, separate change.
- Refactoring `a2kit.packages.mcp.listview` to a FastMCP middleware. Confirmed FastMCP does not provide projection/pagination natively; the listview stays. Possible future change.
- Implementing a full filesystem sandbox for `read_resource` in the CLI stub. The CLI stub handles only `file://` URIs trivially; non-`file://` URIs raise.
- Touching the existing `event` and `report` LDD primitives. They live on a2kit's ToolContext today as additive methods; under the new design they live on a separate small mixin or as free functions taking `ctx`. Decision deferred to design Decision 4.
- Changing `--no-reports` / `--no-events` CLI flags or the `A2KIT_LDD` env var. Their semantics carry over.

## Decisions

### Decision 1: `a2kit.ToolContext = fastmcp.Context` (alias) vs subclass vs Protocol

**Chosen: alias.** `a2kit.ToolContext` is *literally* `fastmcp.Context`, exposed via lazy module-level `__getattr__` on the `a2kit` package so that `import a2kit` alone does not pull `fastmcp`. Accessing `a2kit.ToolContext` (which only happens when a user actually wants the symbol) triggers `from fastmcp import Context as ToolContext`.

**Why not subclass:** subclassing `fastmcp.Context` to add a2kit-specific niceties recreates the ownership tax we are trying to delete. If FastMCP changes its `__init__` signature, the subclass breaks.

**Why not keep a Protocol:** Protocols would need to enumerate all 15 methods and re-grow whenever FastMCP grows. Same problem we have today, scaled up.

**Alternatives considered:**

- A two-tier model (`a2kit.ToolContext` narrow + `fastmcp.Context` for MCP-only). Rejected after the audit: 8 of 15 methods are not portable, the narrow tier shrinks to a near-trivial logging interface, and the cognitive cost of teaching "two contexts, pick the right one" exceeds the value.
- A Protocol that is structurally compatible with `fastmcp.Context`. Rejected: still requires manual maintenance to track FastMCP additions; lint cannot check structural compatibility cheaply.

### Decision 2: CLI stub method-by-method behavior

The CLI stub class (the new `StderrToolContext`) is a duck-typed `fastmcp.Context` workalike — it does not subclass `fastmcp.Context` to avoid coupling to its internals, but exposes every public method.

| Method | CLI behavior | Rationale |
|---|---|---|
| `debug`, `info`, `warning`, `error` | stderr line `[ +s.mmm LEVEL] msg key=val` (current behavior) | preserves LDD wire-format spec |
| `report_progress(current, total)` | stderr line `[ +s.mmm progress] current=N total=M` (current behavior) | preserves LDD wire-format spec |
| `elicit(message, response_type)` | render schema → series of `click.prompt()` calls → return `ElicitResult(action="accept", data=...)`; user sends EOF (Ctrl-D) → `action="cancel"`; user types `--decline` literal → `action="decline"` | covers the "interactive tool that needs more input" use case in CLI honestly |
| `sample(messages, ...)` | raise `RuntimeError("ctx.sample() requires MCP transport — no client LLM available in CLI mode")` | sampling is structurally MCP-only |
| `read_resource(uri)` | parse URI; if `file://`, read the file and return bytes/text; otherwise raise `RuntimeError(f"CLI stub: unsupported scheme in {uri!r}; only file:// is handled")` | trivially useful for local resources without inventing a registry |
| `list_resources`, `list_prompts`, `get_prompt`, `list_roots` | return empty list / raise | no a2kit-side resource registry exists |
| `set_state(key, value)`, `get_state(key)`, `delete_state(key)` | in-memory dict on the stub instance, scoped to one CLI invocation | matches MCP semantics within process bounds |
| `send_notification` | noop | nothing to notify |

The stub raises a typed `MCPOnlyError(RuntimeError)` for the explicitly-unsupported methods so callers and tests can distinguish "you used an MCP-only feature in CLI" from generic runtime errors.

### Decision 3: Lazy `ToolContext` re-export

Implemented in `src/a2kit/__init__.py` via `__getattr__`:

```python
def __getattr__(name: str):
    if name == "ToolContext":
        from fastmcp import Context as _C
        globals()["ToolContext"] = _C
        return _C
    raise AttributeError(name)
```

Plus `__all__` carries `"ToolContext"` so `from a2kit import *` works. This matches the existing PEP 562 lazy-attribute pattern in the codebase (see `PLC0415` ignore in `pyproject.toml`).

`tests/test_cold_start.py::test_import_a2kit_under_100ms_and_no_fastmcp` continues to pass — bare `import a2kit` does not touch `fastmcp`.

User apps that annotate `ctx: a2kit.ToolContext` will pull `fastmcp` when their package's tool module is imported (PEP 563 `from __future__ import annotations` defers it, but `App.add_router → _build_descriptors → typing.get_type_hints` resolves it at registration). This is documented as expected.

### Decision 4: `event` and `report` LDD primitives

Today these live as additional methods on the narrow Protocol (`ctx.event(name, **kw)`, `await ctx.report(BatchReport(...))`). They are a2kit-specific and don't exist on `fastmcp.Context`.

**Chosen:** keep them as a2kit-side functions, not methods. Tools that use LDD beyond logging:

```python
from a2kit.ldd import event, report

await event(ctx, "api.fetched", count=30)
await report(ctx, BatchReport(batch=4, accepted=12))
```

The functions accept any `fastmcp.Context`-shaped object and route over `ctx.send_notification` (MCP) or stderr (CLI stub).

**Why not methods:** monkey-patching methods onto `fastmcp.Context` is unsafe (and impossible if it's a final class). Sticking them as methods on a `ToolContext` subclass forces back to "Decision 1: subclass" which we rejected.

**Alternatives considered:**

- Stash on `ctx` via `set_state`. Rejected — abuses session state for what is really a client-channel call.
- Drop `event`/`report` entirely. Rejected — they're load-bearing for the LDD spec and `streaming_logger` example.

This is mildly migration-flavored: tools currently calling `ctx.event(...)` switch to `await event(ctx, ...)`. Documented in CHANGELOG.

### Decision 5: Consolidate `get_type_hints` sites

Single helper in `src/a2kit/signature.py`:

```python
def resolve_hints(fn: Callable[..., Any]) -> dict[str, Any]:
    """Return type hints for ``fn`` or {} on any resolution failure.

    Single fallback policy for the four sites that previously each
    rolled their own try/except. Logs a single WARN per fn-name, not
    per call.
    """
    ...
```

Replaces:

- `signature.py::find_context_param`'s inline try/except
- `signature.py::wire_input_params`'s inline try/except
- `app.py::_build_descriptors`'s inline try/except
- `connections/container.py::_factory_params`'s inline try/except
- `connections/container.py::_params_for_method`'s inline try/except

Five sites, one helper. The helper caches by `id(fn)` so warm-path lookup is O(1).

### Decision 6: Lint rule update

`A2K-DI-PROVIDER` allowlist changes from `{ToolContext, App}` to `{fastmcp.Context, App}`. Since `a2kit.ToolContext is fastmcp.Context`, both names resolve to the same class object — the rule remains correct for tools written either way.

No new lint rule. The two-tier-rule mentioned in earlier exploration is dropped (single tier eliminates the gap).

## Risks / Trade-offs

- **Cold start of user apps balloons by ~50–150ms** → Mitigation: documented explicitly in CHANGELOG; `<my-app> serve` was already paying this; only `<my-app> --help` and `<my-app> tasks list --schema` pay newly. Benchmark in tasks ensures the regression is bounded; if it exceeds 200ms on CI the change is rolled back to a hybrid (string-detect annotations).

- **Tools or test doubles implementing the old narrow Protocol break** → Mitigation: in-tree there are none. CHANGELOG migration note shows the one-line fix (use `fastmcp.Context` from `fastmcp.testing` or `unittest.mock.MagicMock(spec=fastmcp.Context)`). This is a 0.x → 0.x BREAKING change; we accept it.

- **`StderrToolContext` falls behind `fastmcp.Context` API additions** → Mitigation: it's duck-typed, so missing methods raise `AttributeError` at call time with a clear message. A test inventories `dir(fastmcp.Context)` and asserts every public method is either implemented or explicitly in a known-MCP-only set. Test fails when FastMCP adds a new method, prompting a maintenance touch.

- **`ctx.elicit` UX in CLI is noticeably worse than in MCP** → Mitigation: the schema-driven `click.prompt()` loop handles primitive-only schemas (per the FastMCP elicitation spec). Complex nested schemas raise with a clear error pointing to the MCP-only path. Documented in `examples/elicitation/`.

- **`set_state` in CLI is per-process, not per-session** → Mitigation: documented that session ≡ invocation in CLI; tools that depend on cross-call state must run via MCP. Test verifies the boundary.

- **Existing `thin-core-surface` and `request-scoped-di` specs reference `ToolContext` Protocol** → Mitigation: spec deltas in this change update both. Archive workflow handles the merge.

- **Migration ordering for downstream `a2web`** → Mitigation: the existing `streaming_logger` example continues to work source-unchanged; a2web's PR1 already uses `ctx: a2kit.ToolContext` with logging-only methods, which remains source-compatible. Pin bump to `>=0.24` is the only required action downstream.

## Migration Plan

1. Land the change behind a single feature branch `feat/fastmcp-context-passthrough`.
2. Run full test suite locally + CI. Verify:
   - `test_import_a2kit_under_100ms_and_no_fastmcp` passes.
   - All existing `streaming_logger` tests pass with no source changes.
   - New `examples/elicitation/` tests pass under both CLI and MCP.
   - Cold-start benchmark for a representative user app stays under 200ms (`tracker --help`).
3. Tag and release as `0.24.0` (BREAKING per semver-pre-1.0 convention — minor bump signals removal of `FastMCPContextAdapter` from the public API).
4. Update `a2web` pin: `>=0.23,<1` → `>=0.24,<1`. Source-no-op verification.
5. Archive the openspec change.

**Rollback:** revert the merge commit. The change is contained to context-related modules + one signature helper. Downstream pin reverts trivially.

## Open Questions

- Should `event` and `report` live in `a2kit.ldd` (new module) or stay in `a2kit.packages.mcp.reports`? Leaning toward `a2kit.ldd` because they are protocol-neutral. Decide during implementation.
- Should `ElicitResult` be re-exported from `a2kit` for ergonomics, or do users `from fastmcp import ElicitResult`? Leaning toward not re-exporting — same logic as Decision 1 (don't own surface we don't need to own).
