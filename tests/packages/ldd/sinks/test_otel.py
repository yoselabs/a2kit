"""Unit tests for the OTel sink (drain-on-missing behaviour)."""

from __future__ import annotations

import pytest

from a2kit.packages.ldd.sinks import LddEmission, otel_sink


@pytest.mark.asyncio
async def test_otel_sink_drains_started_events_without_emitting() -> None:
    em = LddEmission(kind="event", name="CellStarted", payload={}, elapsed_ms=0, tool_name="t", ctx=None)
    # Started events are silently consumed; the span fires on *Ended.
    await otel_sink(em)


@pytest.mark.asyncio
async def test_otel_sink_handles_ended_without_sdk_silently() -> None:
    em = LddEmission(kind="event", name="CellEnded", payload={"k": "v"}, elapsed_ms=10, tool_name="t", ctx=None)
    # Without OTel SDK installed (or no tracer configured) the sink
    # MUST drain without raising.
    await otel_sink(em)
