"""``build_http_app`` — FastAPI sub-app builder smoke tests."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import a2kit
from a2kit.packages.http import ApiSurface, build_http_app
from a2kit.runtime import build


class _Store:
    tag = "store-ok"


def _build_di_app() -> a2kit.App:
    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def echo(self, *, msg: str, store: _Store) -> dict[str, Any]:
            return {"msg": msg, "tag": store.tag}

        tools = (echo,)

    return a2kit.App("http-demo").add_router(R()).provide(_Store, lambda: _Store())


@pytest.mark.asyncio
async def test_health_route_responds_200() -> None:
    runtime = build(_build_di_app())
    async with runtime:
        api = build_http_app(runtime)
        with TestClient(api) as client:
            r = client.get("/health")
            assert r.status_code == 200
            assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_projection_tool_mounts_as_post_route() -> None:
    runtime = build(_build_di_app())
    async with runtime:
        api = build_http_app(runtime)
        with TestClient(api) as client:
            r = client.post("/echo", json={"msg": "hi"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body == {"msg": "hi", "tag": "store-ok"}


@pytest.mark.asyncio
async def test_projection_tool_rejects_get() -> None:
    """POST-for-all: GET to a projection-tool route returns 405."""
    runtime = build(_build_di_app())
    async with runtime:
        api = build_http_app(runtime)
        with TestClient(api) as client:
            r = client.get("/echo")
            assert r.status_code == 405


@pytest.mark.asyncio
async def test_openapi_document_contains_projection_tool() -> None:
    runtime = build(_build_di_app())
    async with runtime:
        api = build_http_app(runtime)
        with TestClient(api) as client:
            r = client.get("/openapi.json")
            assert r.status_code == 200
            doc = r.json()
            assert "/echo" in doc["paths"]
            assert "post" in doc["paths"]["/echo"]
            # DI dep `store` must NOT appear in the request body schema.
            post_op = doc["paths"]["/echo"]["post"]
            body_ref = post_op["requestBody"]["content"]["application/json"]["schema"]
            schema_name = body_ref.get("$ref", "").rsplit("/", 1)[-1]
            schema = doc["components"]["schemas"][schema_name]
            assert "msg" in schema["properties"]
            assert "store" not in schema["properties"]


@pytest.mark.asyncio
async def test_swagger_ui_reachable() -> None:
    runtime = build(_build_di_app())
    async with runtime:
        api = build_http_app(runtime)
        with TestClient(api) as client:
            r = client.get("/docs")
            assert r.status_code == 200
            assert "swagger" in r.text.lower()


@pytest.mark.asyncio
async def test_api_surface_routes_register() -> None:
    """``@app.api.get(path)`` registrations land on the FastAPI app."""
    app = _build_di_app()
    surface = ApiSurface()

    @surface.get("/version")
    async def version() -> dict[str, str]:
        return {"v": "1"}

    runtime = build(app)
    async with runtime:
        api = build_http_app(runtime, surface)
        with TestClient(api) as client:
            r = client.get("/version")
            assert r.status_code == 200
            assert r.json() == {"v": "1"}
            assert surface.fastapi_app is api


@pytest.mark.asyncio
async def test_api_surface_di_resolves_on_get() -> None:
    """An author ``@app.api.get`` with a DI-typed param resolves via Container."""
    app = _build_di_app()
    surface = ApiSurface()

    @surface.get("/store-tag")
    async def store_tag(*, store: _Store) -> dict[str, str]:
        return {"tag": store.tag}

    runtime = build(app)
    async with runtime:
        api = build_http_app(runtime, surface)
        with TestClient(api) as client:
            r = client.get("/store-tag")
            assert r.status_code == 200
            assert r.json() == {"tag": "store-ok"}


def test_api_surface_expose_kwarg_rejected() -> None:
    surface = ApiSurface()
    with pytest.raises(TypeError, match=r"expose="):

        @surface.get("/x", expose=["api"])
        async def _h() -> None:
            return None


def test_api_surface_pops_authorize_before_fastapi() -> None:
    """``authorize`` is consumed here; ``fastapi_kwargs`` does not carry it."""
    surface = ApiSurface()

    async def _gate() -> bool:
        return True

    @surface.get("/x", authorize=_gate)
    async def _h() -> None:
        return None

    assert len(surface.routes) == 1
    route = surface.routes[0]
    assert route.authorize is _gate
    assert "authorize" not in route.fastapi_kwargs


@pytest.mark.asyncio
async def test_api_surface_method_specific_decorators() -> None:
    """Each verb decorator records the correct HTTP method."""
    surface = ApiSurface()

    @surface.put("/a")
    async def _a() -> None: ...

    @surface.delete("/b")
    async def _b() -> None: ...

    @surface.patch("/c")
    async def _c() -> None: ...

    methods = {r.path: r.method for r in surface.routes}
    assert methods == {"/a": "PUT", "/b": "DELETE", "/c": "PATCH"}
