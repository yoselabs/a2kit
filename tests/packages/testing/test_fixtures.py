"""Tests for the testing-package pytest fixtures + make_test_app DI swap."""

from __future__ import annotations

import asyncio
from typing import Any

import a2kit
from a2kit.packages.testing import make_test_app
from a2kit.packages.testing.fixtures import _rebuild_with_overrides
from a2kit.routers import Router
from uncalled_for import Depends, resolved_dependencies


# --- DI swap: real and fake factories live at module level ---


def real_db() -> str:
    return "REAL"


def fake_db() -> str:
    return "FAKE"


class TasksRouter(Router):
    name = "tasks"

    @a2kit.read("query")
    async def query(self, *, db: str = Depends(real_db), q: str = "default") -> dict[str, Any]:
        """Return the resolved db + query string."""
        return {"db": db, "q": q}


# Module-level handle to the decorated function (for direct rebuild tests).
query = TasksRouter.__dict__["query"]


# --- tests ---


def test_app_fixture_yields_clean_app() -> None:
    # Call the underlying fixture function (skip pytest wrapper).
    from a2kit.packages.testing.fixtures import app as app_fixture

    inst = app_fixture.__wrapped__() if hasattr(app_fixture, "__wrapped__") else app_fixture()
    assert isinstance(inst, a2kit.App)
    assert inst.name == "test"
    assert inst.tools() == []


def test_cassette_fixture_returns_factory(tmp_path: Any) -> None:
    from a2kit.packages.testing.fixtures import cassette as cassette_fixture

    factory_fn = cassette_fixture.__wrapped__ if hasattr(cassette_fixture, "__wrapped__") else cassette_fixture
    factory = factory_fn(tmp_path)
    cm = factory("first")
    assert hasattr(cm, "__enter__")


def test_rebuild_with_overrides_swaps_factory() -> None:
    rebuilt = _rebuild_with_overrides(query, {real_db: fake_db})
    assert rebuilt is not query

    async def _run() -> dict[str, Any]:
        async with resolved_dependencies(rebuilt) as resolved:
            return await rebuilt(None, **resolved, q="x")  # self=None

    result = asyncio.new_event_loop().run_until_complete(_run())
    assert result == {"db": "FAKE", "q": "x"}


def test_rebuild_no_change_when_factory_not_in_overrides() -> None:
    rebuilt = _rebuild_with_overrides(query, {})
    assert rebuilt is query


def test_make_test_app_attaches_routers() -> None:
    router = TasksRouter()
    test_app = make_test_app([router])
    assert test_app.name == "test"
    assert len(test_app.routers()) == 1


def test_make_test_app_with_overrides_swaps_di() -> None:
    router = TasksRouter()
    test_app = make_test_app([router], overrides={real_db: fake_db})

    tools = test_app.tools()
    assert len(tools) == 1
    rebuilt = tools[0]

    async def _run() -> dict[str, Any]:
        async with resolved_dependencies(rebuilt) as resolved:
            return await rebuilt(None, **resolved, q="hello")  # self=None

    result = asyncio.new_event_loop().run_until_complete(_run())
    assert result["db"] == "FAKE"
    assert result["q"] == "hello"


def test_make_test_app_preserves_meta() -> None:
    router = TasksRouter()
    test_app = make_test_app([router], overrides={real_db: fake_db})
    rebuilt = test_app.tools()[0]
    meta = a2kit.metadata.get_meta(rebuilt)
    assert meta is not None
    assert meta.tool_name == "query"
    assert meta.verb == "read"


def test_make_test_app_preserves_router_slug() -> None:
    router = TasksRouter()
    original_slug = router.slug
    test_app = make_test_app([router], overrides={real_db: fake_db})
    assert test_app.routers()[0].slug == original_slug
