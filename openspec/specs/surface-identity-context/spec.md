# surface-identity-context Specification

## Purpose
TBD - created by archiving change ctx-surface-identity. Update Purpose after archive.
## Requirements
### Requirement: The per-call scope carries the invoking surface's identity

The per-call `_CallScope` SHALL carry two new fields stamping the surface
that dispatched the call. (It is the neutral per-call spine introduced by
`refound-ldd-on-stdlib-logging`, published on `request_scope`.) The fields
are:

- `surface: str | None` — a short stable identifier of the invoking
  surface (`"mcp"`, `"api"`, `"cli"`, or a future surface's name),
  sourced from the dispatching surface's identity, NOT sniffed from the
  ctx object's runtime type.
- `surface_client_id: str | None` — an OPTIONAL transport/client
  correlation id (e.g. an MCP `client_id`, an HTTP request id), `None`
  when the surface has no such notion.

Both fields SHALL default to `None`. This extension is additive: a scope
constructed without surface arguments behaves exactly as before (both
fields `None`). This requirement EXTENDS the `_CallScope` owned by
`refound-ldd-on-stdlib-logging`; it does not redefine that scope's
existing `ctx` / `call_id` / `tool_name` / span fields.

#### Scenario: scope defaults surface to None when unset

- **GIVEN** a `_CallScope` constructed without surface arguments
- **THEN** `surface` is `None` and `surface_client_id` is `None`
- **AND** the call's existing `call_id` / `tool_name` / span behaviour is unchanged

#### Scenario: bind stamps surface and client id onto the scope

- **GIVEN** the per-call bind entry point is opened with `surface="mcp"` and `surface_client_id="client-1"`
- **WHEN** the published per-call scope is read inside the block
- **THEN** the scope's `surface` is `"mcp"`
- **AND** the scope's `surface_client_id` is `"client-1"`

### Requirement: Every framework dispatch stamps the dispatching surface's identity

The transport-neutral dispatch stage that binds the per-call scope SHALL
resolve the identity of the surface driving the call and stamp it onto the
scope. Resolution SHALL be authoritative from the dispatching path (the
surface that is dispatching knows its own identity), not inferred from the
ctx object's type:

- the MCP dispatch path SHALL stamp `surface = "mcp"`;
- the HTTP dispatch path SHALL stamp `surface = "api"`;
- the CLI dispatch path SHALL stamp `surface = "cli"`.

The surface name SHALL be the dispatching surface's own `name` (the
`Surface.name` ClassVar for registered surfaces; the CLI runtime supplies
`"cli"`). When the surface exposes a client/transport correlation id it
SHALL be stamped as `surface_client_id`; otherwise `surface_client_id`
SHALL be `None`. The stamping SHALL NOT require the tool body to declare
or read anything.

#### Scenario: MCP dispatch stamps "mcp"

- **GIVEN** a tool dispatched via the real MCP transport (`fastmcp.Client(transport=build_mcp_server(app))`)
- **WHEN** the tool body reads the active surface
- **THEN** it reads `"mcp"`

#### Scenario: HTTP dispatch stamps "api"

- **GIVEN** a tool dispatched by posting to `/api/<tool_name>` on the built HTTP app
- **WHEN** the tool body reads the active surface
- **THEN** it reads `"api"`

#### Scenario: CLI dispatch stamps "cli"

- **GIVEN** a tool dispatched via the CLI runtime
- **WHEN** the tool body reads the active surface
- **THEN** it reads `"cli"`

#### Scenario: client id is stamped when the surface exposes one

- **GIVEN** an MCP dispatch whose ctx exposes a `client_id`
- **WHEN** the tool body reads the active surface client id
- **THEN** it equals that `client_id`

#### Scenario: client id is None when the surface has none

- **GIVEN** a dispatch on a surface with no client/transport correlation id
- **WHEN** the tool body reads the active surface client id
- **THEN** it is `None` and the dispatch does not raise

### Requirement: The active surface is readable via a stable accessor

The library SHALL expose `a2kit.log.current_surface() -> str | None` and
`a2kit.log.current_surface_client_id() -> str | None` that return the
active per-call scope's `surface` / `surface_client_id`. Inside a dispatch
they return the stamped value; outside any dispatch (no active scope) they
SHALL return `None` and SHALL NOT raise. Tool bodies and other dispatch
stages SHALL read the surface through these accessors rather than reaching
into `request_scope` internals.

#### Scenario: accessor returns the stamped surface inside a dispatch

- **GIVEN** an active dispatch on the MCP surface
- **WHEN** a tool body calls `a2kit.log.current_surface()`
- **THEN** it returns `"mcp"`

#### Scenario: accessor returns None outside any dispatch

- **GIVEN** code running outside any framework dispatch (no active call scope)
- **WHEN** it calls `a2kit.log.current_surface()`
- **THEN** the result is `None`
- **AND** no exception is raised

### Requirement: Surface identity rides every log record and the durable call-record

The per-call scope filter SHALL inject a `surface` attribute onto every
`LogRecord` handled by the `a2kit` logger, equal to the active scope's
`surface` (or `None` when no dispatch is active). (The filter is
`_CallScopeFilter`, owned by `refound-ldd-on-stdlib-logging`.) The durable
call-record / access-log row produced by the call-log SHALL carry the
`surface` field for the invoking surface. This rides the EXISTING
`CallRecord` / access-log row of `refound-ldd-on-stdlib-logging` — it adds
the `surface` field via the filter and does NOT introduce a new durable
record concept.

#### Scenario: log line carries the surface field

- **GIVEN** a tool emitting an app-log line during an MCP dispatch
- **WHEN** the emitted `LogRecord` is inspected
- **THEN** its `surface` attribute is `"mcp"`

#### Scenario: log record outside a dispatch has surface None

- **GIVEN** a log emission with no active call scope
- **WHEN** the `LogRecord` is inspected
- **THEN** its `surface` attribute is `None`

#### Scenario: durable call-record carries the surface

- **GIVEN** the call-log is enabled and a tool is dispatched over the CLI
- **WHEN** the persisted call-record / access-log row is read
- **THEN** it carries `surface = "cli"`

### Requirement: Surface identity is per-call isolated

Concurrent and nested dispatches SHALL each read only their own stamped
surface, reusing the per-call isolation of `request_scope` (copy-on-write
publish + per-task `copy_context`) established by
`refound-ldd-on-stdlib-logging`. A nested dispatch SHALL report its own
dispatch surface; after the inner dispatch returns, the outer dispatch's
surface SHALL be restored.

#### Scenario: concurrent dispatches on different surfaces do not cross

- **GIVEN** two tool calls running concurrently under `asyncio.gather`, one dispatched over `"mcp"` and one over `"api"`
- **WHEN** each reads `current_surface()`
- **THEN** the first reads `"mcp"` and the second reads `"api"`
- **AND** neither observes the other's surface

#### Scenario: nested dispatch shadows then restores the surface

- **GIVEN** tool A dispatched on `"api"` whose body invokes tool B via the in-process test client
- **WHEN** B runs mid-way
- **THEN** reads inside B resolve to B's dispatch surface
- **AND** reads in A after B returns resolve again to `"api"`

