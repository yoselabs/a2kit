# router-conventions Specification Delta

## ADDED Requirements

### Requirement: Router opt-in to ambient ctx synthesis

The `Router` base class SHALL expose a class-level boolean attribute
`emits_ldd: ClassVar[bool] = False`. When a `Router` subclass sets
`emits_ldd = True`, the dispatcher SHALL ensure ambient `ctx` is
non-None for every tool dispatched through that router, regardless
of whether the tool signature declares a `ctx: ToolContext`
parameter.

**Existing behaviour preserved (informative, not normative for this
change):** the dispatcher already enters `ldd_state_for_call(...)`
unconditionally on every dispatch (`packages/mcp/server.py:55-99`,
`packages/cli/runtime.py:61-82`). The marker controls only the
**value of ambient `ctx`**, not whether ambient state is entered.

Concretely, when `emits_ldd = True`:

- **MCP transport** — the tool's rewritten wrapper signature SHALL
  include a `ctx` parameter (so fastmcp injects ctx), the wrapper
  SHALL place the injected ctx into the ambient `_LDD_STATE`, and
  the wrapper SHALL NOT pass `ctx` as a kwarg to the tool body
  unless the tool's original signature declared it.
- **CLI transport** — the runtime SHALL synthesize a
  `StderrToolContext()` into ambient `_LDD_STATE` exactly as it
  does today when `ctx_param_name` is set, and SHALL NOT inject
  `ctx` into the tool body kwargs unless the tool's original
  signature declared it.

When `emits_ldd = False` (the default), behaviour SHALL be
unchanged from today: ambient `ctx` is non-None iff the tool
signature declares `ctx` (per the existing
`mcp-context-passthrough` capability). Tools without `ctx` on
non-marker routers continue to raise `AmbientContextMissing` Mode
B (`missing_ctx_param`) when their bodies invoke `a2kit.ldd.*`
primitives.

The marker decision SHALL be cached at tool-registration time on
the tool's `A2KitMeta` (new field, e.g. `ambient_ctx_via_router:
bool = False`). The dispatch hot path SHALL NOT re-introspect the
router or signature per call.

#### Scenario: marker defaults to False

- **GIVEN** `class WebRouter(a2kit.Router): slug = "web"; tools = (fetch,)`
- **WHEN** the app is built
- **THEN** `WebRouter.emits_ldd is False`
- **AND** a tool on `WebRouter` with no `ctx` param that calls
  `a2kit.ldd.event(...)` raises `AmbientContextMissing` Mode B
  (today's behaviour)

#### Scenario: marker set, no ctx in tool signature — MCP

- **GIVEN** `class WebRouter(a2kit.Router): emits_ldd = True; tools = (fetch,)`
  where `fetch` has no `ctx` parameter in its signature
- **WHEN** a real `fastmcp.Client(transport=...)` invokes `fetch`
  and the body calls `await a2kit.ldd.event("evt", k=1)`
- **THEN** the call completes without raising
  `AmbientContextMissing`
- **AND** the framework does NOT inject a `ctx` kwarg into
  `fetch` (signature unchanged from the consumer's perspective)
- **AND** the captured event surfaces on the test client's
  `events` list with the correct payload and `elapsed_ms`

#### Scenario: marker set, no ctx in tool signature — CLI

- **GIVEN** the same setup
- **WHEN** the auto-generated CLI subcommand invokes `fetch` via
  `Container.dispatch`
- **THEN** the runtime synthesizes a `StderrToolContext()` into
  ambient `_LDD_STATE`
- **AND** the tool body's LDD emissions complete without raising
- **AND** `fetch` is NOT called with a `ctx` kwarg

#### Scenario: marker set AND ctx declared — body still receives ctx

- **GIVEN** `class WebRouter(a2kit.Router): emits_ldd = True; tools = (fetch,)`
  where `fetch` declares `ctx: a2kit.ToolContext`
- **WHEN** the dispatcher invokes `fetch`
- **THEN** the ambient `ctx` is the injected one (per marker
  semantics)
- **AND** the `ctx` kwarg is also injected into `fetch` (per
  signature, today's behaviour preserved)

#### Scenario: non-bool marker raises at app build

- **GIVEN** `class BadRouter(a2kit.Router): emits_ldd = "yes"; tools = (...)`
- **WHEN** the app is built
- **THEN** `TypeError` is raised naming `BadRouter` and the
  expected `bool` type

### Requirement: Cross-transport parity for the marker

The Router LDD marker SHALL produce equivalent observable behaviour
on MCP and CLI dispatch paths. A tool on an `emits_ldd=True` router
that emits an LDD event in its body SHALL surface that event on
both transports' capture / sink surfaces, with identical payload
shape.

This is consistent with the `dispatch-lifecycle-wiring` and
`cross-transport-parity-strict` capabilities: both transports
route through `Container.dispatch` and use the same wrapper chain
construction.

#### Scenario: MCP and CLI captures match for the same tool body

- **GIVEN** the marker-on `fetch` tool emitting
  `await a2kit.ldd.event("fetched", url=url)`
- **WHEN** the test invokes `fetch(url="https://example/")`
  through `a2kit.testing.client(app)` (MCP transport) and through
  the CLI runtime
- **THEN** both captures contain an event with
  `name="fetched"`, `payload={"url": "https://example/"}` and
  comparable `elapsed_ms`
