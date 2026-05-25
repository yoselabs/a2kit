"""BDD: APIKeyAuth end-to-end on the FastAPI sub-app.

Per `auth-spec` + `tool-authorization`:
- Valid key resolves to a `Principal` with the declared subject/scopes.
- Missing header → 401 with the documented JSON envelope.
- Unknown key → 401, no leak of registered set.
- Valid key + denying `authorize=` → 403 (gate runs after auth).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import a2kit
from a2kit.packages.auth import ApiKey, APIKeyAuth
from a2kit.packages.context import Principal
from a2kit.packages.http import build_http_app
from a2kit.runtime import build


def _admin_only(*, principal: Principal) -> bool:
    return "admin" in principal.scopes


def _build_app() -> a2kit.App:
    app = a2kit.App("auth-apikey")
    app.auth(
        APIKeyAuth(
            keys=[
                ApiKey(value="k-admin", subject="alice", scopes=frozenset({"admin"})),
                ApiKey(value="k-reader", subject="bob", scopes=frozenset({"reader"})),
            ]
        )
    )

    @app.api.get("/me", response_model=dict)
    async def me(*, principal: Principal) -> dict[str, str]:
        return {"subject": principal.subject}

    @app.api.get("/admin", response_model=dict, authorize=_admin_only)
    async def admin(*, principal: Principal) -> dict[str, str]:
        return {"subject": principal.subject}

    return app


def test_valid_admin_key_resolves_principal_and_returns_200() -> None:
    runtime = build(_build_app())
    client = TestClient(build_http_app(runtime))
    resp = client.get("/me", headers={"X-API-Key": "k-admin"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"subject": "alice"}


def test_missing_header_returns_401() -> None:
    runtime = build(_build_app())
    client = TestClient(build_http_app(runtime))
    resp = client.get("/me")
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"] == "authentication_failed"
    assert "missing" in body["reason"].lower()


def test_invalid_key_returns_401_without_leak() -> None:
    runtime = build(_build_app())
    client = TestClient(build_http_app(runtime))
    resp = client.get("/me", headers={"X-API-Key": "WRONG"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"] == "authentication_failed"
    # Reason MUST NOT echo any registered key.
    assert "k-admin" not in resp.text
    assert "k-reader" not in resp.text


def test_admin_authorize_denies_non_admin_with_403() -> None:
    runtime = build(_build_app())
    client = TestClient(build_http_app(runtime))
    resp = client.get("/admin", headers={"X-API-Key": "k-reader"})
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body["error"]["type"] == "AuthorizationDenied"
    assert body["error"]["kind"] == "auth"


def test_admin_authorize_passes_for_admin_with_200() -> None:
    runtime = build(_build_app())
    client = TestClient(build_http_app(runtime))
    resp = client.get("/admin", headers={"X-API-Key": "k-admin"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"subject": "alice"}


def test_no_auth_app_has_no_middleware_mounted() -> None:
    """Per `http-surface`: empty auth registry → no auth middleware."""
    app = a2kit.App("no-auth")

    @app.api.get("/x", response_model=dict)
    async def _x() -> dict[str, str]:
        return {"ok": "yes"}

    runtime = build(app)
    sub_app = build_http_app(runtime)
    # Inspect `user_middleware` — Starlette's registered middleware list.
    classes = [getattr(m.cls, "__name__", "") for m in sub_app.user_middleware]
    assert "_BareAsgiMiddleware" not in classes
