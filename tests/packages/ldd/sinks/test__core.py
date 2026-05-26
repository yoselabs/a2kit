"""Unit tests for the sinks core: LddEmission shape + parallel dispatch."""

from __future__ import annotations

import asyncio
import logging

import pytest

from a2kit.packages.ldd.sinks import LddEmission
from a2kit.packages.ldd.sinks._core import _dispatch_sinks


def test_emission_is_frozen_and_slotted() -> None:
    em = LddEmission(kind="event", name="X", payload={}, elapsed_ms=0, tool_name=None, ctx=None)
    import dataclasses

    assert dataclasses.is_dataclass(em)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(em, "name", "Y")  # noqa: B010


@pytest.mark.asyncio
async def test_dispatch_runs_sinks_in_parallel() -> None:
    started: list[str] = []
    finished: list[str] = []

    async def _slow_sink(_em: LddEmission) -> None:
        started.append("slow")
        await asyncio.sleep(0.05)
        finished.append("slow")

    async def _fast_sink(_em: LddEmission) -> None:
        started.append("fast")
        finished.append("fast")

    em = LddEmission(kind="event", name="X", payload={}, elapsed_ms=0, tool_name=None, ctx=None)
    await _dispatch_sinks(em, (_slow_sink, _fast_sink))
    # Parallel: fast finishes before slow even though slow was started first.
    assert finished == ["fast", "slow"]


@pytest.mark.asyncio
async def test_failing_sink_is_logged_and_dropped(caplog: pytest.LogCaptureFixture) -> None:
    async def _bad(_em: LddEmission) -> None:
        raise ValueError("nope")

    em = LddEmission(kind="event", name="X", payload={}, elapsed_ms=0, tool_name=None, ctx=None)
    caplog.set_level(logging.WARNING, logger="a2kit.ldd.sink_failed")
    await _dispatch_sinks(em, (_bad,))  # MUST NOT raise
    assert any("nope" in r.getMessage() for r in caplog.records)
