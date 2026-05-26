"""Capability: with OTel SDK missing, otel_sink still accepts every emission."""

from __future__ import annotations

import sys

import pytest

from a2kit.packages.ldd.sinks import LddEmission, otel_sink


@pytest.mark.asyncio
async def test_otel_sink_drains_when_sdk_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mask any imported opentelemetry module so _get_tracer falls through.
    for mod in list(sys.modules):
        if mod == "opentelemetry" or mod.startswith("opentelemetry."):
            monkeypatch.delitem(sys.modules, mod, raising=False)
    monkeypatch.setattr("builtins.__import__", _refuse_opentelemetry(monkeypatch))
    em = LddEmission(kind="event", name="CellEnded", payload={"k": "v"}, elapsed_ms=10, tool_name="t", ctx=None)
    # Must not raise even though OTel is unavailable.
    await otel_sink(em)


def _refuse_opentelemetry(monkeypatch: pytest.MonkeyPatch):
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    return fake_import
