## 1. The dispatch package, protocol, and build spec

- [x] 1.1 `src/a2kit/packages/dispatch/__init__.py` — fastmcp-free
      package (NOT on the `A2K-IMPORT-DISCIPLINE` allowlist)
- [x] 1.2 `ToolBuildSpec` — frozen dataclass carrying `app`, `router`,
      `meta`, `descriptor`, plus `reports_enabled` / `events_enabled` /
      `sinks` (the LDD stage needs per-invocation flags; the MCP adapter
      sets them once at build time, the CLI adapter per invocation)
- [x] 1.3 `DispatchStage` protocol: `name: str` and
      `wrap(self, fn, spec: ToolBuildSpec) -> fn`
- [x] 1.4 Tests: a trivial stage composes; `wrap` returning `fn`
      unchanged is a valid no-op (`test_pipeline.py`)

## 2. The five transport-neutral stages (BDD-first per unit)

- [x] 2.1 `EnricherStage` — unifies the CLI + MCP enricher wraps
- [x] 2.2 `LddStateStage` — ldd-state + ctx synthesis, fastmcp-free
      (`StderrToolContext` fallback from `a2kit.packages.context`)
- [x] 2.3 `TimeoutStage` — one mechanism (`anyio.fail_after`);
      self-skips when `meta.extras.timeout_seconds` is unset
- [x] 2.4 `DispatchHookStage` — self-skips when the App carries the
      default identity hook *and* the tool has no injectables
- [x] 2.5 `RouterLazyEnterStage` — self-skips when the router has no
      `__aenter__`; closes the CLI parity gap
- [x] 2.6 One unit test per stage, each driving the stage directly —
      no `build_mcp_server`, no CLI builder (`test_stages.py`)
- [x] 2.7 Test: `packages/dispatch` imports no `fastmcp`
      (`test_dispatch.py`)

## 3. Declare and fold the pipeline

- [x] 3.1 `DISPATCH_PIPELINE: tuple[DispatchStage, ...]` innermost-first,
      ordering rationale in its docstring (`pipeline.py`)
- [x] 3.2 `fold_pipeline` helper applies the pipeline to a tool body
- [x] 3.3 Integration test: the folded chain's nesting order matches
      `DISPATCH_PIPELINE` (`test_pipeline.py`)

## 4. Error capture: neutral stage + per-transport render

- [x] 4.1 `ErrorCaptureStage` in `packages/dispatch` — captures a
      tool-body exception into the neutral `CapturedError`
- [x] 4.2 MCP adapter: `McpErrorRenderStage` renders `ToolError(json)`
- [x] 4.3 CLI adapter: `CliErrorRenderStage` renders an `error:` stderr
      line + `typer.Exit(1)`
- [x] 4.4 Tests: same raised exception yields the right shape on each
      transport (`test_operational_contracts.py`, `test_runtime.py`)

## 5. Wire the MCP adapter

- [x] 5.1 `mcp/server.py::_build_one_tool` folds `DISPATCH_PIPELINE`,
      appends `McpErrorRenderStage`, then `install_mcp_signature`
      (the FastMCP `__signature__` rewrite — genuinely MCP-specific,
      kept out of the neutral pipeline)
- [x] 5.2 Deleted the six `_wrap_with_*` functions; `mcp/_wrappers.py`
      now holds only `McpErrorRenderStage` + the signature install. The
      `_ctx_annotation_passthrough` early-exit folded into
      `install_mcp_signature` (it produced the same observable
      signature)
- [x] 5.3 Real-transport coverage green (`test_transport_parity.py`,
      `tests/packages/mcp/` — 59 tests)

## 6. Wire the CLI adapter

- [x] 6.1 `cli/runtime.py` folds `DISPATCH_PIPELINE` + appends
      `CliErrorRenderStage`; `invoke_tool_sync` now takes a
      `ToolBuildSpec`
- [x] 6.2 Deleted `cli/builder.py::_wrap_with_enricher` and the inline
      timeout / ldd / ctx code in `cli/runtime.py`
- [x] 6.3 Cold-start: the CLI path imports no fastmcp
      (`test_dispatch_pipeline_wiring.py`; bench unchanged ~33ms)
- [x] 6.4 CLI parity-gap closed: a router carrying `__aenter__` enters
      on first CLI dispatch (`test_dispatch_pipeline_wiring.py`)

## 7. Wrap-up

- [x] 7.1 OPERATIONAL_CONTRACTS.md: new `Q-Dispatch` section — the
      pipeline, its order, the self-skip rule, per-transport render
- [x] 7.2 ANTIPATTERNS.md #28: duplicating a dispatch concern across
      transport adapters
- [x] 7.3 CHANGELOG `Unreleased`: the shared-dispatch-pipeline restructure
- [x] 7.4 `make lint`, `make test` green (1047 passed, 90.77% cov),
      `make example-smoke` green; `make e2e` has no Makefile target —
      the `test_e2e.py` suites run inside `make test`;
      `openspec validate extract-dispatch-pipeline --strict`
- [x] 7.5 `openspec archive extract-dispatch-pipeline`
