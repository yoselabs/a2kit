"""Capability: ``try_get(T)`` returns ``None`` instead of raising."""

from __future__ import annotations

from dataclasses import dataclass

from a2kit.packages.context import request_scope


@dataclass
class _Marker:
    name: str = ""


def test_try_get_missing_returns_none() -> None:
    assert request_scope.try_get(_Marker) is None
