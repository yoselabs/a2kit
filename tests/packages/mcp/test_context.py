"""``FastMCPContextAdapter`` fulfils ``a2kit.runtime.ToolContext``."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any


from a2kit.runtime import ToolContext
from a2kit.packages.mcp.context import FastMCPContextAdapter, bind_context


class _StubFastmcpCtx:
    """Mimics the subset of fastmcp.Context the adapter touches."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.progress: list[tuple[float, float | None]] = []

    async def info(self, message: str, logger_name: str | None = None, extra: Any = None) -> None:
        self.calls.append(("info", message, dict(extra) if extra else None))

    async def warning(self, message: str, logger_name: str | None = None, extra: Any = None) -> None:
        self.calls.append(("warning", message, dict(extra) if extra else None))

    async def error(self, message: str, logger_name: str | None = None, extra: Any = None) -> None:
        self.calls.append(("error", message, dict(extra) if extra else None))

    async def debug(self, message: str, logger_name: str | None = None, extra: Any = None) -> None:
        self.calls.append(("debug", message, dict(extra) if extra else None))

    async def report_progress(self, progress: float, total: float | None = None) -> None:
        self.progress.append((progress, total))


def test_adapter_satisfies_protocol() -> None:
    stub = _StubFastmcpCtx()
    adapter = FastMCPContextAdapter(stub)
    assert isinstance(adapter, ToolContext)


def test_logging_methods_schedule_and_pass_extras() -> None:
    stub = _StubFastmcpCtx()

    async def _go() -> None:
        adapter = FastMCPContextAdapter(stub)
        adapter.info("starting", file="x.csv")
        adapter.warning("retry", attempt=2)
        adapter.error("boom")
        adapter.debug("trace", id=1)
        # Yield so scheduled tasks complete.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(_go())
    levels = [c[0] for c in stub.calls]
    assert levels == ["info", "warning", "error", "debug"]
    assert stub.calls[0] == ("info", "starting", {"file": "x.csv"})
    assert stub.calls[1] == ("warning", "retry", {"attempt": 2})
    assert stub.calls[2] == ("error", "boom", None)


def test_report_progress_awaits() -> None:
    stub = _StubFastmcpCtx()

    async def _go() -> None:
        adapter = FastMCPContextAdapter(stub)
        await adapter.report_progress(3, 10)
        await adapter.report_progress(5)

    asyncio.run(_go())
    assert stub.progress == [(3, 10), (5, None)]


def test_logging_outside_event_loop_does_not_raise() -> None:
    stub = _StubFastmcpCtx()
    adapter = FastMCPContextAdapter(stub)
    # No running loop — must not raise.
    adapter.info("synchronous")
    # Coroutine was closed; no call recorded.
    assert stub.calls == []


def test_bind_context_sync_tool_wraps_injected_context() -> None:
    seen: dict[str, Any] = {}

    def tool(*, ctx: ToolContext, name: str) -> dict[str, str]:
        seen["ctx"] = ctx
        ctx.info("hi")
        return {"name": name}

    wrapped = bind_context(tool, "ctx")
    stub = _StubFastmcpCtx()

    async def _go() -> None:
        result = wrapped(ctx=stub, name="me")
        await asyncio.sleep(0)
        return result

    result = asyncio.run(_go())
    assert result == {"name": "me"}
    assert isinstance(seen["ctx"], FastMCPContextAdapter)
    # Signature retyped to fastmcp.Context so FastMCP injects it.
    from fastmcp import Context

    sig = inspect.signature(wrapped)
    assert sig.parameters["ctx"].annotation is Context


def test_bind_context_async_tool_wraps_injected_context() -> None:
    seen: dict[str, Any] = {}

    async def tool(*, ctx: ToolContext, n: int) -> dict[str, int]:
        seen["ctx"] = ctx
        ctx.info("done", n=n)
        return {"n": n}

    wrapped = bind_context(tool, "ctx")
    stub = _StubFastmcpCtx()

    async def _go() -> None:
        result = await wrapped(ctx=stub, n=5)
        await asyncio.sleep(0)
        return result

    assert asyncio.run(_go()) == {"n": 5}
    assert isinstance(seen["ctx"], FastMCPContextAdapter)
