"""Capability: a failing sink does not abort other sinks or the wire path."""

from __future__ import annotations

import logging

import pytest

from a2kit.packages.ldd.sinks import LddEmission
from a2kit.packages.ldd.sinks._core import _dispatch_sinks


async def _ok_sink(emission: LddEmission) -> None:
    emission.payload.setdefault("_observed_by", []).append("ok")


async def _bad_sink(_emission: LddEmission) -> None:
    raise RuntimeError("boom")


async def _ok_sink_two(emission: LddEmission) -> None:
    emission.payload.setdefault("_observed_by", []).append("ok2")


@pytest.mark.asyncio
async def test_one_failing_sink_does_not_abort_siblings(caplog: pytest.LogCaptureFixture) -> None:
    payload: dict = {}
    emission = LddEmission(kind="event", name="X", payload=payload, elapsed_ms=0, tool_name="t", ctx=None)
    caplog.set_level(logging.WARNING, logger="a2kit.ldd.sink_failed")
    await _dispatch_sinks(emission, (_ok_sink, _bad_sink, _ok_sink_two))
    # Both ok sinks observed the emission despite the bad sink raising.
    assert payload["_observed_by"] == ["ok", "ok2"]
    # The exception was logged at WARN, not raised.
    warn_messages = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("boom" in m for m in warn_messages)


@pytest.mark.asyncio
async def test_dispatch_returns_normally_on_empty_sinks() -> None:
    emission = LddEmission(kind="event", name="X", payload={}, elapsed_ms=0, tool_name=None, ctx=None)
    await _dispatch_sinks(emission, ())  # MUST NOT raise
