## ADDED Requirements

### Requirement: `AmbientContextMissing` distinguishes pre-dispatch vs missing-ctx-param failure modes

When an LDD primitive raises `AmbientContextMissing`, the exception message SHALL distinguish two failure modes so the author sees an actionable hint at the call site:

- **Mode A — no active dispatch.** The dispatcher's ambient `ldd_state_for_call` scope is not in effect (contextvar unset). This covers module-import-time calls, pre-dispatch lifecycle code, and orphan task contexts. The message SHALL state "called outside an active tool dispatch" and point at the standard remediation (move into a tool body, or use the test harness's `ldd_state_for_call(ctx=...)` context manager).

- **Mode B — dispatch active but tool body did not declare `ctx`.** The contextvar IS set (the dispatcher entered a scope) but `state.ctx is None` because the tool function does not declare a `ctx: a2kit.ToolContext` parameter. The message SHALL state that the tool body called an LDD primitive without declaring the `ctx` parameter, and SHALL instruct the author to add `ctx: a2kit.ToolContext` to the tool signature (the dispatcher will bind it ambient) or remove the LDD call.

Both modes SHALL raise the same exception class (`AmbientContextMissing`); only the message differs.

#### Scenario: Mode A — pre-dispatch call

- **GIVEN** code at module top level calling `a2kit.ldd.event("x", k=1)`
- **WHEN** the module is imported
- **THEN** `AmbientContextMissing` is raised
- **AND** the message contains "called outside an active tool dispatch"
- **AND** the message points at the test harness's `ldd_state_for_call(ctx=...)` context manager as a remediation

#### Scenario: Mode B — tool body without ctx parameter

- **GIVEN** a tool `async def t(self, *, x: int) -> int:` (no `ctx` declared) whose body calls `await a2kit.ldd.event("y", k=1)`
- **WHEN** the tool runs under any transport
- **THEN** `AmbientContextMissing` is raised
- **AND** the message identifies the failure as "tool body did not declare `ctx: a2kit.ToolContext` as a parameter"
- **AND** the message instructs the author to add the `ctx` parameter or remove the LDD call

#### Scenario: Tool body with ctx parameter still works

- **GIVEN** a tool `async def t(self, *, ctx: a2kit.ToolContext, x: int) -> int:` whose body calls `await a2kit.ldd.event("y", k=1)`
- **WHEN** the tool runs under any transport
- **THEN** no exception is raised
- **AND** the event is delivered normally
