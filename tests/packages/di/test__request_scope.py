"""Tests for `a2kit.packages.di._request_scope` contextvar."""

from __future__ import annotations


def test_request_scope_default_is_none() -> None:
    from a2kit.packages.di import _a2kit_request_scope

    assert _a2kit_request_scope.get() is None


def test_request_scope_set_reset_roundtrips() -> None:
    from a2kit.packages.di import Container, _a2kit_request_scope

    sentinel = Container()
    token = _a2kit_request_scope.set(sentinel)
    try:
        assert _a2kit_request_scope.get() is sentinel
    finally:
        _a2kit_request_scope.reset(token)
    assert _a2kit_request_scope.get() is None
