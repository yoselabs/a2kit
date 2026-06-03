"""BDD scenarios for ``a2kit.testing.ambient_for_tests``.

Pytest fixture that binds a call scope so tests calling orchestrator / phase
functions directly (bypassing ``TestClient.invoke``) run as if dispatched:
``a2kit.log.*`` emissions carry a ``call_id`` and resolve a (null) ``ctx`` for
the wire path. Emission itself never raises — it is stdlib logging — so the
fixture is about correlation + ctx, not about avoiding an error.
"""

from __future__ import annotations

import pytest

import a2kit.log
from a2kit.packages.log.scope import _active_scope
from a2kit.testing import ambient_for_tests


def test_ambient_for_tests_is_importable_from_public_surface() -> None:
    assert ambient_for_tests is not None


@pytest.mark.asyncio
async def test_using_fixture_binds_a_call_scope(
    ambient_for_tests: None,  # noqa: ARG001 -- fixture activation
) -> None:
    """Inside a test requesting the fixture, a call scope is active and
    ``a2kit.log.info`` completes."""
    assert _active_scope() is not None
    await a2kit.log.info("evt", k=1)


@pytest.mark.asyncio
async def test_without_fixture_emission_still_completes() -> None:
    """Without the fixture there is no active scope, but emission is plain
    stdlib logging — it completes without raising (no correlation id)."""
    assert _active_scope() is None
    await a2kit.log.info("evt", k=1)


@pytest.mark.asyncio
async def test_emission_completes_under_fixture_defaults(
    ambient_for_tests: None,  # noqa: ARG001
) -> None:
    await a2kit.log.info("evt", k=1)
    await a2kit.log.info("another", payload="data")
