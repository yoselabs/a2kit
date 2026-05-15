## 0. Prerequisites

- [x] 0.1 Reading-only spike on 2026-05-15 confirmed: ambient state binds **unconditionally** on every dispatch (`packages/mcp/server.py:55-99`, `packages/cli/runtime.py:61-82`). The marker controls ambient **ctx value**, not whether ambient state is bound. Design.md updated.
- [x] 0.2 Confirmed dispatcher reads ctx-in-signature at decoration time: `find_context_param(fn)` runs in `_verbs.py:126` and caches on `A2KitMeta.context_param_name` (`metadata.py:69`). Adding `ambient_ctx_via_router: bool = False` as a sibling field is the correct shape.
- [ ] 0.3 Baseline green: `make lint`, `uv run ty check src/`, `uv run pytest -q --no-cov`.
- [ ] 0.4 Confirm the `Router` base class location (`src/a2kit/routers.py`) and that `slug: str` (not `ClassVar`) — `emits_ldd: ClassVar[bool]` is the right annotation here because there is no instance-scope read pattern for it (unlike `slug`).

## 1. `Router.emits_ldd` class attribute

- [ ] 1.1 Write the failing test first: `tests/test_router_emits_ldd.py` with scenarios — default is False; subclass override to True is read at registration; conflicting overrides on subclass chain resolve via MRO; non-bool value at class scope raises `TypeError` at app build.
- [ ] 1.2 Add `emits_ldd: ClassVar[bool] = False` to `src/a2kit/routers.py` `Router` base. Docstring references this change name and explains the trade-off vs per-tool `ctx`.
- [ ] 1.3 Validate at app build: when `app.add_router(...)` runs, assert `isinstance(router_cls.emits_ldd, bool)`; raise `TypeError` with migration hint if not.

## 2. Metadata field + decoration-time wiring

- [ ] 2.1 Write failing test for metadata: `A2KitMeta.ambient_ctx_via_router` defaults to False; setting `emits_ldd = True` on the owning router class causes the field to be True on every tool registered under it; tools on non-marker routers have it False.
- [ ] 2.2 Add `ambient_ctx_via_router: bool = False` to `A2KitMeta` (`src/a2kit/metadata.py`). Per the frozen-dataclass convention, set it explicitly in the `_verbs.py:126` registration site after reading the owning router's `emits_ldd`.
- [ ] 2.3 The owning-router reference at decoration time: `_verbs.py` decorates the function before the router class registers tools. Verify the wiring: either the tool decorator reads `router.emits_ldd` lazily (during app build), or the router-registration path patches the meta. Pick the path that matches existing conventions (likely router-side at registration; check `routers.py`).
- [ ] 2.4 App-build-time validation: when `app.add_router(...)` runs, assert `isinstance(router_cls.emits_ldd, bool)`; raise `TypeError` with migration hint if not.

## 3. MCP transport — wrapper signature + ctx extraction

- [ ] 3.1 Write failing MCP test in `tests/packages/mcp/test_dispatch_marker_ambient.py`:
  - Scenario A: `emits_ldd=True` router, tool with no `ctx` param, body emits `await a2kit.ldd.event("evt", k=1)` — real `fastmcp.Client(transport=...)` invocation surfaces the event on `client.events`.
  - Scenario B: `emits_ldd=True` router, tool WITH `ctx` declared, body uses `ctx.report_progress(...)` — ctx kwarg still injected; ambient ctx is the same instance.
  - Scenario C: `emits_ldd=False` router (today's behaviour), tool with no `ctx` — body's LDD emission still raises Mode B (preserved).
- [ ] 3.2 Update `_ensure_ctx_in_rewritten_signature` (`packages/mcp/server.py:329`) to add ctx to the rewritten signature when EITHER `ctx_param_name is not None` OR `meta.ambient_ctx_via_router is True`. Use a synthesized internal name (e.g. `__a2kit_ctx__`) for the rewritten-only case so it can't collide with a user param.
- [ ] 3.3 Update `_wrap_with_ldd_state` (`server.py:55`) to extract ctx from kwargs at the synthesized name when `ctx_param_name is None and meta.ambient_ctx_via_router`, place into `ldd_state_for_call`, and pop it before dispatching to the tool body so the body doesn't receive an unknown kwarg.
- [ ] 3.4 Verify the MCP capture-side handlers (`a2kit_kind` / `a2kit_payload` un-prefixing in test client) still work — no path change there.

## 4. CLI transport — ctx synthesis path

- [ ] 4.1 Write failing CLI test in `tests/packages/cli/test_dispatch_marker_ambient.py`:
  - Scenario A: `emits_ldd=True` router, tool with no `ctx`, body emits LDD event — CLI runtime injects synthesized `StderrToolContext` into ambient; no Mode B raise.
  - Scenario B: `emits_ldd=False` router, tool with no `ctx`, body emits LDD event — Mode B raises (preserved).
- [ ] 4.2 Update `_invoke_tool_in_process` (`packages/cli/runtime.py:61-82`):
  - The ctx-synthesis branch at lines 65-66 currently triggers when `ctx_param_name` is set. Extend to also trigger when `meta.ambient_ctx_via_router is True` — but DO NOT inject the synthesized ctx into call_kwargs in that case; only feed it into `ldd_state_for_call`.
  - Read `meta = get_meta(fn)` early; today's reads at line 50 already do this.
- [ ] 4.3 Confirm CLI `<app> health` and other CLI subcommands routed through `Container.dispatch` behave correctly (no regression on non-marker routers).

## 5. Cross-transport parity scenario

- [ ] 5.1 Write one parity test that drives the SAME tool body on BOTH transports (MCP via `a2kit.testing.client`, CLI via `_invoke_tool_in_process` or the CliRunner). Per CLAUDE.md: "Add a real-transport scenario for any change touching the MCP wrapper chain."
- [ ] 5.2 Assert identical event payload shape on both captures.

## 6. Lint rule (advisory) — "ctx declared, never referenced"

- [ ] 6.1 Write failing tests covering the three observable forms (per design.md Q1):
  - Form A: `def fetch(*, ctx: ToolContext, ...): del ctx; ...` on a non-marker router with no body reference to `ctx` → rule fires.
  - Form B: `def fetch(*, _ctx: ToolContext, ...): ...` on a non-marker router with no body reference to `_ctx` → rule fires.
  - Form C: `def fetch(*, ctx: ToolContext, ...): ...` with no `del`, no underscore, no body reference → rule fires.
  - Negative: `def fetch(*, ctx: ToolContext, ...): await ctx.report(...); ...` → does NOT fire (ctx is used).
  - Negative: tool on a router with `emits_ldd = True` and `ctx` declared but unused → does NOT fire (marker already opted in; no suggestion to make).
- [ ] 6.2 Add rule under `src/a2kit/packages/lint/rules/ldd.py` (verify by reading the file's existing rules first). Detection logic per design.md Q1 — AST `Name` visitor on the function body, same technique as `purity` / `caps`.
- [ ] 6.3 Default severity: **advisory** (does not fail build). Consumers opt into the strict gate via `a2kit lint static --strict-advisory`.
- [ ] 6.4 Rule emits a message that names the offending param, the owning router class, and the suggested fix (set `emits_ldd = True`, drop the param). Reference the change name `add-router-ldd-marker` in the hint so consumers can grep the CHANGELOG.
- [ ] 6.5 Wire into `static.py` `RULES` dispatch tuple.
- [ ] 6.6 Update `ANTIPATTERNS.md` with the unused-ctx antipattern + the marker fix.

## 7. Documentation

- [ ] 7.1 Update `openspec/specs/router-conventions/spec.md` purpose section (post-archive) and `OPERATIONAL_CONTRACTS.md` Q8 to reference the marker as the canonical opt-in for LDD-emitting routers. Clarify the corrected mental model: ambient state binds unconditionally; the marker controls ambient `ctx` value when the tool doesn't declare ctx.
- [ ] 7.2 Add `CHANGELOG.md` `Unreleased` entry under "Added".
- [ ] 7.3 Update `docs/patterns/` (or wherever router conventions are documented) with a "Routers that emit LDD events" subsection showing the one-line opt-in.

## 8. Spec delta + archive prep

- [ ] 8.1 `openspec validate --changes --strict` — must pass.
- [ ] 8.2 Check archive order: A1/A2 touches `in-process-test-client`, F touches `health-probe` — no header collisions with `router-conventions`. Safe to author in any order. Per CLAUDE.md, archive in implementation order.
- [ ] 8.3 After green CI, archive: `openspec archive add-router-ldd-marker`.
- [ ] 8.4 Update `docs/feedback-responses/v0.38-a2web-round-10.md` with a "Shipped in v0.X" footnote pointing at the merged commit.

## 9. Out-of-scope non-tasks (sanity)

- [ ] 9.1 No per-tool unconditional ctx synthesis. The `False` default holds; marker is per-router opt-in.
- [ ] 9.2 No `@a2kit.uses_ldd` decorator. Marker is the only opt-in.
- [ ] 9.3 No `App.ldd_default` setting. Router granularity is the scope.
- [ ] 9.4 No deprecation of `ctx: ToolContext` in tool signatures. Explicit ctx remains valid and is still required when the tool body actually uses ctx.
- [ ] 9.5 No auto-detection of LDD usage in tool bodies. Static analysis isn't sufficient.
- [ ] 9.6 No change to standalone DI resolution path. Standalone callers wrap their own `ldd_state_for_call` if they want LDD; unchanged from today.
