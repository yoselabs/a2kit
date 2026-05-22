## 1. The dispatch package, protocol, and build spec

- [ ] 1.1 Create `src/a2kit/packages/dispatch/__init__.py` — a
      fastmcp-free package (NOT added to the `A2K-IMPORT-DISCIPLINE`
      allowlist)
- [ ] 1.2 Define `ToolBuildSpec` — a frozen dataclass carrying `app`,
      `router`, `meta`, `descriptor`
- [ ] 1.3 Define the `DispatchStage` protocol: `name: str` and
      `wrap(self, fn, spec: ToolBuildSpec) -> fn`
- [ ] 1.4 Tests: a trivial stage composes; `wrap` returning `fn`
      unchanged is a valid no-op

## 2. The five transport-neutral stages (BDD-first per unit)

- [ ] 2.1 `EnricherStage` — unifies `cli/builder.py::_wrap_with_enricher`
      and `mcp/_wrappers.py`'s enricher wrap
- [ ] 2.2 `LddStateStage` — ldd-state + ctx synthesis, typed against
      the `ToolContext` protocol (fastmcp-free)
- [ ] 2.3 `TimeoutStage` — one mechanism (`anyio.fail_after`);
      self-skips when `meta.extras.timeout_seconds` is unset
- [ ] 2.4 `DispatchHookStage` — self-skips on the default identity hook
- [ ] 2.5 `RouterLazyEnterStage` — self-skips when the router has no
      `__aenter__`; closes the CLI parity gap
- [ ] 2.6 One unit test per stage, each driving the stage directly —
      no `build_mcp_server`, no CLI builder
- [ ] 2.7 Test: `packages/dispatch` imports no `fastmcp` module

## 3. Declare and fold the pipeline

- [ ] 3.1 Define `DISPATCH_PIPELINE: tuple[DispatchStage, ...]`
      innermost-first, with the ordering rationale in its docstring
- [ ] 3.2 Add a fold helper that applies the pipeline to a tool body
- [ ] 3.3 Integration test: the folded chain's nesting order matches
      `DISPATCH_PIPELINE`

## 4. Error capture: neutral stage + per-transport render

- [ ] 4.1 Add a transport-neutral "capture exception → structured
      error" stage in `packages/dispatch`
- [ ] 4.2 MCP adapter: render the structured error as `ToolError(json)`
- [ ] 4.3 CLI adapter: render the structured error as an exit-code
      mapping
- [ ] 4.4 Tests: same raised exception yields the right shape on each
      transport

## 5. Wire the MCP adapter

- [ ] 5.1 Rewrite `mcp/server.py::_build_one_tool` to fold
      `DISPATCH_PIPELINE` and append the MCP error-render stage
- [ ] 5.2 Delete the `_wrap_with_*` functions now living in
      `packages/dispatch`; keep only genuinely MCP-specific code in
      `packages/mcp`
- [ ] 5.3 Real-transport test (`fastmcp.Client(transport=...)`): a
      tool with a timeout + an LDD report behaves correctly end-to-end

## 6. Wire the CLI adapter

- [ ] 6.1 Rewrite `cli/runtime.py` to fold `DISPATCH_PIPELINE` and
      append the CLI error-render stage
- [ ] 6.2 Delete `cli/builder.py::_wrap_with_enricher` and the inline
      timeout / ldd / ctx code in `cli/runtime.py`
- [ ] 6.3 Cold-start benchmark: the CLI path still imports no fastmcp
      (`bench/cli_cold_start.py`)
- [ ] 6.4 CLI e2e: a router carrying `__aenter__` now enters on first
      CLI dispatch — the parity gap is closed

## 7. Wrap-up

- [ ] 7.1 OPERATIONAL_CONTRACTS.md: document the pipeline, its order,
      the self-skip rule, and the per-transport error render
- [ ] 7.2 ANTIPATTERNS.md: entry on duplicating a dispatch concern
      across transport adapters
- [ ] 7.3 CHANGELOG `Unreleased`: note the internal restructure
- [ ] 7.4 `make lint`, `make test`, `make e2e` green;
      `openspec validate extract-dispatch-pipeline --strict`
- [ ] 7.5 `openspec archive extract-dispatch-pipeline`
