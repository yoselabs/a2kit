"""BDD: the supported spoke client round-trips verbs over a real UDS.

Per `internal-spoke`: the client dials the socket and invokes verbs by
canonical name; its reachable set is the API surface's projected catalog
(no second catalog); auth failures and unknown verbs surface as
`SpokeError`.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

import a2kit
from a2kit.packages.auth import TokenAuth
from a2kit.packages.context import Principal
from a2kit.packages.http import build_http_app
from a2kit.packages.serve import _make_uds_socket
from a2kit.packages.spoke import SpokeError, client
from a2kit.runtime import build
from a2kit.testing import app_of


class _Store:
    def __init__(self) -> None:
        self.items: list[str] = []


def _app(live: dict[str, Principal]) -> a2kit.App:
    class R(a2kit.Router):
        slug = "store"

        @a2kit.write()
        async def add(self, *, item: str, store: _Store) -> dict[str, Any]:
            store.items.append(item)
            return {"count": len(store.items)}

        @a2kit.read()
        async def items(self, *, store: _Store) -> dict[str, Any]:
            return {"items": list(store.items)}

    app = app_of("spoke-client", R())
    app.provide(_Store, lambda: _Store())
    app.auth(TokenAuth(resolve=lambda t: live.get(t)))
    return app


class _SpokeServer:
    """Run the spoke over a UDS in a background thread for sync-client tests."""

    def __init__(self, runtime: Any, uds: str) -> None:
        self._runtime = runtime
        self._uds = uds
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> _SpokeServer:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        assert self._ready.wait(15), "spoke server did not start"
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(15)

    def _run(self) -> None:
        import uvicorn

        async def main() -> None:
            spoke = build_http_app(self._runtime, auth_target="internal")
            server = uvicorn.Server(uvicorn.Config(spoke, log_level="warning"))
            sock = _make_uds_socket(self._uds)
            async with self._runtime:
                task = asyncio.create_task(server.serve(sockets=[sock]))
                while not server.started:
                    await asyncio.sleep(0.01)
                self._ready.set()
                while not self._stop.is_set():
                    await asyncio.sleep(0.05)
                server.should_exit = True
                await task

        asyncio.run(main())


def test_client_invokes_verbs_by_canonical_name(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    live = {"lease": Principal(subject="job", scopes=frozenset({"jobs"}), claims={}, issued_by="runner")}
    runtime = build(_app(live))
    with _SpokeServer(runtime, "spoke.sock"), client("spoke.sock", "lease") as c:
        assert c.invoke("store_add", item="alpha") == {"count": 1}
        assert c.invoke("store_items") == {"items": ["alpha"]}


def test_client_bad_token_raises_spokeerror(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    runtime = build(_app({}))
    with (
        _SpokeServer(runtime, "spoke.sock"),
        client("spoke.sock", "nope") as c,
        pytest.raises(SpokeError) as exc,
    ):
        c.invoke("store_items")
    assert exc.value.status == 401


def test_client_unknown_verb_404s(tmp_path: Any, monkeypatch: Any) -> None:
    """The client carries no catalog — an unprojected name 404s from the spoke."""
    monkeypatch.chdir(tmp_path)
    live = {"lease": Principal(subject="job", scopes=frozenset({"jobs"}), claims={}, issued_by="runner")}
    runtime = build(_app(live))
    with (
        _SpokeServer(runtime, "spoke.sock"),
        client("spoke.sock", "lease") as c,
        pytest.raises(SpokeError) as exc,
    ):
        c.invoke("does_not_exist")
    assert exc.value.status == 404


def test_spoke_catalog_equals_api_surface_catalog() -> None:
    """Reachable verb set == the API surface's projected catalog (no second catalog)."""
    live = {"lease": Principal(subject="job", scopes=frozenset({"jobs"}), claims={}, issued_by="runner")}
    runtime = build(_app(live))
    spoke_paths = set(build_http_app(runtime, auth_target="internal").openapi()["paths"])
    api_paths = set(build_http_app(runtime).openapi()["paths"])
    assert spoke_paths == api_paths
    assert {"/store_add", "/store_items"} <= spoke_paths
