"""``FastMCPContextAdapter`` fulfils ``a2kit.runtime.ToolContext``."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest
from pydantic import BaseModel

from a2kit.exceptions import ReportTypeMismatch, ReportTypeNotDeclared
from a2kit.packages.mcp.context import FastMCPContextAdapter, bind_context
from a2kit.runtime import ToolContext


class _StubFastmcpCtx:
    """Mimics the subset of fastmcp.Context the adapter touches."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.progress: list[tuple[float, float | None]] = []
        self.logs: list[dict[str, Any]] = []

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

    async def log(
        self,
        message: str,
        level: str | None = None,
        logger_name: str | None = None,
        extra: Any = None,
    ) -> None:
        self.logs.append({"message": message, "level": level, "extra": dict(extra) if extra else None})


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
    # Every emission carries elapsed_ms; original kwargs round-trip via extra.
    info_call = stub.calls[0]
    assert info_call[0] == "info"
    assert info_call[1] == "starting"
    assert info_call[2] is not None and info_call[2]["file"] == "x.csv"
    assert "elapsed_ms" in info_call[2]
    warn_call = stub.calls[1]
    assert warn_call[2] is not None and warn_call[2]["attempt"] == 2
    err_call = stub.calls[2]
    # error("boom") with no fields → extra has only elapsed_ms.
    assert err_call[2] is not None and set(err_call[2]) == {"elapsed_ms"}


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


# --- LDD: events --- #


def test_event_emits_log_with_a2kit_kind() -> None:
    stub = _StubFastmcpCtx()

    async def _go() -> None:
        adapter = FastMCPContextAdapter(stub)
        await adapter.event("api.fetched", count=30, source="primary")

    asyncio.run(_go())
    assert len(stub.logs) == 1
    log = stub.logs[0]
    assert log["message"] == "api.fetched"
    assert log["level"] == "info"
    extra = log["extra"]
    assert extra["a2kit_kind"] == "event"
    assert extra["name"] == "api.fetched"
    assert extra["payload"] == {"count": 30, "source": "primary"}
    assert "elapsed_ms" in extra


def test_event_disabled_emits_nothing() -> None:
    stub = _StubFastmcpCtx()

    async def _go() -> None:
        adapter = FastMCPContextAdapter(stub, events_enabled=False)
        await adapter.event("ignored")

    asyncio.run(_go())
    assert stub.logs == []


# --- LDD: reports --- #


class _BatchReport(BaseModel):
    batch: int
    accepted: int


def test_report_happy_path() -> None:
    stub = _StubFastmcpCtx()

    async def _go() -> None:
        adapter = FastMCPContextAdapter(stub, report_type=_BatchReport, tool_name="t")
        await adapter.report(_BatchReport(batch=4, accepted=12))

    asyncio.run(_go())
    assert len(stub.logs) == 1
    log = stub.logs[0]
    assert log["message"] == "_BatchReport"
    extra = log["extra"]
    assert extra["a2kit_kind"] == "report"
    assert extra["payload"] == {"batch": 4, "accepted": 12}
    assert "elapsed_ms" in extra


def test_report_without_declared_type_raises() -> None:
    stub = _StubFastmcpCtx()
    adapter = FastMCPContextAdapter(stub, tool_name="t")
    with pytest.raises(ReportTypeNotDeclared):
        asyncio.run(adapter.report({"any": "dict"}))


def test_report_type_mismatch_raises() -> None:
    stub = _StubFastmcpCtx()
    adapter = FastMCPContextAdapter(stub, report_type=_BatchReport, tool_name="t")
    with pytest.raises(ReportTypeMismatch):
        asyncio.run(adapter.report({"wrong": "shape"}))


def test_report_disabled_still_validates() -> None:
    stub = _StubFastmcpCtx()
    adapter = FastMCPContextAdapter(stub, report_type=_BatchReport, tool_name="t", reports_enabled=False)
    # Type-correct: no emission.
    asyncio.run(adapter.report(_BatchReport(batch=1, accepted=1)))
    assert stub.logs == []
    # Type-incorrect: still raises.
    with pytest.raises(ReportTypeMismatch):
        asyncio.run(adapter.report({"wrong": "shape"}))
