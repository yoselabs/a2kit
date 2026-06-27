# Tasks — add-code-mode-config-default

## 1. Config seam (`McpConfig.code_mode`)

- [ ] 1.1 BDD: spec/test that `A2kitConfig().mcp.code_mode` defaults `True`,
      that `A2KIT_MCP__CODE_MODE=false` sets it `False`, and that env beats a
      `McpConfig(code_mode=True)` kwarg (mirror the `structured_output` tests).
- [ ] 1.2 Add `code_mode: bool = Field(default=True, description=…)` to
      `McpConfig` in `config.py`, beside `structured_output`.

## 2. Resolve in `build_mcp_server` (tri-state)

- [ ] 2.1 BDD: with no `code_mode` arg, `build_mcp_server(app)` installs the
      transform iff `config.mcp.code_mode` is True; an explicit
      `code_mode=False` wins over `config.mcp.code_mode=True` and vice-versa.
- [ ] 2.2 Change the `code_mode` param to `bool | None = None`; after
      `runtime = build(app)`, compute
      `effective_code_mode = code_mode if code_mode is not None else bool(runtime.config.mcp.code_mode)`.
- [ ] 2.3 Replace the two `code_mode` reads (FormatRoutingMiddleware
      `consumer=`, and the `if code_mode:` transform block) with
      `effective_code_mode`. Update the docstring.

## 3. Serve CLI flag (absolute pair)

- [ ] 3.1 BDD: `serve --no-code-mode` → `code_mode=False`; `serve --code-mode`
      → `code_mode=True`; neither → `code_mode=None` threaded into `mcp_options`
      (config decides). Assert `--code-mode-off` is gone.
- [ ] 3.2 Replace the `code_mode_off: bool = False` option with
      `code_mode: Optional[bool] = typer.Option(None, "--code-mode/--no-code-mode", …)`;
      set `mcp_options["code_mode"] = code_mode` (no `not …` inversion).

## 4. Invariants to preserve

- [ ] 4.1 `run_code` keeps `build_mcp_server(app, code_mode=True, …)` — assert
      the `a2kit code` path stays sandbox-on regardless of config.
- [ ] 4.2 Default path unchanged: no config + no flag = code mode ON (existing
      code-execution tests stay green).

## 5. Land

- [ ] 5.1 `make test` (or the package's test target) green.
- [ ] 5.2 `openspec validate add-code-mode-config-default --strict`.
- [ ] 5.3 Update `A2KIT_FEEDBACK` adoption note / a2web bridge can flip to
      `code_mode=False` once released.
