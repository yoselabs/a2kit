"""BDD contract for App's async-context-manager protocol.

App is its own async context manager. Construction is pure: no
async work, no singleton ``__aenter__``, no router ``__aenter__``.
First ``__aenter__`` triggers framework-owned resource entry.
"""

from __future__ import annotations

import pytest

import a2kit


class _DB:
    enter_count = 0
    exit_count = 0

    async def __aenter__(self) -> _DB:
        type(self).enter_count += 1
        return self

    async def __aexit__(self, *_exc: object) -> None:
        type(self).exit_count += 1


@pytest.fixture(autouse=True)
def _reset_db_counters() -> None:
    _DB.enter_count = 0
    _DB.exit_count = 0


def test_construction_is_pure() -> None:
    """AppBuilder + add_router + singleton should fire zero __aenter__ calls."""

    class _R(a2kit.Router):
        slug = "r"
        tools = ()

    builder = a2kit.AppBuilder("api")
    builder.provide(_DB)
    builder.add_router(_R())

    assert _DB.enter_count == 0
    assert _DB.exit_count == 0
