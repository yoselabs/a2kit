"""Mirror tests for in-process LDD sinks (Phase 2-6 of ldd-emission-sinks)."""

from __future__ import annotations

import logging

import anyio

import a2kit
from a2kit.ldd import event as ldd_event, ldd_state_for_call, report as ldd_report
from a2kit.packages.ldd import LddEmission
from a2kit.packages.cli.context import StderrToolContext


# --- LddEmission shape --- #


def test_emission_is_frozen() -> None:
    import pytest

    e = LddEmission(kind="event", name="x", payload={}, elapsed_ms=0, tool_name=None, ctx=None)
    with pytest.raises((AttributeError, Exception)) as info:
        e.name = "y"  # type: ignore[misc]  # ty: ignore[invalid-assignment]  # why: test mutates a frozen/read-only property to set up a forced-error scenario
    assert (
        "FrozenInstanceError" in type(info.value).__name__
        or "can't set attribute" in str(info.value)
        or "cannot assign" in str(info.value).lower()
    )


def test_emission_carries_all_fields() -> None:
    e = LddEmission(kind="report", name="R", payload={"a": 1}, elapsed_ms=42, tool_name="t", ctx="ctx-obj")
    assert e.kind == "report"
    assert e.name == "R"
    assert e.payload == {"a": 1}
    assert e.elapsed_ms == 42
    assert e.tool_name == "t"
    assert e.ctx == "ctx-obj"


# --- add_sink / remove_sink / sinks property --- #


def test_add_and_remove_sink_round_trip() -> None:
    async def sink(_e: LddEmission) -> None:
        pass

    app = a2kit.App("t")
    app.ldd.add_sink(sink)
    assert app.ldd.sinks == (sink,)
    app.ldd.remove_sink(sink)
    assert app.ldd.sinks == ()


def test_sinks_property_is_immutable_tuple() -> None:
    app = a2kit.App("t")
    assert isinstance(app.ldd.sinks, tuple)


# --- Fan-out via event() / report() --- #


def test_event_fan_out_calls_sink_with_emission() -> None:
    seen: list[LddEmission] = []

    async def sink(e: LddEmission) -> None:
        seen.append(e)

    async def run() -> None:
        ctx = StderrToolContext()
        with ldd_state_for_call(ctx=ctx, sinks=(sink,)):
            await ldd_event("x", k=1)

    anyio.run(run)
    assert len(seen) == 1
    assert seen[0].kind == "event"
    assert seen[0].name == "x"
    assert seen[0].payload == {"k": 1}


def test_report_fan_out_calls_sink_with_emission() -> None:
    from pydantic import BaseModel

    class R(BaseModel):
        v: int

    seen: list[LddEmission] = []

    async def sink(e: LddEmission) -> None:
        seen.append(e)

    async def run() -> None:
        ctx = StderrToolContext()
        with ldd_state_for_call(ctx=ctx, sinks=(sink,), report_type=R):
            await ldd_report(R(v=7))

    anyio.run(run)
    assert len(seen) == 1
    assert seen[0].kind == "report"
    assert seen[0].name == "R"
    assert seen[0].payload == {"v": 7}


def test_sink_exception_does_not_break_dispatch(caplog) -> None:
    async def bad_sink(_e: LddEmission) -> None:
        msg = "boom"
        raise RuntimeError(msg)

    async def run() -> None:
        ctx = StderrToolContext()
        with ldd_state_for_call(ctx=ctx, sinks=(bad_sink,)):
            await ldd_event("x")  # must complete without raising

    with caplog.at_level(logging.ERROR, logger="a2kit.ldd.sinks"):
        anyio.run(run)
    assert any("LDD sink" in r.getMessage() for r in caplog.records)


def test_sinks_fire_in_registration_order() -> None:
    order: list[str] = []

    async def a(_e: LddEmission) -> None:
        order.append("a")

    async def b(_e: LddEmission) -> None:
        order.append("b")

    async def c(_e: LddEmission) -> None:
        order.append("c")

    async def run() -> None:
        ctx = StderrToolContext()
        with ldd_state_for_call(ctx=ctx, sinks=(a, b, c)):
            await ldd_event("x")

    anyio.run(run)
    assert order == ["a", "b", "c"]


def test_kill_switch_gates_wire_and_sinks_symmetrically() -> None:
    seen: list[LddEmission] = []

    async def sink(e: LddEmission) -> None:
        seen.append(e)

    async def run() -> None:
        ctx = StderrToolContext()
        with ldd_state_for_call(ctx=ctx, sinks=(sink,), events_enabled=False):
            await ldd_event("x")  # disabled — no wire emit, no sink

    anyio.run(run)
    assert seen == []


def test_state_resets_after_context_exit() -> None:
    seen: list[LddEmission] = []

    async def sink(e: LddEmission) -> None:
        seen.append(e)

    from a2kit.exceptions import AmbientContextMissing

    async def run() -> None:
        ctx = StderrToolContext()
        with ldd_state_for_call(ctx=ctx, sinks=(sink,)):
            await ldd_event("inside")
        # Outside the context: ambient ctx is gone → fail loud.
        try:
            await ldd_event("outside")
        except AmbientContextMissing:
            pass
        else:
            msg = "expected AmbientContextMissing outside ldd_state_for_call"
            raise AssertionError(msg)

    anyio.run(run)
    assert len(seen) == 1
    assert seen[0].name == "inside"


# --- End-to-end via in-process testing client --- #


def test_in_process_client_propagates_sinks_to_dispatch() -> None:
    """Tool body emits via `a2kit.ldd.event`; registered sink sees the emission."""
    from a2kit.packages.testing import client as test_client

    class _R(a2kit.Router):
        slug = "rs"
        name = "rs"

        @a2kit.read()
        async def tick(self, *, ctx: a2kit.ToolContext) -> dict[str, int]:
            from a2kit.ldd import event

            await event("tickle", seq=1)
            return {"ok": 1}

        tools = (tick,)

    app = a2kit.App("sinkstest")
    app.add_router(_R())

    seen: list[LddEmission] = []

    async def sink(e: LddEmission) -> None:
        seen.append(e)

    app.ldd.add_sink(sink)

    async def go() -> None:
        async with test_client.TestClient(app) as c:
            await c.invoke("tick")

    anyio.run(go)
    assert any(e.name == "tickle" for e in seen)
