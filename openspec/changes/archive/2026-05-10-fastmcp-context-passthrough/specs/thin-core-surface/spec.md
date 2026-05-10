## MODIFIED Requirements

### Requirement: ToolContext Protocol provides protocol-neutral logging + progress

The library SHALL expose `a2kit.ToolContext` as a lazy re-export of `fastmcp.Context`. The library SHALL NOT define an independent `ToolContext` Protocol in `a2kit/runtime.py` or anywhere else. Tool functions that need any context-bound capability (logging, progress, elicitation, sampling, resource access, session state) SHALL declare a `ctx: a2kit.ToolContext` keyword-only parameter. The transport adapters SHALL bind a context value at invocation time:

- The MCP adapter SHALL pass the live `fastmcp.Context` instance through unwrapped.
- The CLI adapter SHALL bind a `fastmcp.Context`-shaped stub class with the per-method behavior matrix specified in capability `mcp-context-passthrough`.

The narrow surface previously enumerated (`info`, `warning`, `error`, `debug`, `report_progress`) is replaced by the full `fastmcp.Context` surface. Tools that only used the previously-narrow methods are source-compatible.

a2kit SHALL NOT depend on `structlog` for the CLI Context implementation.

#### Scenario: ToolContext usable in both MCP and CLI invocations
- **WHEN** a tool fn declares `ctx: a2kit.ToolContext` and calls `ctx.info("msg", k=v)`
- **THEN** the message is delivered to the MCP wire (in serve mode) OR printed to stderr (in CLI mode), without modification of the tool fn

#### Scenario: ctx parameter excluded from input schema
- **WHEN** a tool fn has both `ctx: a2kit.ToolContext` and other kwonly params
- **THEN** the `--schema` output and Click subcommand options do NOT include `ctx`

#### Scenario: CLI Context emits compact text, not JSON
- **WHEN** a CLI invocation triggers `ctx.info("starting", file="x")`
- **THEN** stderr receives a single line in the form `[ +s.mmm INFO    ] starting file=x`

#### Scenario: No structlog dependency
- **WHEN** the `packages/cli/` source tree is inspected
- **THEN** no module imports `structlog`

#### Scenario: ToolContext aliasing is identity
- **WHEN** a process runs `import a2kit, fastmcp`
- **THEN** `a2kit.ToolContext is fastmcp.Context`

#### Scenario: New FastMCP Context capabilities work without a2kit changes
- **WHEN** a tool calls `await ctx.elicit(...)` or `await ctx.sample(...)` under `<app> serve`
- **THEN** the call reaches the MCP client unchanged, with no a2kit-side adapter code mediating the call
