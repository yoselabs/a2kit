"""Capability: two concurrent asyncio tasks each see only their own seeds."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from a2kit.packages.context import request_scope


@dataclass
class _Marker:
    name: str


async def _task(name: str) -> str:
    marker = _Marker(name=name)
    token = request_scope.publish(marker)
    try:
        await asyncio.sleep(0)
        return request_scope.get(_Marker).name
    finally:
        request_scope.reset(token)


async def test_concurrent_scope_isolation() -> None:
    a, b = await asyncio.gather(_task("a"), _task("b"))
    assert a == "a"
    assert b == "b"
