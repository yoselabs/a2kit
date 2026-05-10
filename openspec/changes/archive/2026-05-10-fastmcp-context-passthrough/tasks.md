## 1. Specs in BDD-first order

- [x] 1.1 Gherkin-flavored scenarios documented at the top of `tests/examples/elicitation/test_server.py` — three scenarios (CLI accept, CLI decline, MCP via in-memory test client).
- [x] 1.2 Gherkin-flavored scenarios documented at the top of `tests/examples/sampling/test_server.py` — two scenarios (MCP returns summary, CLI raises MCPOnlyError).
- [x] 1.3 Inventory test at `tests/test_context_surface.py` — asserts every public `fastmcp.Context` member is on the stub or in the documented `MCP_ONLY` allowlist. Currently green.

## 2. Lazy ToolContext re-export

- [x] 2.1 `_LAZY_ATTRS["ToolContext"] = ("fastmcp", "Context")` in `src/a2kit/__init__.py`; existing `__getattr__` resolves on first access.
- [x] 2.2 `"ToolContext"` already in `__all__`.
- [x] 2.3 Deleted `src/a2kit/runtime.py`; updated `signature.py` to lazy-detect via `sys.modules`. Removed `runtime.py` entry from `mirror.py` allowlist.
- [x] 2.4 `tests/test_cold_start.py::test_import_a2kit_under_100ms_and_no_fastmcp` still passes (verified).
- [x] 2.5 `tests/test_toolcontext_alias.py::test_toolcontext_resolves_to_fastmcp_context` asserts `a2kit.ToolContext is fastmcp.Context`.
- [x] 2.6 `tests/test_toolcontext_alias.py::test_import_star_binds_toolcontext` exercises wildcard import via ``exec``, asserts the bound symbol is identity-equal to `fastmcp.Context`.

## 3. Consolidate signature introspection

- [x] 3.1 `signature.resolve_hints(fn)` shipped. **Caching dropped** — `id(fn)` reused across nested test scopes producing stale empty-hint hits. WARN-once dedup via `__qualname__` is preserved.
- [x] 3.2 `find_context_param` uses `resolve_hints`. Identity check via `sys.modules.get("fastmcp")` short-circuit keeps cold-start clean.
- [x] 3.3 `wire_input_params` uses `resolve_hints`.
- [x] 3.4 `_build_descriptors` (in `app.py`) uses `resolve_hints`.
- [x] 3.5 `_factory_params` (in `connections/container.py`) uses `resolve_hints`.
- [x] 3.6 `_params_for_method` (in `connections/container.py`) uses `resolve_hints`.
- [x] 3.7 Migrated `_reject_singleton_connection_dep` to `resolve_hints` for consistency. Dedicated unit tests at `tests/test_resolve_hints.py`: empty-dict on failure, WARN-once dedup per `__qualname__`, normal-function passthrough.

## 4. Delete FastMCPContextAdapter

- [x] 4.1 `build_mcp_server` now wraps tool fns with `_wrap_with_ldd_state` (sets contextvar) instead of `bind_context` (which constructed an adapter). The live `fastmcp.Context` is injected by FastMCP directly — no adapter wrapping.
- [x] 4.2 Deleted `src/a2kit/packages/mcp/context.py`.
- [x] 4.3 Deleted `tests/packages/mcp/test_context.py`.
- [x] 4.4 No adapter-specific `noqa` markers remained.
- [x] 4.5 No `__init__.py` export of `FastMCPContextAdapter` existed.

## 5. Rewrite StderrToolContext as fastmcp.Context-shaped stub

- [x] 5.1 `MCPOnlyError(RuntimeError)` lives in `src/a2kit/packages/cli/context.py` with `(method, hint=None)` constructor.
- [x] 5.2 Rewrote `StderrToolContext` with full Context-shaped surface. Logging methods (`info`/`warning`/`error`/`debug`/`log`) and `report_progress` are now async to match `fastmcp.Context` — examples and tests migrated to `await`. Updated A2K-IMPORT-DISCIPLINE allowlist to permit the lazy `fastmcp.server.elicitation` import inside `elicit()`.
- [x] 5.3 `set_state` / `get_state` / `delete_state` use a per-instance dict. Tests cover round-trip and isolation between instances.
- [x] 5.4 `read_resource` handles `file://` URIs — text by default, binary fallback on `UnicodeDecodeError`. Other schemes raise `MCPOnlyError`.
- [x] 5.5 `elicit` runs an `input()` prompt loop. Supports str/int/float/bool/list[str] enums. EOF/Ctrl-C → `CancelledElicitation`; literal `--decline` → `DeclinedElicitation`; otherwise `AcceptedElicitation(data=...)`. Complex types raise `MCPOnlyError`.
- [x] 5.6 `sample`/`sample_step`/`list_resources`/`list_prompts`/`get_prompt`/`list_roots`/`send_notification` raise `MCPOnlyError`.
- [x] 5.7 CLI runtime already instantiates `StderrToolContext` and binds it via `find_context_param`/`_wrap_with_ldd_state` — no changes needed since the stub class identity is unchanged.
- [x] 5.8 Inventory test at `tests/test_context_surface.py` is green — full surface covered.

## 6. LDD primitives as free functions

- [x] 6.1 Created `src/a2kit/packages/ldd/__init__.py` (with `src/a2kit/ldd.py` as a thin shim — keeps `from a2kit.ldd import event, report` working while satisfying `A2K-CORE-CLEAN`).
- [x] 6.2 `event` MCP path uses `await ctx.log(level="info", extra={"a2kit_kind": "event", ...})` (matches the prior adapter wire format byte-for-byte). CLI path delegates to `StderrToolContext._emit("event", ...)`.
- [x] 6.3 `report` validates payload type against `ldd_state.report_type` (raises `ReportTypeNotDeclared`/`ReportTypeMismatch` even when reports are disabled). MCP path mirrors the prior adapter `extra={"a2kit_kind": "report", ...}`. CLI path uses `_emit("report", ...)`.
- [x] 6.4 `--no-events` / `--no-reports` / `A2KIT_LDD=off` flow into `ldd_state_for_call(events_enabled=..., reports_enabled=...)` set by both `mcp/server.py::_wrap_with_ldd_state` and `cli/runtime.py::_invoke_tool_in_process`. Gated calls return `None` cleanly.
- [x] 6.5 Updated `examples/streaming_logger/routers.py` to import from `a2kit.ldd` and call `await event(ctx, ...)` / `await report(ctx, ...)`.
- [x] 6.6 `examples/streaming_logger/README.md` updated: API note about `await` on Context methods, channel table now shows `await ctx.info(...)` etc. and `await event(ctx, ...)` / `await report(ctx, ...)` from `a2kit.ldd`.
- [x] 6.7 All streaming_logger tests still pass (verified — `tests/examples/streaming_logger/` green).

## 7. Lint and DI allowlist updates

- [x] 7.1 No-op — `_allowlist` in `Container` has no callers in-tree; no class-identity reference to update. `a2kit.ToolContext is fastmcp.Context` makes any future allowlist work transparently.
- [x] 7.2 No-op — there is no separate `A2K-DI-PROVIDER` rule file. The container's `partition_kwargs` walks types by identity, which works automatically since the alias resolves to the same class.
- [x] 7.3 Two new lint-rule regressions in `tests/packages/lint/test_rules_misc.py`: `cli/context.py` allowlisted for the lazy elicit() import; user-app code under their own package can use `from fastmcp import Context` without A2K-IMPORT-DISCIPLINE firing (rule only fires inside `a2kit/`).
- [x] 7.4 Audited: `mirror.py` had a stale `runtime.py` exemption removed. `lint/cli.py` docstring mention is irrelevant. No other lint-text references.

## 8. Examples

- [x] 8.1 `examples/elicitation/server.py` with `UsersRouter.greet` calling `await ctx.elicit("Pick a username", response_type=str)`. Returns greeting on accept, `{status: "no name"}` on decline/cancel.
- [x] 8.2 CLI path uses CliRunner stdin (`alice\n` / `--decline\n`); MCP path uses `fastmcp.Client(transport=server, elicitation_handler=...)` for in-memory parity. Stub now writes the elicit prompt to stderr (not stdout) so the tool's JSON return on stdout stays parseable.
- [x] 8.3 `examples/sampling/server.py` with `TextRouter.summarize` calling `await ctx.sample("Summarize ...")`. Extracts `result.text` for the response payload.
- [x] 8.4 MCP path uses `Client(transport=server, sampling_handler=...)` returning a string; CLI path asserts non-zero exit and an MCPOnlyError mention in output.
- [x] 8.5 All five scenarios from 1.1 and 1.2 are green.

## 9. Cold-start and benchmarks

- [x] 9.1 Bare-package test unchanged. Added `test_user_app_help_a2kit_overhead_under_200ms` parametrized over `streaming_logger` / `elicitation` / `sampling` examples. Pre-imports fastmcp before timing so the assertion measures a2kit + click + builder overhead only — fastmcp's own ~1s import cost is out of scope (and unavoidable for any real user app since tool annotations resolve `a2kit.ToolContext`).
- [x] 9.2 CHANGELOG note added under "Cold-start budget note" explaining the bare-package vs user-app split. README polish deferred.

## 9b. Structured events (absorbed from a2web feedback)

- [x] 9b.1 `StderrToolContext.send_log_message(level, logger, data)` renders the canonical LDD line via the shared `format_ldd_line` helper. Non-JSON values coerced to `str(v)`.
- [x] 9b.2 CLI ``event`` path goes through `_emit(..., elapsed_ms=...)` which delegates to `format_ldd_line` — single source of truth shared with `info`/`warning`/`error`/`debug`/`log`/`report_progress`/`send_log_message`.
- [x] 9b.3 `format_ldd_line` is the shared helper. `_APP_START_MONOTONIC` captured at module load; falls back to that basis when LDD called outside a tool dispatch. Text portion capped at `TEXT_CAP=60` chars with `…` elision; cap applied to MCP `message` field too. `elapsed_ms: int` injected into every event/report payload.
- [x] 9b.4 `EventRegistry` with `register(model, *, progress=None)` and `async emit_typed(ctx, evt)`. `emit_typed` calls `evt.model_dump(mode="json")` → `event(ctx, type(evt).__name__, **dumped)` → `ctx.report_progress(current, total)` when registered. Re-registration is last-write-wins. `event` and `report` switched to positional-only first args (`__ctx`, `__name`/`payload`) so dumped payloads can include ``name`` / ``ctx`` keys without collision.
- [x] 9b.5 `app.ldd.events: EventRegistry` mounted on `App.__init__` via `_AppLdd` namespace object. Lazy-imported from `a2kit.packages.ldd` inside `__init__` — no cold-start impact for apps that don't construct an App (and `App` itself is already lazy via `__getattr__`).
- [x] 9b.6 11 tests in `tests/test_event_registry.py`: `format_ldd_line` shape, cap with `…`, no-msg path; `_emit` byte-equivalent to `format_ldd_line`; `elapsed_ms` monotonic across events; typed registry emit+payload, progress callback, last-write-wins, datetime → ISO via `model_dump(mode="json")`; `app.ldd.events` registry presence.
- [x] 9b.7 `examples/typed_events/server.py` demonstrates `app.ldd.events.register(StepStarted, progress=lambda e: (e.step, e.total))` plus `emit_typed`. Tested via `tests/examples/typed_events/test_server.py` — typed events render to stderr with progress lines.

## 10. Spec deltas + capability promotion

- [ ] 10.1 Verify `openspec validate fastmcp-context-passthrough --strict` passes.
- [ ] 10.2 After implementation: run `openspec archive fastmcp-context-passthrough`. Confirm `openspec/specs/mcp-context-passthrough/spec.md` is created and `thin-core-surface`, `request-scoped-di` are updated.

## 11. Release

- [x] 11.1 `pyproject.toml` bumped 0.23.0 → 0.24.0.
- [x] 11.2 `CHANGELOG.md` 0.24.0 section with BREAKING (ToolContext = fastmcp.Context, async logging methods, ctx.event/report removed, FastMCPContextAdapter deleted), Migration (await ctx.info, free-function event/report, typed event registry, a2web pattern), Added (LDD primitives, EventRegistry, format_ldd_line, resolve_hints, full StderrToolContext surface, MCPOnlyError, three new examples, A2K-LOCAL-RETURN-MODEL), Changed (Container.resolve optional, positional-only event/report args, allowlist), Removed (a2kit.runtime, a2kit.packages.mcp.context, ctx.event/ctx.report). Cold-start budget note included.
- [x] 11.3 `README.md` updated: `ToolContext` line in core symbols table; the LDD section now shows async logging + free-function event/report + typed registry; lint-rule descriptions updated to `report(ctx, ...)` form.
- [ ] 11.4 Tag `v0.24.0` and push. **Held for user** — destructive/external action; needs explicit go.
- [x] 11.5 Wrote new `project_a2kit_design_state.md` capturing the v0.24 surface (Context passthrough, LDD free functions, typed event registry, lifecycle, singletons, format routing, cold-start budget, examples). Indexed in MEMORY.md. The older `project_a2kit_format_routing.md` is kept untouched as a v0.22→v0.23 trace.
