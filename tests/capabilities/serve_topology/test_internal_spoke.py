"""e2e: the internal spoke over a real Unix domain socket.

Per `serve-topology` + `internal-spoke`: a first-party caller reaches the
dispatcher over a `0600` UDS, authenticated by `TokenAuth`, and writes
through the **same** `SINGLETON` store a public (TCP) call resolves. The
public surfaces and their auth are unaffected.
"""

from __future__ import annotations

import asyncio
import os
import stat
from typing import Any

import httpx
import pytest

import a2kit
from a2kit.packages.auth import TokenAuth
from a2kit.packages.context import Principal
from a2kit.packages.http import build_http_app
from a2kit.packages.serve import _make_uds_socket
from a2kit.runtime import build
from a2kit.testing import app_of


class _Store:
    def __init__(self) -> None:
        self.items: list[str] = []


def _build_app(live: dict[str, Principal]) -> a2kit.App:
    class R(a2kit.Router):
        slug = "store"

        @a2kit.write()
        async def add(self, *, item: str, store: _Store) -> dict[str, Any]:
            store.items.append(item)
            return {"count": len(store.items)}

        @a2kit.read()
        async def items(self, *, store: _Store) -> dict[str, Any]:
            return {"items": list(store.items)}

    app = app_of("spoke-e2e", R())
    app.provide(_Store, lambda: _Store())
    app.auth(TokenAuth(resolve=lambda t: live.get(t)))
    return app


@pytest.mark.asyncio
async def test_spoke_over_uds_authenticates_and_shares_store(tmp_path: Any, monkeypatch: Any) -> None:
    import uvicorn

    live = {"lease": Principal(subject="job", scopes=frozenset({"jobs"}), claims={}, issued_by="runner")}
    runtime = build(_build_app(live))

    # AF_UNIX path is length-capped on macOS (both bind AND connect); use a
    # short relative name from inside the tmp dir for both sides.
    monkeypatch.chdir(tmp_path)
    uds = "spoke.sock"
    spoke = build_http_app(runtime, auth_target="internal")
    sock = _make_uds_socket(uds)
    server = uvicorn.Server(uvicorn.Config(spoke, log_level="warning"))
    serve_task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with runtime:
            for _ in range(500):
                if server.started:
                    break
                await asyncio.sleep(0.01)
            assert server.started, "spoke uvicorn did not start"

            # Socket node is owner-only.
            assert stat.S_IMODE(os.stat(uds).st_mode) == 0o600

            transport = httpx.AsyncHTTPTransport(uds=uds)
            async with httpx.AsyncClient(transport=transport, base_url="http://spoke") as c:
                # No token → 401, public OAuth/API-key path never consulted.
                denied = await c.post("/store_add", json={"item": "x"})
                assert denied.status_code == 401
                assert denied.json()["error"] == "authentication_failed"

                # Valid lease → dispatch with the lease's Principal.
                hdr = {"X-A2kit-Token": "lease"}
                wrote = await c.post("/store_add", headers=hdr, json={"item": "alpha"})
                assert wrote.status_code == 200, wrote.text
                assert wrote.json() == {"count": 1}

                # Read over the spoke reflects the write — one persisted store.
                read = await c.post("/store_items", headers=hdr, json={})
                assert read.status_code == 200, read.text
                assert read.json() == {"items": ["alpha"]}

            # Same SINGLETON the TCP/public listener would resolve: the
            # runtime's root container hands back the very instance the
            # spoke request wrote through — no second store handle.
            store = await runtime.container().get(_Store)
            assert store.items == ["alpha"]
    finally:
        server.should_exit = True
        await serve_task
