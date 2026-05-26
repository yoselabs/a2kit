"""Capability: ``LDD_OTEL_SINK=auto`` registers iff SDK present AND OTEL_EXPORTER_* set."""

from __future__ import annotations

import sys

import pytest

from a2kit._ldd_bootstrap import should_register_otel_sink


def test_otel_off_never_registers() -> None:
    assert should_register_otel_sink("off") is False


def test_otel_on_always_registers() -> None:
    assert should_register_otel_sink("on") is True


def test_otel_auto_skips_when_sdk_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for mod in list(sys.modules):
        if mod == "opentelemetry" or mod.startswith("opentelemetry."):
            monkeypatch.delitem(sys.modules, mod, raising=False)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def _refuse_otel(name: str, *args, **kwargs):
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _refuse_otel)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    assert should_register_otel_sink("auto") is False


def test_otel_auto_skips_when_no_exporter_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(__import__("os").environ):
        if key.startswith("OTEL_EXPORTER_"):
            monkeypatch.delenv(key, raising=False)
    # Even if the SDK is importable (we don't mock it here; if it's not
    # installed in the test env, this returns False for the SDK reason —
    # either way the assertion below holds.)
    assert should_register_otel_sink("auto") is False
