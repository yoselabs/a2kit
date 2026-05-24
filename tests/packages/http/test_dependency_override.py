"""Test seam for swapping a2kit-DI'd dependencies in FastAPI tests.

**The canonical seam: re-register on a fresh ``App`` before ``build()``.**

For a projection-tool route whose param resolves via a2kit DI directly
(not via FastAPI ``Depends``), ``app.dependency_overrides[T] = fake`` has
no effect — FastAPI never consults ``dependency_overrides`` for that
param because it is hidden from the wrapper's surface signature. The
canonical override path is ``App.provide(T, fake_factory)`` on a fresh
``App`` before ``build()``.

When a route DOES go through FastAPI ``Depends`` (e.g.
``Annotated[T, Depends(T)]`` on a ``Security`` guard), the
[[bridge-container-fastapi-depends]] change wires
``dependency_overrides[T]`` to the a2kit resolver — so FastAPI's
override surface composes with a2kit DI. That direction is covered by
``tests/packages/http/test_di_bridge.py``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import a2kit
from a2kit.packages.http import build_http_app
from a2kit.runtime import build


class _Database:
    def __init__(self, tag: str) -> None:
        self.tag = tag


def _build_app(db: _Database) -> a2kit.App:
    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def whoami(self, *, db: _Database) -> dict[str, str]:
            return {"tag": db.tag}

        tools = (whoami,)

    return a2kit.App("test").add_router(R()).provide(_Database, lambda: db)


async def test_provide_at_app_build_swaps_di() -> None:
    """Re-providing on a fresh App at test setup yields the fake instance."""
    real_db = _Database(tag="real")
    fake_db = _Database(tag="fake")

    # Test app uses fake_db directly — App.provide is last-write-wins.
    test_app = _build_app(fake_db)
    runtime = build(test_app)

    async with runtime:
        api = build_http_app(runtime)
        with TestClient(api) as client:
            r = client.post("/whoami", json={})
            assert r.status_code == 200, r.text
            assert r.json() == {"tag": "fake"}

    # The original instance was never touched.
    assert real_db.tag == "real"


async def test_dependency_overrides_does_not_swap_a2kit_di_on_wrapper_routes() -> None:
    """For routes resolving via a2kit DI directly (no FastAPI ``Depends``),
    ``app.dependency_overrides[T]`` has no effect — the param is hidden
    from the surface signature so FastAPI never consults the override.

    Routes using ``Annotated[T, Depends(T)]`` (covered separately in
    ``test_di_bridge.py``) DO get the bridge-installed resolver, and
    user overrides set on ``dependency_overrides[T]`` would compose.
    """
    real_db = _Database(tag="real")
    fake_db = _Database(tag="this-should-be-ignored")

    runtime = build(_build_app(real_db))
    async with runtime:
        api = build_http_app(runtime)
        # The "naive" FastAPI override path — does nothing for a2kit DI.
        api.dependency_overrides[_Database] = lambda: fake_db
        with TestClient(api) as client:
            r = client.post("/whoami", json={})
            assert r.status_code == 200, r.text
            # The a2kit-resolved Database wins; dependency_overrides was
            # a no-op for this type.
            assert r.json() == {"tag": "real"}
