"""Unit tests for the App-boot built-in sink registration helper."""

from __future__ import annotations

from typing import Any, cast

from a2kit.config import LddConfig
from a2kit.packages.ldd import _AppLdd
from a2kit._ldd_bootstrap import register_builtin_ldd_sinks


class _StubLdd:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add_sink(self, sink: Any) -> None:
        self.added.append(sink)


def _as_ldd(stub: _StubLdd) -> _AppLdd:
    """The helper takes ``_AppLdd``; ``_StubLdd`` is structural-compatible."""
    return cast("_AppLdd", stub)


def test_default_config_registers_no_sinks() -> None:
    ldd = _StubLdd()
    cfg = LddConfig(otel_sink="off")  # avoid auto pulling OTel in the test env
    register_builtin_ldd_sinks(_as_ldd(ldd), cfg)
    assert ldd.added == []


def test_stderr_pretty_registered_when_configured() -> None:
    ldd = _StubLdd()
    cfg = LddConfig(stderr_sink="pretty", otel_sink="off")
    register_builtin_ldd_sinks(_as_ldd(ldd), cfg)
    assert len(ldd.added) == 1
    assert getattr(ldd.added[0], "__name__", "") == "stderr_pretty_sink"


def test_stderr_json_registered_when_configured() -> None:
    ldd = _StubLdd()
    cfg = LddConfig(stderr_sink="json", otel_sink="off")
    register_builtin_ldd_sinks(_as_ldd(ldd), cfg)
    assert len(ldd.added) == 1
    assert getattr(ldd.added[0], "__name__", "") == "stderr_json_sink"


def test_otel_on_registers_otel_sink() -> None:
    ldd = _StubLdd()
    cfg = LddConfig(otel_sink="on")
    register_builtin_ldd_sinks(_as_ldd(ldd), cfg)
    assert any(getattr(s, "__name__", "") == "otel_sink" for s in ldd.added)


def test_live_on_registers_live_sink() -> None:
    ldd = _StubLdd()
    cfg = LddConfig(otel_sink="off", live_sink="on")
    register_builtin_ldd_sinks(_as_ldd(ldd), cfg)
    assert any(getattr(s, "__name__", "") == "live_sink" for s in ldd.added)
