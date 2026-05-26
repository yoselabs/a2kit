"""Capability: ``publish(value)`` then ``get(T)`` returns the same instance.

Per `generalise-context-bridges` (2026-05-27).
"""

from __future__ import annotations

from dataclasses import dataclass

from a2kit.packages.context import request_scope


@dataclass
class _Marker:
    name: str


def test_publish_then_get_returns_same_instance() -> None:
    payload = _Marker(name="hello")
    token = request_scope.publish(payload)
    try:
        assert request_scope.get(_Marker) is payload
    finally:
        request_scope.reset(token)
