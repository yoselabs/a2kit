"""HTTP surface: typed-error envelope responses (Group 15).

Maps AppError kind → status code (with per-class override) and emits
``{"error": <envelope dict>}`` as the JSON body.
"""

from __future__ import annotations

from typing import Annotated

from fastapi.testclient import TestClient

import a2kit
from a2effect import AppError, Raises
from a2effect.errors import InfrastructureError
from a2kit.packages.http.build import build_http_app
from a2kit.runtime import build


class _NotFound(AppError):
    kind = "input"
    http_status = 404
    hint = "verify the id from list_memories"


class _OopsBug(AppError):
    kind = "bug"


def _make_client(router_cls: type[a2kit.Router]) -> TestClient:
    app = a2kit.App("t").add_router(router_cls())
    fast_app = build_http_app(build(app))
    return TestClient(fast_app, raise_server_exceptions=False)


async def test_not_found_subclass_maps_to_404_with_envelope() -> None:
    class R(a2kit.Router):
        slug = "mem"

        @a2kit.read()
        async def fetch(self, *, id: str) -> Annotated[dict, Raises(_NotFound)]:
            raise _NotFound(f"memory id {id!r} does not exist", details={"id": id})

        tools = (fetch,)

    client = _make_client(R)
    resp = client.post("/fetch", json={"id": "abc"})
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["type"] == "_NotFound"
    assert body["error"]["kind"] == "input"
    assert body["error"]["base_kind"] == "input"
    assert body["error"]["details"] == {"id": "abc"}
    assert body["error"]["hint"] == "verify the id from list_memories"
    assert body["error"]["envelope_version"] == "1"
    assert resp.headers["content-type"].startswith("application/json")


async def test_infra_error_defaults_to_503() -> None:
    class R(a2kit.Router):
        slug = "svc"

        @a2kit.read()
        async def call(self, *, x: int) -> Annotated[dict, Raises(InfrastructureError)]:
            raise InfrastructureError("downstream gone")

        tools = (call,)

    client = _make_client(R)
    resp = client.post("/call", json={"x": 1})
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["kind"] == "infra"
    assert body["error"]["retryable"] is True


async def test_bug_kind_maps_to_500() -> None:
    class R(a2kit.Router):
        slug = "broken"

        @a2kit.read()
        async def boom(self, *, x: int) -> Annotated[dict, Raises(_OopsBug)]:
            raise _OopsBug("internal explosion")

        tools = (boom,)

    client = _make_client(R)
    resp = client.post("/boom", json={"x": 1})
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["kind"] == "bug"
    assert body["error"]["type"] == "_OopsBug"


async def test_non_app_error_quarantined_to_500_envelope() -> None:
    class R(a2kit.Router):
        slug = "raw"

        @a2kit.read()
        async def boom(self, *, x: int) -> dict:
            raise KeyError(f"missing-{x}")

        tools = (boom,)

    client = _make_client(R)
    resp = client.post("/boom", json={"x": 1})
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["type"] == "UnexpectedDefect"
    assert body["error"]["kind"] == "bug"
