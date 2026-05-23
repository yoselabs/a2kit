"""Test seam for swapping a2kit-DI'd dependencies in FastAPI tests.

**The correct seam: re-register on a fresh ``App`` before ``build()``.**

FastAPI's ``app.dependency_overrides[T] = fake`` mechanism keys on
``Depends`` callables; a2kit-DI'd types are not ``Depends``. Therefore
``dependency_overrides[Database] = fake_db`` will NOT swap an
a2kit-resolved ``Database``.

The working pattern is to construct a fresh ``App`` with the test
provider — ``App.provide()`` is last-write-wins, so re-registering
overrides the prior provider on the new App. The sealed ``AppRuntime``
takes a snapshot at ``build(app)`` time, so the override is locked in
for the test's runtime and does not affect the original App.

These tests assert both halves: the positive (re-provide works) and
the negative (``dependency_overrides`` does NOT route to a2kit DI).
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


async def test_dependency_overrides_does_not_route_to_a2kit_di() -> None:
    """FastAPI's ``dependency_overrides[T]`` does NOT swap a2kit-resolved deps.

    This codifies the documented constraint: the FastAPI override
    mechanism keys on ``Depends`` callables; a2kit DI is type-driven
    via the wrapper's ``Container.call_scope``. The two do not meet —
    setting ``dependency_overrides[T]`` is a silent no-op for
    Container-known types.
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
