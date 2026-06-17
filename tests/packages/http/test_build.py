"""``build_http_app`` — FastAPI sub-app builder smoke tests."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

import a2kit
from a2kit.packages.auth import AuthSpec
from a2kit.packages.auth._asgi import send_401
from a2kit.packages.context import Principal, request_scope
from a2kit.packages.http import ApiSurface, build_http_app
from a2kit.runtime import build
from a2kit.testing import app_of


class _Store:
    tag = "store-ok"


def _build_di_app() -> a2kit.App:
    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def echo(self, *, msg: str, store: _Store) -> dict[str, Any]:
            return {"msg": msg, "tag": store.tag}

    return app_of("http-demo", R()).provide(_Store, lambda: _Store())


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
            r = client.post("/demo_echo", json={"msg": "hi"})
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
            r = client.get("/demo_echo")
            assert r.status_code == 405


def _build_visibility_app() -> a2kit.App:
    """App with one verb per placement tier so the HTTP surface filter is exercised."""

    class R(a2kit.Router):
        slug = "ops"

        @a2kit.read()
        async def public_op(self, *, x: int = 0) -> dict[str, int]:
            return {"x": x}

        @a2kit.write(surfaces=("cli",))
        async def trust_vault(self, *, path: str = "") -> dict[str, str]:
            return {"path": path}

        @a2kit.read(surfaces={"cli": "unlisted"})
        async def secret_op(self, *, y: int = 0) -> dict[str, int]:
            return {"y": y}

    return app_of("vis-demo", R())


@pytest.mark.asyncio
async def test_cli_only_verb_not_mounted_on_http() -> None:
    """`surfaces=("cli",)` must not be reachable over HTTP — no route, 404."""
    runtime = build(_build_visibility_app())
    async with runtime:
        api = build_http_app(runtime)
        mounted = {getattr(r, "path", None) for r in api.routes}
        assert "/ops_public_op" in mounted
        assert "/ops_trust_vault" not in mounted, "CLI-only verb leaked onto HTTP"
        with TestClient(api) as client:
            assert client.post("/ops_trust_vault", json={"path": "x"}).status_code == 404


@pytest.mark.asyncio
async def test_hidden_verb_not_mounted_on_http() -> None:
    """`surfaces={"cli": "unlisted"}` must not be reachable over HTTP — matches MCP."""
    runtime = build(_build_visibility_app())
    async with runtime:
        api = build_http_app(runtime)
        mounted = {getattr(r, "path", None) for r in api.routes}
        assert "/ops_secret_op" not in mounted, "hidden verb leaked onto HTTP"


@pytest.mark.asyncio
async def test_http_no_di_override_for_non_all_visibility() -> None:
    """No dependency_overrides entry for an unmounted (cli-only) verb."""
    from tests.packages.http._vault_fixture import Vault, VaultRouter

    app = app_of("vis-di", VaultRouter()).provide(Vault, lambda: Vault())
    runtime = build(app)
    async with runtime:
        api = build_http_app(runtime)
        assert Vault not in api.dependency_overrides, "DI override registered for an unmounted verb"


@pytest.mark.asyncio
async def test_http_and_mcp_apply_same_visibility_rule() -> None:
    """HTTP mounts exactly the network-visible verbs MCP registers — one rule, two surfaces."""
    from a2kit.packages.mcp.server import build_mcp_server

    app = _build_visibility_app()
    server = build_mcp_server(app, code_mode=False)
    mcp_names = {t.name for t in await server.list_tools()}

    runtime = build(_build_visibility_app())
    async with runtime:
        api = build_http_app(runtime)
        http_projection = {
            getattr(r, "path", "").lstrip("/")
            for r in api.routes
            if getattr(r, "path", "").lstrip("/") in {"ops_public_op", "ops_trust_vault", "ops_secret_op"}
        }

    assert http_projection == {"ops_public_op"}
    assert "ops_public_op" in mcp_names
    assert {"ops_trust_vault", "ops_secret_op"} & mcp_names == set()
    assert {"ops_trust_vault", "ops_secret_op"} & http_projection == set()


@pytest.mark.asyncio
async def test_openapi_document_contains_projection_tool() -> None:
    runtime = build(_build_di_app())
    async with runtime:
        api = build_http_app(runtime)
        with TestClient(api) as client:
            r = client.get("/openapi.json")
            assert r.status_code == 200
            doc = r.json()
            assert "/demo_echo" in doc["paths"]
            assert "post" in doc["paths"]["/demo_echo"]
            # DI dep `store` must NOT appear in the request body schema.
            post_op = doc["paths"]["/demo_echo"]["post"]
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


def test_api_surface_surfaces_kwarg_rejected() -> None:
    surface = ApiSurface()
    with pytest.raises(TypeError, match=r"surfaces="):

        @surface.get("/x", surfaces=["api"])
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


def _custom_auth_app() -> tuple[a2kit.App, type]:
    """An App whose auth strategy is a custom `AuthSpec` unknown to build.py.

    Proves the generic mount path: `_install_auth_middlewares` mounts any
    `target`-matched spec via `spec.build_middleware()` with no per-class
    isinstance branch.
    """
    from typing import Any as _Any

    class _HeaderAuth(AuthSpec):
        target = "internal"

        def build_middleware(self) -> _Any:
            def factory(app: _Any) -> _Any:
                async def mw(scope: dict[str, _Any], receive: _Any, send: _Any) -> None:
                    if scope.get("type") != "http":
                        await app(scope, receive, send)
                        return
                    headers = dict(scope.get("headers", ()))
                    if headers.get(b"x-spoke-token") != b"let-me-in":
                        await send_401(send, "missing token")
                        return
                    token = request_scope.publish(Principal(subject="job-7", scopes=frozenset({"jobs"}), claims={}, issued_by="custom"))
                    try:
                        await app(scope, receive, send)
                    finally:
                        request_scope.reset(token)

                return mw

            return factory

    app = app_of("custom-auth")
    app.auth(_HeaderAuth())

    @app.api.get("/me", response_model=dict)
    async def me(*, principal: Principal) -> dict[str, str]:
        return {"subject": principal.subject}

    return app, _HeaderAuth


def test_custom_authspec_mounts_via_build_middleware() -> None:
    """A non-bundled AuthSpec authenticates through the generic mount loop."""
    app, _ = _custom_auth_app()
    runtime = build(app)
    client = TestClient(build_http_app(runtime, auth_target="internal"))

    ok = client.get("/me", headers={"X-Spoke-Token": "let-me-in"})
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"subject": "job-7"}

    denied = client.get("/me")
    assert denied.status_code == 401
    assert denied.json()["error"] == "authentication_failed"


def test_custom_authspec_not_mounted_for_other_target() -> None:
    """Building for `auth_target='api'` does not mount the internal-targeted spec."""
    app, _ = _custom_auth_app()
    runtime = build(app)
    sub_app = build_http_app(runtime, auth_target="api")
    classes = [getattr(m.cls, "__name__", "") for m in sub_app.user_middleware]
    assert "_BareAsgiMiddleware" not in classes
