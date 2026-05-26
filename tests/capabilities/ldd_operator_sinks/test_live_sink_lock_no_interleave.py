"""Capability: 100 concurrent emissions through live_sink produce 100 atomic lines."""

from __future__ import annotations

import asyncio

import pytest

from a2kit.packages.ldd.sinks import LddEmission, make_live_sink


@pytest.mark.asyncio
async def test_concurrent_emissions_are_atomic(capsys: pytest.CaptureFixture[str]) -> None:
    sink = make_live_sink(event_prefixes=("",), heartbeat_seconds=0.0)
    emissions = [LddEmission(kind="event", name=f"E{i}Ended", payload={}, elapsed_ms=i, tool_name="t", ctx=None) for i in range(100)]
    await asyncio.gather(*(sink(em) for em in emissions))
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 100
    # Each line carries a single "E<i>Ended" token — character interleave
    # would have produced fewer than 100 well-formed event names.
    import re

    names = {m.group(0) for line in lines for m in [re.search(r"E\d+Ended", line)] if m}
    assert names == {f"E{i}Ended" for i in range(100)}
