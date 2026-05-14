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
    """App + add_router + singleton should fire zero __aenter__ calls."""

    class _R(a2kit.Router):
        slug = "r"
        tools = ()

    app = a2kit.App("api")
    app.singleton(_DB)
    app.add_router(_R())

    assert _DB.enter_count == 0
    assert _DB.exit_count == 0


@pytest.mark.asyncio
async def test_async_with_app_enters_singletons() -> None:
    app = a2kit.App("api")
    app.singleton(_DB)

    assert _DB.enter_count == 0
    async with app:
        assert _DB.enter_count == 1
        assert _DB.exit_count == 0
    assert _DB.exit_count == 1


@pytest.mark.asyncio
async def test_async_with_app_exits_lifo() -> None:
    """Singletons exit in reverse-of-enter order."""

    order: list[str] = []

    class _A:
        async def __aenter__(self) -> _A:
            order.append("A-enter")
            return self

        async def __aexit__(self, *_exc: object) -> None:
            order.append("A-exit")

    class _B:
        async def __aenter__(self) -> _B:
            order.append("B-enter")
            return self

        async def __aexit__(self, *_exc: object) -> None:
            order.append("B-exit")

    app = a2kit.App("api")
    app.singleton(_A)
    app.singleton(_B)

    async with app:
        pass

    assert order == ["A-enter", "B-enter", "B-exit", "A-exit"]
