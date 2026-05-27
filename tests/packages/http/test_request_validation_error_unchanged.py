"""FastAPI ``RequestValidationError`` handling is unchanged by ``dispatch-pipeline-parity-on-http``.

The refactor shrinks ``_install_typed_error_handlers`` to the AppError +
catch-all paths only. ``RequestValidationError`` (FastAPI's body-parsing /
schema-validation exception) was never explicitly handled — FastAPI's
default handler covers it, returning HTTP 422 with a ``{"detail": [...]}``
body. This test pins that baseline so a future shrink of the fallback
handler doesn't silently change the validation-error wire shape.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import a2kit
from a2kit.packages.http.build import build_http_app
from a2kit.runtime import build


def test_invalid_body_returns_422_with_fastapi_default_shape() -> None:
    class R(a2kit.Router):
        slug = "v"

        @a2kit.read()
        async def echo(self, *, id: str) -> dict[str, str]:
            return {"id": id}

        tools = (echo,)

    app = a2kit.App("validation-test").add_router(R())
    client = TestClient(build_http_app(build(app)), raise_server_exceptions=False)

    # Missing required `id` field. FastAPI rejects at body parse with 422.
    resp = client.post("/echo", json={})
    assert resp.status_code == 422
    body = resp.json()
    # FastAPI's default validation-error shape: `{"detail": [{...}]}`.
    # NOT the typed envelope shape `{"error": {...}}` — validation errors
    # are framework-layer, not tool-body AppErrors.
    assert "detail" in body, f"expected FastAPI default `detail` key, got: {body}"
    assert isinstance(body["detail"], list)
    assert "error" not in body, "validation errors must NOT be wrapped in the typed envelope"


def test_wrong_content_type_returns_422_not_typed_envelope() -> None:
    """Sending non-JSON content also lands in the framework-validation path."""

    class R(a2kit.Router):
        slug = "v2"

        @a2kit.read()
        async def echo(self, *, id: str) -> dict[str, str]:
            return {"id": id}

        tools = (echo,)

    app = a2kit.App("validation-test-2").add_router(R())
    client = TestClient(build_http_app(build(app)), raise_server_exceptions=False)

    # Wrong shape: list instead of an object.
    resp = client.post("/echo", json=["not", "an", "object"])
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body
    assert "error" not in body
