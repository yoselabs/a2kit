"""v0.18 — `a2kit.get_tool_logger` + structlog contextvar binding middleware.

Covers:
- ``get_tool_logger`` returns a structlog logger bindable to context.
- Logging middleware binds ``tool.name`` and ``tool.connection`` into
  ``structlog.contextvars`` for the duration of the inner call.
- Bindings are isolated across concurrent tool invocations (no leakage).
- Bindings unwind on success and on exception.
- ``bind_tool_context`` helper exposes the same binding behaviour for
  explicit-chain users.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import structlog
from structlog.testing import LogCapture

import a2kit
from a2kit.logging import bind_tool_context, get_tool_logger
from a2kit.middleware._chain import ToolContext, compose
from a2kit.middleware._logging import structlog_context_factory


def test_get_tool_logger_returns_bound_logger() -> None:
    log = get_tool_logger("a2kit.test")
    # Should expose the standard structlog API.
    assert hasattr(log, "info")
    assert hasattr(log, "bind")


def test_get_tool_logger_exported_from_top_level() -> None:
    assert a2kit.get_tool_logger is get_tool_logger


def test_logger_emits_bound_context_via_middleware(log_output: LogCapture) -> None:
    """Records emitted inside the chain carry ``tool.name`` + ``tool.connection``."""
    mw = structlog_context_factory()
    log = get_tool_logger("test.tool")

    async def inner(**_: Any) -> str:
        log.info("inside")
        return "ok"

    ctx = ToolContext(
        tool_name="my_tool",
        verb="read",
        write=False,
        capabilities=frozenset(),
        state={"connection_key": ("acme", "prod")},
    )
    handler = compose([mw], inner, ctx)
    result = asyncio.run(handler())
    assert result == "ok"
    [event] = log_output.entries
    assert event["event"] == "inside"
    assert event["tool.name"] == "my_tool"
    assert event["tool.connection"] == "acme-prod"


def test_logger_omits_connection_when_absent(log_output: LogCapture) -> None:
    mw = structlog_context_factory()
    log = get_tool_logger("test.tool")

    async def inner(**_: Any) -> None:
        log.info("hello")

    ctx = ToolContext(
        tool_name="solo",
        verb="tool",
        write=False,
        capabilities=frozenset(),
        state={"connection_key": None},
    )
    handler = compose([mw], inner, ctx)
    asyncio.run(handler())
    [event] = log_output.entries
    assert event["tool.name"] == "solo"
    assert "tool.connection" not in event


def test_bindings_unwind_on_exception(log_output: LogCapture) -> None:
    """After an inner-raised exception, no bindings leak into subsequent logs."""
    mw = structlog_context_factory()
    log = get_tool_logger("test.tool")

    async def boom(**_: Any) -> None:
        raise RuntimeError("boom")

    ctx = ToolContext(
        tool_name="failing",
        verb="tool",
        write=False,
        capabilities=frozenset(),
        state={"connection_key": ("k",)},
    )
    handler = compose([mw], boom, ctx)
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(handler())

    # Emit *outside* the chain — should NOT carry tool.name/tool.connection.
    log.info("after")
    [event] = log_output.entries
    assert event["event"] == "after"
    assert "tool.name" not in event
    assert "tool.connection" not in event


def test_bindings_isolated_across_concurrent_calls(log_output: LogCapture) -> None:
    """Two concurrent tool invocations see only their own bindings."""
    mw = structlog_context_factory()
    log = get_tool_logger("test.tool")

    async def make_inner(label: str):
        async def inner(**_: Any) -> None:
            # Yield to scheduler so the other task runs in between.
            await asyncio.sleep(0)
            log.info(label)

        return inner

    async def run_two() -> None:
        a_inner = await make_inner("A")
        b_inner = await make_inner("B")
        ctx_a = ToolContext(
            tool_name="tool_A",
            verb="read",
            write=False,
            capabilities=frozenset(),
            state={"connection_key": ("conn_A",)},
        )
        ctx_b = ToolContext(
            tool_name="tool_B",
            verb="read",
            write=False,
            capabilities=frozenset(),
            state={"connection_key": ("conn_B",)},
        )
        handler_a = compose([mw], a_inner, ctx_a)
        handler_b = compose([mw], b_inner, ctx_b)
        await asyncio.gather(handler_a(), handler_b())

    asyncio.run(run_two())
    by_event = {e["event"]: e for e in log_output.entries}
    assert by_event["A"]["tool.name"] == "tool_A"
    assert by_event["A"]["tool.connection"] == "conn_A"
    assert by_event["B"]["tool.name"] == "tool_B"
    assert by_event["B"]["tool.connection"] == "conn_B"


def test_bind_tool_context_helper(log_output: LogCapture) -> None:
    """The standalone helper binds the same keys for explicit-chain users."""
    log = get_tool_logger("test.tool")
    token = bind_tool_context("manual", ("ck",))
    try:
        log.info("hi")
    finally:
        structlog.contextvars.reset_contextvars(**token)
    [event] = log_output.entries
    assert event["tool.name"] == "manual"
    assert event["tool.connection"] == "ck"


def test_bind_tool_context_without_connection(log_output: LogCapture) -> None:
    log = get_tool_logger("test.tool")
    token = bind_tool_context("manual_solo", None)
    try:
        log.info("hi")
    finally:
        structlog.contextvars.reset_contextvars(**token)
    [event] = log_output.entries
    assert event["tool.name"] == "manual_solo"
    assert "tool.connection" not in event


def test_logging_middleware_wired_into_implicit_chain(log_output: LogCapture) -> None:
    """End-to-end via the public decorator: bound context appears on records."""
    log = get_tool_logger("decorator.test")

    @a2kit.tool()
    def emit(x: int) -> dict:
        log.info("decorated", x=x)
        return {"x": x}

    out = emit(x=7)
    assert out == {"x": 7}
    decorated_events = [e for e in log_output.entries if e["event"] == "decorated"]
    assert decorated_events, "expected the tool body's log line"
    assert decorated_events[0]["tool.name"] == "emit"
    # No connection bound on this tool — connection key is absent.
    assert "tool.connection" not in decorated_events[0]


async def test_async_decorator_path_runs_chain_and_binds(log_output: LogCapture) -> None:
    """End-to-end via the async decorator: the implicit middleware chain runs
    `structlog_context_factory()` so logs from the async tool body inherit
    `tool.name`. Guards against a future regression where `_build_chain`
    stops adding the logging middleware.
    """
    log = get_tool_logger("async.decorator.test")

    @a2kit.tool()
    async def emit_async(x: int) -> dict:
        log.info("async-decorated", x=x)
        return {"x": x}

    out = await emit_async(x=11)
    assert out == {"x": 11}
    [event] = [e for e in log_output.entries if e["event"] == "async-decorated"]
    assert event["tool.name"] == "emit_async"
    assert "tool.connection" not in event
