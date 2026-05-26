"""Unit tests for the stderr-pretty sink."""

from __future__ import annotations

import pytest

from a2kit.packages.ldd.sinks import LddEmission, stderr_pretty_sink


@pytest.mark.asyncio
async def test_pretty_sink_includes_kind_and_name(capsys: pytest.CaptureFixture[str]) -> None:
    em = LddEmission(kind="event", name="Foo", payload={}, elapsed_ms=0, tool_name=None, ctx=None)
    await stderr_pretty_sink(em)
    err = capsys.readouterr().err
    assert "event:Foo" in err or "Foo" in err
