"""Round-4 Soft B: null ToolContext shim for unit-testing internal functions.

Gherkin scenarios (mirroring `specs/in-process-test-client/spec.md` ADDED
section "Null context shim for unit-testing internal functions"):

  Scenario: Null context can be passed to a function expecting ToolContext
    GIVEN an async fn taking ctx: a2kit.ToolContext that calls ldd.event(...)
    WHEN the fn is called with a2kit.testing.null_context()
    THEN no AttributeError, the call returns normally

  Scenario: All logging methods are no-ops
    GIVEN a null context
    THEN await ctx.info / warning / error / debug return None silently

  Scenario: report_progress is a no-op
    THEN await ctx.report_progress(0.5, 1.0) returns None silently

  Scenario: request_id returns a fixed sentinel
    THEN ctx.request_id == "null-context"

  Scenario: ldd.event accepts the null context
    THEN await event(null_ctx, "x", k=1) raises nothing
"""

from __future__ import annotations

import asyncio

import a2kit
from a2kit.log import info
from a2kit.packages.log.scope import bind_call_scope
from a2kit.testing import null_context


def test_null_context_is_toolcontext_shaped() -> None:
    """Has the public methods of fastmcp.Context (re-exported as a2kit.ToolContext)."""
    ctx = null_context()
    # Logging surface.
    assert hasattr(ctx, "info")
    assert hasattr(ctx, "warning")
    assert hasattr(ctx, "error")
    assert hasattr(ctx, "debug")
    assert hasattr(ctx, "log")
    # Progress.
    assert hasattr(ctx, "report_progress")
    # State surface.
    assert hasattr(ctx, "set_state")
    assert hasattr(ctx, "get_state")
    # MCP-side surface (no-op in null).
    assert hasattr(ctx, "read_resource")
    assert hasattr(ctx, "elicit")


def test_logging_methods_are_noops() -> None:
    ctx = null_context()

    async def _go() -> None:
        await ctx.info("hi")
        await ctx.warning("hi")
        await ctx.error("hi")
        await ctx.debug("hi")
        await ctx.log("hi", level="info")

    asyncio.run(_go())


def test_report_progress_is_noop() -> None:
    ctx = null_context()
    asyncio.run(ctx.report_progress(0.5, 1.0))
    asyncio.run(ctx.report_progress(1.0, None, "done"))


def test_request_id_is_sentinel() -> None:
    ctx = null_context()
    assert ctx.request_id == "null-context"


def test_log_info_accepts_null_context() -> None:
    ctx = null_context()

    async def _go() -> None:
        with bind_call_scope(ctx=ctx, tool_name="t"):
            await info("x", k=1)

    asyncio.run(_go())  # must not raise


def test_null_context_satisfies_toolcontext_annotation() -> None:
    """A function annotated `ctx: a2kit.ToolContext` accepts a null context at runtime."""

    async def fn(ctx: a2kit.ToolContext) -> str:
        await ctx.info("called")
        return "ok"

    result = asyncio.run(fn(null_context()))
    assert result == "ok"


def test_mcp_only_methods_are_noops_too() -> None:
    """Null shim does NOT raise MCPOnlyError on sample/list_*; returns harmless defaults."""
    ctx = null_context()

    async def _go() -> None:
        # These would normally raise MCPOnlyError on the CLI stub. The null
        # shim returns None / [] instead so unit tests of code paths that touch
        # them don't blow up.
        assert await ctx.sample() is None
        assert await ctx.sample_step() is None
        assert await ctx.list_resources() == []
        assert await ctx.list_prompts() == []
        assert await ctx.list_roots() == []
        assert await ctx.get_prompt("foo") is None
        assert await ctx.send_notification({"x": 1}) is None
        assert await ctx.read_resource("file:///nope") == ""
        assert await ctx.elicit("prompt") is None

    asyncio.run(_go())
