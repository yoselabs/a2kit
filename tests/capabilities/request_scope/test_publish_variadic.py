"""Capability: ``publish(*values)`` accepts multiple typed seeds at once."""

from __future__ import annotations

from dataclasses import dataclass

from a2kit.packages.context import request_scope


@dataclass
class _A:
    n: int = 0


@dataclass
class _B:
    s: str = ""


@dataclass
class _C:
    f: float = 0.0


def test_variadic_publish_each_retrievable() -> None:
    a, b, c = _A(n=1), _B(s="two"), _C(f=3.0)
    token = request_scope.publish(a, b, c)
    try:
        assert request_scope.get(_A) is a
        assert request_scope.get(_B) is b
        assert request_scope.get(_C) is c
    finally:
        request_scope.reset(token)
