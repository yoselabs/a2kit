"""Capability: ``all_seeds()`` returns a defensive copy; mutation doesn't leak."""

from __future__ import annotations

from dataclasses import dataclass

from a2kit.packages.context import request_scope


@dataclass
class _A:
    n: int = 0


@dataclass
class _B:
    s: str = ""


def test_all_seeds_returns_defensive_copy() -> None:
    a, b = _A(n=1), _B(s="two")
    token = request_scope.publish(a, b)
    try:
        seeds = request_scope.all_seeds()
        assert seeds == {_A: a, _B: b}
        seeds.clear()
        # Mutating the snapshot does NOT clear the scope.
        assert request_scope.get(_A) is a
        assert request_scope.get(_B) is b
    finally:
        request_scope.reset(token)
