## MODIFIED Requirements

### Requirement: Decoration-time invariant — rewritten MCP signature contains ctx

When the MCP runtime wraps a tool function with the dispatch-hook signature rewrite, the rewritten `__signature__` SHALL contain the tool's ctx parameter name whenever `A2KitMeta.context_param_name` is non-None for that tool. The rewrite SHALL raise `a2kit.exceptions.A2KitContextBindingBroken` at App-construction time if the invariant does not hold.

The check is framework-internal: user code cannot cause it to fire. Its purpose is to catch wrapper-chain regressions immediately when the App is constructed, before any tool call reaches a real transport.

#### Scenario: App fails to build when wrapper chain drops ctx

- **GIVEN** a hypothetical regression in `_wrap_with_dispatch_hook` that produces a rewritten signature missing the ctx parameter
- **WHEN** router registration runs (the App composes a router whose tool has `ctx: a2kit.ToolContext`) and the MCP wrapper chain is assembled for that tool
- **THEN** the call raises `A2KitContextBindingBroken` with `fn_name` and `ctx_param_name` attributes
- **AND** the error message identifies the regression as framework-internal and instructs the user to file an issue

#### Scenario: Normal apps build without raising

- **GIVEN** a correctly-functioning a2kit installation (post fix-mcp-dispatch-strips-ctx)
- **WHEN** any App with any tool combination is built
- **THEN** no `A2KitContextBindingBroken` exception is raised
