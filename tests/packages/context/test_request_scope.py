"""Unit tests for the request-scope bridge."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from a2kit.packages.context import request_scope


@dataclass
class _Marker:
    name: str = ""


def test_publish_get_round_trip() -> None:
    m = _Marker(name="x")
    token = request_scope.publish(m)
    try:
        assert request_scope.get(_Marker) is m
    finally:
        request_scope.reset(token)


def test_get_without_scope_raises_typed() -> None:
    with pytest.raises(request_scope.RequestScopeMissing) as info:
        request_scope.get(_Marker)
    assert info.value.requested_type is _Marker


def test_try_get_without_scope_returns_none() -> None:
    assert request_scope.try_get(_Marker) is None


def test_all_seeds_is_a_defensive_copy() -> None:
    m = _Marker(name="x")
    token = request_scope.publish(m)
    try:
        seeds = request_scope.all_seeds()
        seeds.clear()
        assert request_scope.get(_Marker) is m
    finally:
        request_scope.reset(token)


def test_reset_clears_all_published_values() -> None:
    @dataclass
    class _Other:
        n: int = 0

    token = request_scope.publish(_Marker(name="a"), _Other(n=1))
    request_scope.reset(token)
    assert request_scope.try_get(_Marker) is None
    assert request_scope.try_get(_Other) is None
