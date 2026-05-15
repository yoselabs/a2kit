# mcp-context-passthrough Specification Delta

## ADDED Requirements

### Requirement: Ambient ctx is non-None inside any framework dispatch

The MCP wrapper and CLI runtime SHALL bind a non-None `ctx` into the
ambient `_LDD_STATE` for every framework-dispatched tool, regardless
of whether the tool's body declares `ctx: a2kit.ToolContext`.

Implementation:

- **MCP**: the rewritten wrapper signature SHALL always include a
  ctx Parameter (named `_a2kit_ctx` when the tool body did not
  declare one) annotated `fastmcp.Context`. fastmcp injects the
  live context via its standard introspection. The wrapper extracts
  ctx from kwargs into ambient state.
- **CLI**: the runtime SHALL synthesize `StderrToolContext()` for
  ambient binding even when the tool body does not declare ctx.

In both transports, the ctx kwarg SHALL be passed to the tool body
ONLY when the tool's *original* signature declared it. The
synthesized `_a2kit_ctx` Parameter (MCP) is a framework-internal
mechanism for ambient binding and SHALL NOT leak into tool body
kwargs.

This requirement establishes the invariant: **inside any framework
dispatch, `a2kit.ldd.current_ctx()` returns a non-None value**.

#### Scenario: MCP transport — tool without ctx param emits LDD

- **GIVEN** a tool `async def fetch(*, url: str) -> dict: await a2kit.ldd.event("fetch", url=url); return {}` registered on a Router
- **WHEN** a real `fastmcp.Client(transport=...)` invokes `fetch(url="https://example/")`
- **THEN** the invocation completes without raising `AmbientContextMissing`
- **AND** the captured event surfaces on the test client's `events` list with name `"fetch"` and payload `{"url": "https://example/"}`
- **AND** the tool body received no `ctx` kwarg (its signature did not declare one)

#### Scenario: CLI runtime — tool without ctx param emits LDD

- **GIVEN** the same tool shape
- **WHEN** invoked via the CLI runtime
- **THEN** the invocation completes without raising
- **AND** the stderr capture contains an LDD-formatted line matching the event

#### Scenario: Tool with ctx param — today's behaviour preserved

- **GIVEN** a tool `async def scrape(*, target: str, ctx: a2kit.ToolContext) -> dict: ...`
- **WHEN** invoked under any transport
- **THEN** the tool body receives the live ctx as a kwarg (unchanged from today)
- **AND** ambient state has the same ctx instance

#### Scenario: Synthesized ctx name does not collide with consumer params

- **GIVEN** a Router with tools declaring various param names (`url`, `target`, `state`, etc.)
- **WHEN** the framework synthesizes the `_a2kit_ctx` Parameter in rewritten signatures
- **THEN** no consumer-defined param name collides (the `_a2kit_*` prefix is reserved by the framework)
- **AND** the synthesized parameter never appears in any tool body's kwargs
