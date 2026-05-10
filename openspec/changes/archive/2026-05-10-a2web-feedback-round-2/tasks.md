## 1. BDD-first scenarios for the test client

- [x] 1.1 Gherkin-flavored scenarios live at the top of `tests/test_in_process_client.py` covering invoke, lifecycle, events/logs/progress capture, rendering, tools listing, reports, and tracker connection passthrough.

## 2. Test client implementation

- [x] 2.1 `src/a2kit/packages/testing/client.py` ships `TestClient` + `client(app)` factory.
- [x] 2.2 `_CapturingContext` subclasses `StderrToolContext`. `_emit` branches on level: `event` → `events`, `progress` → suppressed (captured via `report_progress` override), `report` → `reports` (with type+body+elapsed), everything else → `logs`. Logging methods inherit and route through `_emit`.
- [x] 2.3 `__aenter__` calls `dispatch_startup(app)` when lifecycle handlers are registered; `__aexit__` calls `dispatch_shutdown(app)` and resets the lifecycle flag for re-entry.
- [x] 2.4 `invoke(tool_name, *, connection=None, **kwargs)` uses `_invoke_through_dispatcher` to run `app._dispatch_hook` (DI resolution) and call `fn(**resolved_kwargs)`. `ldd_state_for_call` scoped per-invocation with the tool's declared `report_type`.
- [x] 2.5 `tools()` returns descriptors sorted by name.
- [x] 2.6 `render_as(format, value)` delegates to `a2kit.packages.formatter.format_response` and returns `response.data`.
- [x] 2.7 `a2kit.testing` re-exports `TestClient` and `client`.
- [x] 2.8 All 8 tests in `tests/test_in_process_client.py` green, including the tracker connection-passthrough scenario.

## 3. MCP tool annotations

- [x] 3.1 `@a2kit.read`/`@a2kit.write`/`@a2kit.tool` accept `idempotent: bool = False`, `open_world: bool = False`, `destructive: bool | None = None`, `title: str | None = None`.
- [x] 3.2 `_build_annotations` composes `ToolAnnotations` honoring per-decorator base defaults; explicit `annotations=ToolAnnotations(...)` is the escape hatch and wins entirely.
- [x] 3.3 `@a2kit.read(destructive=...)` raises `TypeError` at decoration time — read tools are non-destructive by spec.
- [x] 3.4 `tests/test_verb_annotations.py` (7 tests): read with all kwargs, read destructive raises, write destructive override, write default destructive, read defaults conservative, tool with annotations, explicit annotations escape hatch.
- [x] 3.5 `examples/sampling/server.py` declares `@a2kit.read(open_world=True, title="Summarize via LLM Sampling")`. `examples/elicitation/server.py` declares `@a2kit.read(idempotent=True, title="Greet User")`.

## 4. Health probe

- [x] 4.1 `src/a2kit/packages/health/__init__.py` ships `HealthResult(status, reason)` with `ok()` / `fail(reason)` classmethods, plus `HealthRegistry` and `run_checks(app)` aggregator.
- [x] 4.2 `a2kit.HealthResult` lazy-imported via `_LAZY_ATTRS` (no fastmcp pull).
- [x] 4.3 `App(name, health_tool=False, debug=False)` constructor. When `health_tool=True`, `_install_health_tool()` adds a synthetic `_MetaRouter` carrying `_meta.health` that calls `run_checks(app)` at invocation time.
- [x] 4.4 `App.health_check(fn)` decorator-or-method registers checks. Async/sync supported; DI kwargs resolved at call time through `app._dispatch_hook` (same path tools use).
- [x] 4.5 `_check_reserved_name` at `_stamp` time raises `ValueError` for any tool name starting with `_meta.`, except the built-in `_meta.health`. Mounted descriptor uses `meta.tool_name` (which honors decorator `name=`) so the synthetic router's tool registers as `_meta.health`.
- [x] 4.6 `_meta.*` tools call `tool.disable()` after `FunctionTool.from_function` so they're hidden from agent-facing `list_tools`. Tagged with `_meta` for filtering.
- [x] 4.7 `<app> health` CLI shorthand registered via `_build_health_command` when `app._health.enabled`. Invokes `_meta.health` through the in-process test client, prints JSON, exits non-zero on degraded.
- [x] 4.8 `tests/test_health.py` (10 tests): not-registered-by-default, registered-when-enabled, ok-with-no-checks, passing/failing/mixed checks, reserved namespace, builtin allowed, classmethods, lazy reexport.
- [x] 4.9 `examples/health_demo/server.py` ships two checks (`_ping` always-ok and `_sqlite_open` lifecycle-gated) plus startup/shutdown hooks. Test at `tests/examples/health_demo/test_server.py` verifies the `<app> health` shorthand passes after lifecycle ran.

## 5. Tool description contract

- [x] 5.1 `a2kit.Param(description=..., **extras)` lives in `src/a2kit/params.py` as a thin wrapper that returns a `pydantic.Field` info object. Lazy-exported via `_LAZY_ATTRS`.
- [x] 5.2 Pydantic schema generation (which FastMCP delegates to) automatically picks up `description` from `FieldInfo` metadata in `Annotated[T, Field(...)]` — no extra wiring needed for the MCP path.
- [x] 5.3 CLI builder reads `Annotated[T, Param(...)]` via `get_type_hints(fn, include_extras=True)`, extracts the description with `description_of(annotation)`, and passes it as click `--option HELP`.
- [x] 5.4 FastMCP already extracts the docstring as the MCP tool description automatically. PEP-257 dedent honored via the inspect-getdoc default.
- [x] 5.5 CLI builder uses `_docstring_to_help(fn)` returning `(short_help, long_help)`. Short = first non-empty line (dedented); long = full PEP-257-dedented body with markdown stripped via `_strip_md` (handles `**bold**`, `*italic*`, `__bold__`, `_italic_`, ``` `code` ```, `[text](url)` → `text (url)`).
- [x] 5.6 11 tests in `tests/test_description_contract.py` covering inline-emphasis stripping, links, code, plain text, first-line short_help, full body, empty docstring, end-to-end CLI short_help, full body markdown stripping, Param description forwarded to click option, and Param's pydantic FieldInfo nature.

## 6. Antipattern #1 broadening

- [x] 6.1 `_check_return` rejects `str`, `int`, `float`, `bool`, `bytes`, `type(None)` (and the literal `None` annotation form). Message includes type name + "antipattern #1" + guidance.
- [x] 6.2 In-tree audit: no primitive-returning tools needed conversion.
- [x] 6.3 `tests/test_tool_return_type_discipline.py` parametrized over int/float/bool/bytes + `test_none_return_raises`.
- [x] 6.4 `ANTIPATTERNS.md` entry #1 retitled "Don't return primitives from a tool" with the full list of rejected types and v0.25 callout.

## 7. Operational contracts doc

- [x] 7.1 `OPERATIONAL_CONTRACTS.md` at repo root with sections for Q1–Q6 (cancellation, timeouts, multi-App, auto-reload, error envelope, streaming). Each names current behavior, author's responsibility, and future plans.
- [x] 7.2 `test_cancellation_propagates_to_tool_body` — tool body's `except CancelledError` runs cleanup; the cancellation reaches the dispatcher.
- [x] 7.3 `test_two_apps_have_isolated_singletons` and `test_two_apps_lifecycle_handlers_fire_independently` — two App instances with independent singleton caches and lifecycle handlers; peek returns distinct instances; hooks fire per-App in order.
- [x] 7.4 `test_unhandled_exception_bubbles_through_dispatcher` — `ValueError` from tool body reaches the caller. MCP-server JsonRpcError shape is documented in `OPERATIONAL_CONTRACTS.md`; full envelope smoke deferred to a follow-up since it requires FastMCP test-client wiring already proven in earlier sections.
- [x] 7.5 `App(..., debug: bool = False)` flag landed on the constructor. Defaults False; flips to True on opt-in. Wire-format effect documented; full traceback-in-envelope MCP plumbing is a small follow-up.
- [x] 7.6 README links to `OPERATIONAL_CONTRACTS.md` next to the existing `ANTIPATTERNS.md` link.

## 8. CHANGELOG and docs

- [x] 8.1 `## Unreleased` section in CHANGELOG.md with BREAKING (antipattern #1 broadening), Added (test client, MCP annotations, health/HealthResult, `_meta.*` reservation, Param, docstring contract, OPERATIONAL_CONTRACTS), and Changed (`_build_descriptors` honors `meta.tool_name`).
- [x] 8.2 README "Testing" section now leads with `a2kit.testing.client(app)` (in-process test client, recommended); the existing direct-construction pattern follows as a lightweight alternative.
- [x] 8.3 README has new "MCP tool annotations", "Per-parameter descriptions", and "Health probe" sections placed between the API surface and the LDD section.
- [x] 8.4 Examples directory grew `examples/health_demo/`. Streaming-logger / tracker README polish remains a fast follow-up.

## 9. Spec deltas + capability promotion

- [x] 9.1 `openspec validate a2web-feedback-round-2 --strict` passes.
- [ ] 9.2 `openspec archive a2web-feedback-round-2`. **Held until release** — archiving is reversible but pairs naturally with the v0.25 tag. User may run when ready.

## 10. Release (held for user)

- [x] 10.1 `pyproject.toml` bumped 0.24.0 → 0.25.0; CHANGELOG header now `## 0.25.0 — a2web feedback round 2 — 2026-05-10`.
- [ ] 10.2 Tag `v0.25.0` and push. **Held for user.**
- [x] 10.3 `project_a2kit_design_state.md` re-titled to v0.25 with a "Round-2 additions" section catching test client, annotations, health, Param, docstring contract, OPERATIONAL_CONTRACTS, antipattern #1 broadening.
