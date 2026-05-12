"""Tests — ambient LDD ctx binding (round-5 gap 2).

LDD primitives read `ctx` from the ambient `_LDD_STATE` ContextVar set
by the dispatcher. Calling a primitive outside an active dispatch
raises `AmbientContextMissing` — fail loud, never silently no-op.
"""

from __future__ import annotations

import asyncio

import pytest

import a2kit
from a2kit.exceptions import AmbientContextMissing
from a2kit.ldd import debug as ldd_debug
from a2kit.ldd import error as ldd_error
from a2kit.ldd import event as ldd_event
from a2kit.ldd import info as ldd_info
from a2kit.ldd import ldd_state_for_call, report
from a2kit.ldd import log as ldd_log
from a2kit.ldd import warning as ldd_warning
from a2kit.packages.cli.context import StderrToolContext
from a2kit.packages.ldd import EventRegistry


def _run(coro: asyncio.coroutines) -> None:
    asyncio.run(coro)


@pytest.mark.parametrize(
    ("expected_fragment", "call"),
    [
        ("a2kit.ldd.event", lambda: ldd_event("x")),
        ("a2kit.ldd.log", lambda: ldd_log("info", "x")),
        # Each shorthand surfaces its own name in the error so the trace
        # points at the actual call site rather than the inner `log` frame.
        ("a2kit.ldd.info", lambda: ldd_info("x")),
        ("a2kit.ldd.warning", lambda: ldd_warning("x")),
        ("a2kit.ldd.error", lambda: ldd_error("x")),
        ("a2kit.ldd.debug", lambda: ldd_debug("x")),
    ],
)
def test_primitive_outside_dispatch_raises_ambient_missing(expected_fragment: str, call) -> None:
    with pytest.raises(AmbientContextMissing) as excinfo:
        _run(call())
    assert expected_fragment in str(excinfo.value)


def test_emit_typed_outside_dispatch_raises() -> None:
    class E:
        def model_dump(self, mode: str = "python") -> dict[str, int]:  # noqa: ARG002
            return {"seq": 1}

    reg = EventRegistry()
    with pytest.raises(AmbientContextMissing) as excinfo:
        _run(reg.emit_typed(E()))
    assert "a2kit.ldd.event" in str(excinfo.value)


def test_report_outside_dispatch_raises() -> None:
    class Payload:
        pass

    with pytest.raises(AmbientContextMissing) as excinfo:
        _run(report(Payload()))
    assert "a2kit.ldd.report" in str(excinfo.value)


class _PingRouter(a2kit.Router):
    slug = "_ping"
    @a2kit.read()
    async def ping(self, ctx: a2kit.ToolContext) -> dict[str, str]:
        await ldd_info("hello", k="v")
        return {"ok": "yes"}
    tools = (ping,)


def test_dispatch_provides_ambient_ctx_to_primitives() -> None:
    """End-to-end through TestClient: `ldd_info` inside a tool body works
    with no ctx arg."""
    from a2kit.testing import client

    app = a2kit.App("ambient").add_router(_PingRouter())

    async def go() -> None:
        async with client(app) as c:
            result = await c.invoke("ping")
            assert result == {"ok": "yes"}
            # The TestClient captures LDD via the wire path; an info
            # delivered should be visible as a log entry.
            log_msgs = [entry.get("msg") for entry in c.logs]
            assert "hello" in log_msgs

    asyncio.run(go())


def test_lifespan_body_using_ldd_primitive_raises() -> None:
    """Lifespan body runs BEFORE any dispatch; primitives must fail loud."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        await ldd_info("from-lifespan")  # no ambient ctx — must raise
        yield

    app = a2kit.App("noctx", lifespan=lifespan)

    async def go() -> None:
        with pytest.raises(AmbientContextMissing):
            async with app.lifespan_cm():
                pass

    asyncio.run(go())


def test_ldd_state_for_call_with_stub_makes_primitives_work() -> None:
    """The test seam: wrap with `ldd_state_for_call(ctx=stub)` to exercise
    primitives without a full dispatch."""
    ctx = StderrToolContext()

    async def go() -> None:
        with ldd_state_for_call(ctx=ctx):
            await ldd_event("seam-works")

    # No raise expected.
    asyncio.run(go())
