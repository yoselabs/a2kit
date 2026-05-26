"""Unit tests for the live sink."""

from __future__ import annotations

import pytest

from a2kit.packages.ldd.sinks import LddEmission, make_live_sink


@pytest.mark.asyncio
async def test_live_sink_filters_by_prefix(capsys: pytest.CaptureFixture[str]) -> None:
    sink = make_live_sink(event_prefixes=("Cell",), heartbeat_seconds=0.0)
    matched = LddEmission(kind="event", name="CellStarted", payload={}, elapsed_ms=0, tool_name="t", ctx=None)
    unmatched = LddEmission(kind="event", name="OtherStarted", payload={}, elapsed_ms=0, tool_name="t", ctx=None)
    await sink(matched)
    await sink(unmatched)
    out = capsys.readouterr().out
    assert "CellStarted" in out
    assert "OtherStarted" not in out


@pytest.mark.asyncio
async def test_live_sink_writes_started_then_ended(capsys: pytest.CaptureFixture[str]) -> None:
    sink = make_live_sink(event_prefixes=("",), heartbeat_seconds=0.0)
    await sink(LddEmission(kind="event", name="XStarted", payload={}, elapsed_ms=0, tool_name="t", ctx=None))
    await sink(LddEmission(kind="event", name="XEnded", payload={}, elapsed_ms=10, tool_name="t", ctx=None))
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 2
    assert "XStarted" in lines[0]
    assert "XEnded" in lines[1]
