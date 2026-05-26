"""Capability: JSON sink writes one valid JSON record per line."""

from __future__ import annotations

import json

import pytest

from a2kit.packages.ldd.sinks import LddEmission, stderr_json_sink


@pytest.mark.asyncio
async def test_json_sink_writes_one_round_trippable_record(capsys: pytest.CaptureFixture[str]) -> None:
    em = LddEmission(kind="report", name="Result", payload={"score": 0.9}, elapsed_ms=42, tool_name="t", ctx=None)
    await stderr_json_sink(em)
    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if line.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record == {
        "kind": "report",
        "name": "Result",
        "elapsed_ms": 42,
        "tool_name": "t",
        "payload": {"score": 0.9},
    }
