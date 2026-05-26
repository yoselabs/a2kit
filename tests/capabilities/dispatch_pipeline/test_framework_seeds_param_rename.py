"""Capability: ``Container.call_scope(framework_seeds=...)`` is the keyword
that publishes framework-tier typed seeds on the per-call child container.
"""

from __future__ import annotations

import pytest

from a2kit.packages.di.container import Container


class _Seed:
    pass


def _expects_seed(seed: _Seed) -> _Seed:
    return seed


@pytest.mark.asyncio
async def test_framework_seeds_publishes_typed_value() -> None:
    container = Container()
    seed = _Seed()
    async with container.call_scope(_expects_seed, framework_seeds={_Seed: seed}) as merged:
        assert merged.get("seed") is seed
