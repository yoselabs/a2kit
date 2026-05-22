# mcp-context-passthrough Specification

## MODIFIED Requirements

### Requirement: LDD wire-format invariants are owned by `a2kit.ldd`

Every event delivered via `a2kit.ldd.event(ctx, name, **kw)` SHALL carry an `elapsed_ms` integer in its structured payload, computed as `int((monotonic() - app_start_monotonic) * 1000)` where `app_start_monotonic` is captured at first emit (or at App `__aenter__` when the lifecycle ran). The CLI rendering SHALL prefix every line with `+s.mmm` relative time using zero-padded three-decimal milliseconds. The human-readable text portion of any LDD line SHALL be capped at 60 characters with `…` elision when truncated. The CLI stub `send_log_message` rendering and the MCP `notifications/message` payload (carrying the same `level`, `logger`, `data`) SHALL agree on the structured `data` field's contents key-for-key — transports may differ on framing only, never on the structured payload.

#### Scenario: elapsed_ms increases monotonically

- **WHEN** two `a2kit.ldd.event` calls happen 50 ms apart in the same process
- **THEN** the second emission's `elapsed_ms` is greater than the first's by approximately 50 (within OS scheduler tolerance)

#### Scenario: text capped at 60 chars

- **WHEN** `a2kit.ldd.info(ctx, "<200-char string>", k=1)` is called
- **THEN** the delivered/rendered text portion is exactly 60 characters with the final character `…`

### Requirement: Ambient ctx is non-None inside any framework dispatch

The MCP wrapper and CLI runtime SHALL bind a non-None `ctx` into the ambient `_LDD_STATE` for every framework-dispatched tool, regardless of whether the tool's body declares `ctx: a2kit.ToolContext`.

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

This requirement establishes the invariant: **inside any framework dispatch, the ambient context resolved from the `_LDD_STATE` ContextVar is non-None**, so every LDD primitive has a live transport context to dispatch against.

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
