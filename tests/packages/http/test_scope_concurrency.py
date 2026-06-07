"""Per-call DI scope under concurrent HTTP requests.

Per ``di-per-call-scope`` (ADR 0009 + ADR 0020): a ``Scope.SCOPED``
provider returns a fresh instance for each tool dispatch. The HTTP
substrate must honour this without coupling between concurrent
requests — the wrapper opens ``Container.call_scope`` per request, so
two concurrent requests dispatching the same tool MUST see distinct
``Scope.SCOPED`` instances.
"""

from __future__ import annotations

import asyncio

import httpx

import a2kit
from a2kit.packages.http import build_http_app
from a2kit.runtime import build


class _ScopedThing:
    """Per-dispatch unique marker — fresh instance per Container.call_scope."""

    counter = 0

    def __init__(self) -> None:
        type(self).counter += 1
        self.id = type(self).counter


async def test_concurrent_requests_get_distinct_scoped_instances() -> None:
    """Two concurrent POST /api/<tool> calls observe different SCOPED instances."""

    barrier = asyncio.Barrier(2)

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def ping(self, *, thing: _ScopedThing) -> dict[str, int]:
            # Park both requests inside their respective call_scope, so
            # the "same instance" failure mode (a leaking singleton)
            # cannot be masked by request serialisation.
            await barrier.wait()
            return {"id": thing.id}

    app = a2kit.App("scope-test").add_router(R()).provide(_ScopedThing, per_call=True)
    runtime = build(app)

    async with runtime:
        fastapi_app = build_http_app(runtime)
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r1, r2 = await asyncio.gather(
                client.post("/ping", json={}),
                client.post("/ping", json={}),
            )

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    id_a = r1.json()["id"]
    id_b = r2.json()["id"]
    assert id_a != id_b, f"SCOPED provider returned the same instance ({id_a}) under concurrent requests — per-call scope is broken"
