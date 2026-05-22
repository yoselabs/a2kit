"""``a2kit.packages.rest.build_rest_app`` — the minimal REST sub-app."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.testclient import TestClient

import a2kit
from a2kit.packages.rest import build_rest_app


def test_build_rest_app_returns_asgi_app() -> None:
    rest = build_rest_app(a2kit.App("test"))
    assert isinstance(rest, Starlette)
    assert callable(rest)


def test_rest_app_carries_only_framework_routes() -> None:
    """The minimal slice ships only the health + OpenAPI routes — no projected tools."""
    rest = build_rest_app(a2kit.App("test"))
    paths = {getattr(r, "path", None) for r in rest.routes}
    assert paths == {"/health", "/openapi.json"}


def test_health_route_responds_with_success() -> None:
    rest = build_rest_app(a2kit.App("test"))
    with TestClient(rest) as client:
        resp = client.get("/health")
    assert resp.status_code == 200


def test_openapi_document_info_reflects_app_name() -> None:
    rest = build_rest_app(a2kit.App("inventory-api"))
    with TestClient(rest) as client:
        resp = client.get("/openapi.json")
    assert resp.status_code == 200
    doc = resp.json()
    assert "openapi" in doc
    assert doc["info"]["title"] == "inventory-api"
    assert doc["paths"] == {}
