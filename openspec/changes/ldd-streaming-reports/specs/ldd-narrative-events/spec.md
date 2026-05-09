## ADDED Requirements

### Requirement: `ctx.event(name, **payload)` emits typed narrative events

The `ToolContext` Protocol SHALL expose
`async def event(self, name: str, **payload: Any) -> None`. Calling
`ctx.event("api.fetched", count=30, source="primary")` SHALL emit a
notification immediately (same channel as `ctx.info` / `ctx.report`) with
`level="event"`, the event `name`, and the structured `payload` dict.

Events are distinct from logs (`ctx.info`) because:
- Events carry a stable `name` (string identifier) — agents can pattern-match
- Payload is structured-by-default — no string formatting, no regex parsing
- Logs answer "what is the process doing"; events answer "what happened"

Events are distinct from reports (`ctx.report`) because:
- Reports are typed mid-flight result chunks (declared via `report=` decorator kwarg)
- Events are unstructured-payload narration with a name (no per-tool schema)

#### Scenario: Tool emits an event with structured payload
- **WHEN** a tool body calls `await ctx.event("fallback.used", reason="primary_timeout", elapsed_ms=2500)`
- **THEN** the MCP client receives a `notifications/message` with `level="event"`, `name="fallback.used"`, `payload={"reason": "primary_timeout", "elapsed_ms": 2500}`

#### Scenario: Empty payload is allowed
- **WHEN** a tool body calls `await ctx.event("phase.started")`
- **THEN** the notification is emitted with an empty payload dict

#### Scenario: CLI runtime renders events to stderr
- **WHEN** the same tool runs in CLI mode (`<app> tool ...`)
- **THEN** each `ctx.event` writes a recognizable stderr line (e.g., `[event] fallback.used reason=primary_timeout elapsed_ms=2500`)

### Requirement: Event name follows dot-namespace convention

Event names SHOULD follow `<area>.<verb>` dot-notation (e.g., `api.fetched`,
`cache.miss`, `auth.refreshed`, `phase.complete`). The runtime SHALL NOT
enforce this — but the streaming_logger example, README docs, and
ANTIPATTERNS entry SHALL recommend it.

#### Scenario: Documentation recommends dot-namespace
- **WHEN** a user reads the README "Logging + progress" section
- **THEN** the dot-namespace convention is shown with concrete examples

### Requirement: Events do not require a decorator kwarg

Unlike `ctx.report`, `ctx.event(...)` SHALL work on any tool — no
`event=` decorator kwarg is required. Events are a free narrative channel.

#### Scenario: ctx.event on a tool without any LDD decorator kwargs
- **WHEN** a plain `@a2kit.read()` tool body calls `await ctx.event("started")`
- **THEN** the event is emitted normally — no error, no warning
