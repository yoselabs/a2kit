# mcp-context-passthrough — fix-mcp-dispatch-strips-ctx delta

## MODIFIED Requirements

### Requirement: ctx parameter excluded from input schema

When a tool function declares a parameter typed `a2kit.ToolContext` (i.e. `fastmcp.Context`), schema generation, CLI option synthesis, and MCP wire-input synthesis SHALL exclude that parameter from the **user-facing input surface** — that is, the agent-supplied `inputSchema` over MCP and the `--option`-style command-line flags over CLI.

The exclusion SHALL apply only to the user-facing input surface. The **internal** call-time signature that the MCP transport introspects to bind framework-supplied parameters (notably the live `fastmcp.Context`) SHALL retain the ctx parameter so that FastMCP injects it at dispatch time. Wrapper code that rewrites a tool's `__signature__` for FastMCP introspection MUST include the ctx parameter when the tool declares one.

#### Scenario: ctx omitted from MCP schema

- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext, name: str) -> str`
- **WHEN** the MCP tool schema is generated
- **THEN** the schema input properties include `name` only

#### Scenario: ctx omitted from CLI options

- **GIVEN** the same tool registered in a CLI app
- **WHEN** the user runs `<app> tasks t --help`
- **THEN** the option list shows `--name` and not `--ctx`

#### Scenario: ctx preserved in internal call-time signature over MCP

- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext, name: str, state: AppState) -> str` where `state: AppState` is supplied via `app.singleton(AppState, ...)`
- **WHEN** the MCP transport assembles the wrapper chain for `t` and FastMCP introspects the outermost wrapped function
- **THEN** the introspected signature contains both `name` and `ctx` (FastMCP-injected) as keyword-only parameters
- **AND** an `mcp` `tools/call` with `arguments={"name": "x"}` reaches `t`'s body with all three kwargs (`name`, `ctx`, `state`) bound and returns successfully

#### Scenario: ctx and container-DI combine cleanly over MCP

- **GIVEN** a tool that declares both `state: T` (container-resolved) AND `ctx: a2kit.ToolContext`
- **WHEN** the tool is invoked via `fastmcp.Client(transport=build_mcp_server(app))`
- **THEN** the response is a successful tool result (NOT `{isError: true}`)
- **AND** the body received both `state` (from the container) and `ctx` (from FastMCP)

## ADDED Requirements

### Requirement: Decoration-time invariant — rewritten MCP signature contains ctx

When the MCP runtime wraps a tool function with the dispatch-hook signature rewrite, the rewritten `__signature__` SHALL contain the tool's ctx parameter name whenever `A2KitMeta.context_param_name` is non-None for that tool. The rewrite SHALL raise `a2kit.exceptions.A2KitContextBindingBroken` at App-construction time if the invariant does not hold.

The check is framework-internal: user code cannot cause it to fire. Its purpose is to catch wrapper-chain regressions immediately when the App is constructed, before any tool call reaches a real transport.

#### Scenario: App fails to build when wrapper chain drops ctx

- **GIVEN** a hypothetical regression in `_wrap_with_dispatch_hook` that produces a rewritten signature missing the ctx parameter
- **WHEN** `App.add_router` runs and the MCP wrapper chain is assembled for a tool with `ctx: a2kit.ToolContext`
- **THEN** the call raises `A2KitContextBindingBroken` with `fn_name` and `ctx_param_name` attributes
- **AND** the error message identifies the regression as framework-internal and instructs the user to file an issue

#### Scenario: Normal apps build without raising

- **GIVEN** a correctly-functioning a2kit installation (post fix-mcp-dispatch-strips-ctx)
- **WHEN** any App with any tool combination is built
- **THEN** no `A2KitContextBindingBroken` exception is raised

### Requirement: Optional-ctx annotation form rejected at decoration time

A tool function's ctx parameter annotation MUST be exactly `a2kit.ToolContext` (or equivalent re-export of `fastmcp.Context`). Annotations of the form `ctx: ToolContext | None`, `ctx: Optional[ToolContext]`, or `ctx: Union[ToolContext, None]` SHALL be rejected at decoration time with `a2kit.exceptions.A2KitInvalidContextAnnotation`.

The rejection enforces the runtime invariant that ctx is always bound by the dispatcher when declared: there is no transport or test path that produces a `None` ctx for a declared parameter. The Optional form is misleading typing with no corresponding runtime semantics.

#### Scenario: Optional ctx rejected

- **GIVEN** a tool body `async def t(*, msg: str, ctx: a2kit.ToolContext | None = None) -> dict`
- **WHEN** `@a2kit.read()` decorates the function
- **THEN** the decoration raises `A2KitInvalidContextAnnotation`
- **AND** the message identifies the parameter name and includes the hint "ctx is always bound by the dispatcher when declared; drop '| None' from the annotation, or remove ctx entirely if the tool does not need it."

#### Scenario: Plain ToolContext accepted

- **GIVEN** a tool body `async def t(*, msg: str, ctx: a2kit.ToolContext) -> dict`
- **WHEN** `@a2kit.read()` decorates the function
- **THEN** the decoration succeeds and `A2KitMeta.context_param_name == "ctx"`

#### Scenario: No ctx declaration accepted

- **GIVEN** a tool body `async def t(*, msg: str) -> dict`
- **WHEN** `@a2kit.read()` decorates the function
- **THEN** the decoration succeeds and `A2KitMeta.context_param_name is None`

### Requirement: Transport-parity matrix

A test suite SHALL pin the contract that a tool's behavior is identical across the CLI and MCP transports for the four canonical declaration combinations of `(state-DI present, ctx-DI present)`. The suite SHALL drive the MCP transport through `fastmcp.Client(transport=build_mcp_server(app))` (not the in-process test client) so the full production wrapper chain — including `_wrap_with_dispatch_hook`'s signature rewrite and `_wrap_with_ldd_state`'s ambient binding — is exercised. The suite SHALL assert both successful-payload structural equality and exact exception-class parity on misuse cases.

#### Scenario: All four declaration combos pass parity

- **GIVEN** the test fixture App with four tools: `tool_none` (neither), `tool_state` (state only), `tool_ctx` (ctx only), `tool_both` (both)
- **WHEN** each tool is invoked over both CLI and MCP with the same kwargs
- **THEN** the returned payloads are structurally equal across transports for every tool

#### Scenario: Error class parity for unknown-kwarg misuse

- **GIVEN** a tool `tool_none` invoked with an unknown kwarg `extra="y"`
- **WHEN** invoked on each transport
- **THEN** both transports surface an error of the same Python exception class (`TypeError`)
