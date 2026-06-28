## MODIFIED Requirements

### Requirement: `authorize=` enforcement is uniform across surfaces

The `authorize=` kwarg accepted by `@a2kit.read` / `@a2kit.write` / `@a2kit.list_` / `@app.api.<method>` / `@app.mcp.<feature>` SHALL be enforced uniformly across all dispatch surfaces. For projection verbs and `@app.api.<method>` the gate runs as `AuthorizeGateStage` inside the dispatch pipeline (HTTP path additionally bridged by `_apply_authorize_gate` in `packages/http/build.py`). For `@app.mcp.<feature>` — which bypasses the dispatch pipeline by construction — the same gate SHALL be applied at registration time to the substrate-wrapped callable, reusing the one `AuthorizeGateStage` evaluation logic, so the escape hatch is not an authorization gap. The gate SHALL resolve the callable's parameters through `Container.call_scope` so authors can annotate `principal: Principal` plus any container-known type. A falsy return SHALL raise `AuthorizationDenied(reason, callable_name)` on every surface; HTTP maps it to 403 with body `{"error": "authorization_denied", "reason": ..., "callable": ...}`; MCP renders the same shape through `McpErrorRenderStage` into the `ToolError` JSON payload.

#### Scenario: Same authorize= callable denies on both surfaces uniformly

- **GIVEN** `@a2kit.read(authorize=lambda *, principal: "admin" in principal.scopes) async def admin_op(...): ...` exposed on both surfaces
- **WHEN** invoked via HTTP and via MCP with the same non-admin Principal
- **THEN** HTTP returns 403 with `{"error": "authorization_denied", ...}`
- **AND** MCP raises `ToolError` carrying the same structured fields
- **AND** the tool body is never invoked in either case

#### Scenario: `@app.mcp.*` enforces authorize= at registration

- **GIVEN** `@app.mcp.tool(name="admin_dash", authorize=lambda *, principal: "admin" in principal.scopes)`
- **WHEN** the tool is invoked via MCP with a non-admin Principal
- **THEN** it raises `AuthorizationDenied` rendered through `McpErrorRenderStage` into the `ToolError` JSON payload
- **AND** the tool body is never invoked

#### Scenario: An authorized Principal passes the `@app.mcp.*` gate

- **GIVEN** the same `@app.mcp.tool(authorize=...)` registration
- **WHEN** the tool is invoked via MCP with an admin Principal
- **THEN** the gate passes and the tool body runs normally
