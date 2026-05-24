"""Tests for `a2kit.packages.di._fastapi_bridge` resolver factory."""

from __future__ import annotations

import pytest

from a2kit.packages.di._fastapi_bridge import _make_resolver


class _X:
    pass


@pytest.mark.asyncio
async def test_resolver_outside_scope_raises() -> None:
    resolver = _make_resolver(_X)
    with pytest.raises(RuntimeError, match="outside call_scope"):
        await resolver()
