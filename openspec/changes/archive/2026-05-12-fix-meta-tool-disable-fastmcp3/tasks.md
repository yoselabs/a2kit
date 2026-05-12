## 1. Prerequisites & repro

- [x] 1.1 Baseline green: `make lint` + `make test`. Record test count.
- [x] 1.2 Reproduce the `NotImplementedError` against `fastmcp 3.2.4`:
      construct an `App(health_tool=True)`, call
      `build_mcp_server(app)`, confirm crash with the documented
      message. Capture for the regression test in §3.
- [x] 1.3 Confirm no conflict with in-flight change
      `align-context-method-signatures` — that one touches
      `mcp-context-passthrough`, not the registration loop.

## 2. Call-site fix in `build_mcp_server`

- [x] 2.1 In `src/a2kit/packages/mcp/server.py`, change the import
      `from fastmcp.tools.tool import FunctionTool` to
      `from fastmcp.tools.function_tool import FunctionTool`.
      Keep the import at its current placement (local vs. module
      top) per the cold-start gate in `tests/test_cold_start.py`;
      do not add re-export shims for the legacy path.
- [x] 2.2 Remove the per-tool `if is_meta: tool.disable()` branch
      (current lines 319-320).
- [x] 2.3 Track which registered tool names are `_meta.*` while
      iterating, or rely on the tag-based selector. After the
      registration loop (and before middleware registration to
      keep ordering stable), call
      `server.disable(tags={"_meta"})` once.
- [x] 2.4 Add the registration-time guard (D3): attach an
      `a2kit.internal=True` sentinel to the metadata extras of
      a2kit-built `_meta.*` tools (currently just `_meta.health`
      in `a2kit/packages/health.py` or wherever it's registered);
      in the loop, raise `ValueError` if a tool is `_meta.*`
      without the sentinel, naming the reserved-namespace contract.

## 3. Regression test

- [x] 3.1 New module `tests/test_meta_tool_disable.py`.
- [x] 3.2 Test `test_build_mcp_server_with_health_tool_does_not_raise`:
      construct `App(name="t", health_tool=True)` + one ordinary
      `@app.read` tool; call `build_mcp_server(app)`; assert no
      exception.
- [x] 3.3 Test `test_meta_health_present_but_disabled`:
      inspect the FastMCP server's tool registry — `_meta.health`
      MUST be registered; the visibility-transform stack MUST
      include the `tags={"_meta"}` disable transform.
- [x] 3.4 Test `test_default_list_tools_omits_meta`:
      use `a2kit.testing.client(app)` (or the lowest available
      level that exercises FastMCP's `list_tools`); assert no
      tool named `_meta.*` appears in the default listing.
- [x] 3.5 Test `test_meta_health_not_callable_via_mcp_wire`:
      via the FastMCP server's `_call_tool_mcp` path, call
      `_meta.health` by exact name; assert `NotFoundError`
      (FastMCP-3's visibility transform blocks both list and
      call). CLI surface is verified separately by the existing
      `<app> health` CLI test, if any.
- [x] 3.6 Test `test_user_meta_tool_rejected_at_build`:
      construct an app with a tool whose metadata was forced to
      a `_meta.*` name without the `a2kit.internal` sentinel
      (using the metadata-mutation path the codebase already
      exposes for tests); call `build_mcp_server`; assert
      `ValueError` with the reserved-namespace message.
- [x] 3.7 Test `test_no_fastmcp_deprecation_warning_on_build`:
      capture warnings with
      `warnings.catch_warnings(record=True)` around
      `build_mcp_server`; assert no `FastMCPDeprecationWarning`
      from the `fastmcp.tools.tool` legacy path.

## 4. Documentation

- [x] 4.1 Add a `## The _meta.* tool namespace` section to
      `OPERATIONAL_CONTRACTS.md` (≤200 words) covering: closed
      namespace; MCP `list_tools` exclusion + name-callable
      preservation; CLI `_meta` subcommand surfacing; rejection
      rule for user `_meta.*` tools. Cross-link to the
      `health-probe` spec for the existing reservation requirement.
- [x] 4.2 Update `CHANGELOG.md`: one line under the next-release
      section noting the FastMCP-3 `_meta` disable fix and the
      `FunctionTool` import migration.

## 5. Validation & release

- [x] 5.1 `openspec validate fix-meta-tool-disable-fastmcp3 --strict`
      passes.
- [x] 5.2 `make lint` + `make test` green; new tests counted.
- [x] 5.3 `uv run python -W error::DeprecationWarning -c "from a2kit.packages.mcp.server import build_mcp_server"`
      succeeds (no deprecation surfaces at import).
- [ ] 5.4 Cut release `v0.28.1` per existing cadence. Tag,
      changelog entry, PyPI publish via existing release flow.
      (User-driven; not done in this session.)
- [ ] 5.5 Notify a2web (round-6 reporter): release is out, no
      downstream pin needed. (Depends on 5.4.)

## 6. Follow-ups (NOT in this change — track separately)

- [ ] 6.1 Open a separate change proposal for `@app.async_resource`
      (round-5 gap 1).
- [ ] 6.2 Open a separate change proposal for ambient `ctx` via
      ContextVar (round-5 gap 2).
- [ ] 6.3 Open a separate change proposal for
      `app.testing.override(T, fake)` (round-5 gap 3).
- [ ] 6.4 Open a separate change proposal for `a2kit.Param`
      docstring-pull / verbosity (round-5 gap 4).
- [ ] 6.5 Open a separate change proposal for wire-payload
      inspection on `a2kit.testing.client` (round-6 friction 2).
- [ ] 6.6 Decide whether to surface FastMCP 3 component
      versioning (`@v1` keys) for a2kit's own tool surface; spike
      first, then propose if useful.
