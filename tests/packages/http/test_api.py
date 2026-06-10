"""``ApiSurface`` — author-side ``@app.api.<method>`` decorator family."""

from __future__ import annotations

import pytest

from a2kit.packages.http.api import ApiRoute, ApiSurface


def test_get_decorator_records_route() -> None:
    surface = ApiSurface()

    @surface.get("/x")
    async def _h() -> None:
        return None

    assert len(surface.routes) == 1
    route = surface.routes[0]
    assert isinstance(route, ApiRoute)
    assert route.method == "GET"
    assert route.path == "/x"


def test_method_specific_decorators() -> None:
    """Each verb decorator records the correct HTTP method."""
    surface = ApiSurface()

    @surface.put("/a")
    async def _a() -> None: ...

    @surface.delete("/b")
    async def _b() -> None: ...

    @surface.patch("/c")
    async def _c() -> None: ...

    @surface.options("/d")
    async def _d() -> None: ...

    @surface.head("/e")
    async def _e() -> None: ...

    @surface.post("/f")
    async def _f() -> None: ...

    methods = {r.path: r.method for r in surface.routes}
    assert methods == {
        "/a": "PUT",
        "/b": "DELETE",
        "/c": "PATCH",
        "/d": "OPTIONS",
        "/e": "HEAD",
        "/f": "POST",
    }


def test_surfaces_kwarg_is_rejected() -> None:
    """``surfaces=`` belongs on projection decorators, not on ``@app.api.*``."""
    surface = ApiSurface()
    with pytest.raises(TypeError, match=r"surfaces="):

        @surface.get("/x", surfaces=["api"])
        async def _h() -> None:
            return None


def test_authorize_kwarg_is_popped_before_fastapi() -> None:
    """``authorize`` is consumed here; ``fastapi_kwargs`` does not carry it."""
    surface = ApiSurface()

    async def _gate() -> bool:
        return True

    @surface.get("/x", authorize=_gate)
    async def _h() -> None:
        return None

    route = surface.routes[0]
    assert route.authorize is _gate
    assert "authorize" not in route.fastapi_kwargs


def test_fastapi_kwargs_are_preserved() -> None:
    """``response_model``/``status_code``/etc. pass through to FastAPI."""
    surface = ApiSurface()

    @surface.post("/x", status_code=201, tags=["users"])
    async def _h() -> None:
        return None

    route = surface.routes[0]
    assert route.fastapi_kwargs == {"status_code": 201, "tags": ["users"]}


def test_fastapi_app_starts_unset() -> None:
    """``fastapi_app`` is populated only after ``build_http_app`` runs."""
    surface = ApiSurface()
    assert surface.fastapi_app is None
