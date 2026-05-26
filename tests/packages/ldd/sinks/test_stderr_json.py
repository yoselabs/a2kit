"""Unit tests for the stderr-json sink."""

from __future__ import annotations

import json

import pytest

from a2kit.packages.ldd.sinks import LddEmission, stderr_json_sink


@pytest.mark.asyncio
async def test_json_sink_emits_round_trippable_json(capsys: pytest.CaptureFixture[str]) -> None:
    em = LddEmission(kind="log", name="L", payload={"k": 1}, elapsed_ms=5, tool_name="t", ctx=None)
    await stderr_json_sink(em)
    record = json.loads(capsys.readouterr().err.strip())
    assert record["name"] == "L"
    assert record["payload"] == {"k": 1}
