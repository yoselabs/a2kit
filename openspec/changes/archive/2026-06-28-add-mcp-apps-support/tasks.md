## 1. Close the `authorize=` enforcement drift on `@app.mcp.*` (Track 2)

- [x] 1.1 Write failing test(s) in `tests/packages/mcp/test_server.py` (mirror rule): `@app.mcp.tool(authorize=...)` invoked via MCP with a non-admin Principal denies with the `AuthorizationDenied` envelope and the body never runs; plus the authorized-Principal-passes case.
- [x] 1.2 Reuse the existing shared `_run_authorize_gate(authorize, container)` helper (already exported from `a2kit.packages.dispatch` and used by `AuthorizeGateStage`) — no extraction needed; one auth semantics across surfaces (AGENTS.md §2).
- [x] 1.3 In `server.py::_register_mcp_surface`, apply the captured `reg.authorize` to the substrate-wrapped callable (new `_gate_substrate_callable`) before `server.tool/resource/prompt`; denial converts `AuthorizationDenied` → `ToolError` so `TypedErrorEnvelopeMiddleware` renders the standard `{"error": envelope}`.
- [x] 1.4 1.1 passes; `tests/packages/mcp/test_server.py` + `tests/test_wire_error_envelope.py` + `tests/packages/dispatch/test_authorize_gate.py` green.

## 2. Prove the MCP Apps wire capability (Track 1 — test)

- [x] 2.1 Wire test in `tests/packages/mcp/test_server.py` asserting: `@app.mcp.tool(app=AppConfig(resourceUri="ui://..."))` → `_meta.ui.resourceUri`; `@app.mcp.resource(uri="ui://...", app=AppConfig(csp=...))` → MIME `text/html;profile=mcp-app` + `ui.csp` meta + byte-identical bundle read-back; building the server pulls no `prefab` into `sys.modules`; `app=True` forwards the `ui` payload. (Test the wire, not pixels.)
- [x] 2.2 Confirmed 2.1 passes against current code with NO src change — the `@app.mcp.*` verbatim forward already serves MCP Apps. Ratification, not new code.

## 3. Working example

- [x] 3.1 Created `examples/mcp_app/` — `@app.mcp.tool(app={"resourceUri": ...})` shell, `@app.mcp.resource` HTML bundle (with CSP), and a projection data verb `@a2kit.read(surfaces=("mcp",))` the iframe calls back. Inline HTML (no bundler / no UI-framework dep / no `fastmcp.apps` import — dict `app=` form). Passes ty + ruff + a2kit static lint.
- [x] 3.2 Verified the example builds via `build_mcp_server` (shell `meta.ui.resourceUri`, resource MIME, data verb all correct) and `--help` runs; added it to the `examples:` Make smoke target. Not in the cold-start parametrize list, so no budget regression.

## 4. Docs + decision record

- [x] 4.1 Wrote `docs/patterns/mcp-apps.md`: the `@app.mcp.*` escape-hatch pattern, custom HTML + Prefab-optional (never-bind-to-Prefab), the shell-vs-data-verb split, and the test-the-wire-not-pixels posture. Only resolvable `a2kit.*` dotted symbols.
- [x] 4.2 Wrote `docs/adr/0031-mcp-apps-support.md` (accepted): standard-first / Prefab-optional / mechanism-not-UI (Roles 1–2 yes, Role 3 no); records the `authorize=` enforcement fix and the deferred Posture-B trigger. Regenerated `INDEX.md` (`make adr-index`); `make adr-check` clean.

## 5. Validate and land

- [x] 5.1 Real project gates green: ruff clean, `ty check src/` clean, full pytest **1618 passed** / 90.54% cov (incl. cold-start + no-fastmcp guards). NOTE: `make check`'s `ty check tests/` reports 27 **pre-existing** diagnostics (identical count on committed HEAD with this change stashed — a2kit dynamic-attribute false-positives in untouched files); this change adds zero new ty diagnostics.
- [x] 5.2 Added CHANGELOG `0.47.0` section (MCP Apps support + the `authorize=`-on-`@app.mcp.*` enforcement fix, flagged behavior-tightening); bumped `pyproject` 0.46.0 → 0.47.0; refreshed `uv.lock` self-entry.
- [x] 5.3 Strict-validated; committed (ae171eb) + tagged v0.47.0; archived as 2026-06-28-add-mcp-apps-support (mcp-apps spec created, tool-authorization updated).
