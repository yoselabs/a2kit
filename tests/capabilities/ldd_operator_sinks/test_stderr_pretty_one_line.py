"""Capability: pretty sink writes one human-readable line per emission."""

from __future__ import annotations

import pytest

from a2kit.packages.ldd.sinks import LddEmission, stderr_pretty_sink


@pytest.mark.asyncio
async def test_pretty_sink_writes_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    em = LddEmission(kind="event", name="CellStarted", payload={"id": 1}, elapsed_ms=123, tool_name="run", ctx=None)
    await stderr_pretty_sink(em)
    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if line.strip()]
    assert len(lines) == 1
    assert "CellStarted" in lines[0]
    assert "event" in lines[0]
    assert "tool=run" in lines[0]
