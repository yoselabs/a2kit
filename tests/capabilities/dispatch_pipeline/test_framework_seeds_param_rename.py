"""Capability: ``Container.call_scope(framework_seeds=...)`` is the new keyword.

``scoped_seeds=`` forwards to ``framework_seeds=`` with a
``DeprecationWarning``.
"""

from __future__ import annotations

import warnings

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


@pytest.mark.asyncio
async def test_scoped_seeds_alias_emits_deprecation_warning() -> None:
    container = Container()
    seed = _Seed()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        async with container.call_scope(_expects_seed, scoped_seeds={_Seed: seed}) as merged:
            assert merged.get("seed") is seed
    assert any(issubclass(w.category, DeprecationWarning) and "framework_seeds" in str(w.message) for w in caught), [
        (w.category.__name__, str(w.message)) for w in caught
    ]
