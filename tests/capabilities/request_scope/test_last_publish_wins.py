"""Capability: last-write-wins on type collision (matches Container.provide)."""

from __future__ import annotations

from dataclasses import dataclass

from a2kit.packages.context import request_scope


@dataclass
class _Marker:
    name: str


def test_second_publish_shadows_first() -> None:
    first = _Marker(name="first")
    second = _Marker(name="second")
    t1 = request_scope.publish(first)
    t2 = request_scope.publish(second)
    try:
        assert request_scope.get(_Marker) is second
    finally:
        request_scope.reset(t2)
        request_scope.reset(t1)
