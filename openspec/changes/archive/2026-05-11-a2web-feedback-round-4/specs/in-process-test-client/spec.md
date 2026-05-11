## ADDED Requirements

### Requirement: Null context shim for unit-testing internal functions

The library SHALL expose `a2kit.testing.null_context() -> ToolContext` returning a no-op object that satisfies the `fastmcp.Context` interface. Every public method of `fastmcp.Context` SHALL be present on the shim. Async methods SHALL return immediately without I/O. Properties (`request_id`, `client_id`, etc.) SHALL return fixed sentinel values documented in the docstring.

The shim is for **unit tests of internal phase functions that bypass `a2kit.testing.client`**. Production code SHOULD take `ctx: ToolContext` (non-Optional) and tests SHOULD construct one of these shims rather than passing `None`.

#### Scenario: Null context can be passed to a function expecting ToolContext

- **GIVEN** an async function `async def fetch_tier(ctx: a2kit.ToolContext, url: str) -> str` that calls `await ldd.event(ctx, "tier.started", url=url)` internally
- **WHEN** a unit test calls `await fetch_tier(a2kit.testing.null_context(), "https://...")`
- **THEN** the call succeeds, the event call is a silent no-op, and no `AttributeError` is raised

#### Scenario: All logging methods are no-ops

- **WHEN** test code calls `await ctx.info("hi")`, `await ctx.warning("hi")`, `await ctx.error("hi")`, `await ctx.debug("hi")` on a null context
- **THEN** all calls return None and produce no observable side effect

#### Scenario: report_progress is a no-op

- **WHEN** test code calls `await ctx.report_progress(0.5, 1.0)` on a null context
- **THEN** the call returns None and produces no observable side effect

#### Scenario: request_id returns a fixed sentinel

- **WHEN** test code reads `ctx.request_id` on a null context
- **THEN** the value is the literal string `"null-context"`

### Requirement: null_context is in a2kit.testing alongside client

The `a2kit.testing` module SHALL re-export `null_context` (alongside `client` and `TestClient`). The shim implementation SHALL live in `src/a2kit/packages/testing/null_context.py`.

#### Scenario: Re-export

- **WHEN** test code runs `from a2kit.testing import null_context`
- **THEN** the import succeeds
