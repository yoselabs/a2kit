"""``a2kit.packages.serve.build_parent_app`` — the multiplex parent app.

The route-shape tests build the parent app and inspect its mounts. The
end-to-end test runs the parent under a real uvicorn server in a
background thread and proves: the REST health route answers over
``/api``, a DI-backed tool answers over ``/mcp``, and the ``App``
lifecycle is entered exactly once for the whole process.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

import a2kit
from a2kit.packages.serve import build_parent_app
from a2kit.runtime import AppRuntime
from a2kit.testing import app_of


# --------------------------------------------------------------- DI test app


class _Store:
    tag = "store-ok"


def _build_di_app() -> a2kit.App:
    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def echo(self, *, msg: str, store: _Store) -> dict[str, Any]:
            return {"msg": msg, "tag": store.tag}

    return app_of("multiplex-demo", R()).provide(_Store, lambda: _Store())


# ------------------------------------------------------------- server harness


@contextlib.contextmanager
def _running(parent: Any) -> Iterator[int]:
    """Run ``parent`` under uvicorn on a kernel-assigned port in a daemon thread.

    ``port=0`` lets uvicorn bind a free port directly and report it back —
    no bind-read-close-rebind window for another process to race into.
    """
    import uvicorn

    config = uvicorn.Config(parent, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 15
        while not server.started:
            if time.time() > deadline:
                raise RuntimeError("uvicorn server did not start within 15s")
            time.sleep(0.02)
        port = int(server.servers[0].sockets[0].getsockname()[1])
        yield port
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        if thread.is_alive():
            raise RuntimeError("uvicorn server thread did not exit within 15s")


def _mount_paths(parent: Any) -> set[Any]:
    return {getattr(r, "path", None) for r in parent.routes}


# ------------------------------------------------------------ route-shape tests


def test_build_parent_app_auto_mounts_both_for_projection_app() -> None:
    """Projection tools default to both surfaces — both mounts present."""
    parent = build_parent_app(_build_di_app())
    assert _mount_paths(parent) == {"/mcp", "/api"}


def test_build_parent_app_mcp_only_when_only_mcp_registrations() -> None:
    """``@app.mcp.tool``-only app mounts only ``/mcp``."""
    app = app_of("mcp-only")

    @app.mcp.tool(name="hello")
    async def _h() -> dict[str, str]:
        return {"v": "hi"}

    parent = build_parent_app(app)
    assert _mount_paths(parent) == {"/mcp"}


def test_build_parent_app_api_only_when_only_api_registrations() -> None:
    """``@app.api.<method>``-only app mounts only ``/api``."""
    app = app_of("api-only")

    @app.api.get("/version")
    async def _v() -> dict[str, str]:
        return {"v": "1"}

    parent = build_parent_app(app)
    assert _mount_paths(parent) == {"/api"}


def test_build_parent_app_requires_a_surface() -> None:
    """Empty App with no registrations raises ValueError on build."""
    with pytest.raises(ValueError, match="no registered surface has registrations"):
        build_parent_app(app_of("empty"))


# --------------------------------------------------------------- end-to-end


def test_api_only_parent_starts_and_serves_health() -> None:
    """An ``@app.api.*``-only parent runs its lifespan and serves /api/health."""
    from starlette.testclient import TestClient

    app = app_of("api-only")

    @app.api.get("/version")
    async def _v() -> dict[str, str]:
        return {"v": "1"}

    parent = build_parent_app(app)
    with TestClient(parent) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert resp.json() == {"v": "1"}


@pytest.mark.asyncio
async def test_multiplexed_serve_health_di_tool_and_single_lifecycle() -> None:
    """One process serves /api health + /mcp DI tool; App enters exactly once."""
    import httpx
    from fastmcp import Client

    app = _build_di_app()
    parent = build_parent_app(app)

    orig_aenter = AppRuntime.__aenter__
    orig_aexit = AppRuntime.__aexit__
    enters: list[Any] = []
    exits: list[Any] = []

    async def _counting_aenter(self: AppRuntime) -> Any:
        enters.append(self)
        return await orig_aenter(self)

    async def _counting_aexit(self: AppRuntime, *exc: Any) -> Any:
        exits.append(self)
        return await orig_aexit(self, *exc)

    with (
        pytest.MonkeyPatch.context() as mp,
    ):
        mp.setattr(AppRuntime, "__aenter__", _counting_aenter)
        mp.setattr(AppRuntime, "__aexit__", _counting_aexit)
        with _running(parent) as port:
            health = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=10)
            async with Client(f"http://127.0.0.1:{port}/mcp") as client:
                result = await client.call_tool("demo_echo", {"msg": "hi"})

    assert health.status_code == 200
    payload = result.data if getattr(result, "data", None) is not None else result.structured_content
    assert payload == {"msg": "hi", "tag": "store-ok"}

    # The parent app builds one AppRuntime and owns its single lifecycle —
    # neither the MCP nor the REST mount entered or exited it themselves.
    assert len(enters) == 1, f"AppRuntime entered {len(enters)} times — expected 1"
    assert len(exits) == 1, f"AppRuntime exited {len(exits)} times — expected 1"


# ----------------------------------------------- spoke: enter_runtime + mcp_options


@pytest.mark.asyncio
async def test_build_parent_app_enter_runtime_false_does_not_enter() -> None:
    """`enter_runtime=False`: the parent lifespan forwards surfaces but does not
    enter the runtime — the caller (spoke serve path) owns the single
    `async with runtime:`."""
    from a2kit.runtime import build

    runtime = build(_build_di_app())

    orig_aenter = AppRuntime.__aenter__
    enters: list[Any] = []

    async def _counting_aenter(self: AppRuntime) -> Any:
        enters.append(self)
        return await orig_aenter(self)

    with patch.object(AppRuntime, "__aenter__", _counting_aenter):
        parent = build_parent_app(runtime, enter_runtime=False)
        async with parent.router.lifespan_context(parent):
            assert enters == []  # runtime NOT entered by the parent
        # And the caller can own it:
        async with runtime:
            assert len(enters) == 1


def test_build_parent_app_threads_mcp_options() -> None:
    """`mcp_options` reach `build_mcp_server` (with own_app_lifecycle=False)."""
    from a2kit.runtime import build

    runtime = build(_build_di_app())
    captured: dict[str, Any] = {}

    real = None
    from a2kit.packages.mcp import server as _mcp_server

    real = _mcp_server.build_mcp_server

    def _spy(rt: Any, **kw: Any) -> Any:
        captured.update(kw)
        return real(rt, **kw)

    with patch.object(_mcp_server, "build_mcp_server", _spy):
        build_parent_app(runtime, mcp_options={"compact": True, "tool_selection": "demo_echo"})

    assert captured.get("compact") is True
    assert captured.get("tool_selection") == "demo_echo"
    assert captured.get("own_app_lifecycle") is False


def test_make_uds_socket_is_0600(tmp_path: Any, monkeypatch: Any) -> None:
    """The spoke socket node is created owner-only (0600)."""
    import stat
    from pathlib import Path

    from a2kit.packages.serve import _make_uds_socket

    # AF_UNIX paths are length-capped (~104 on macOS); bind a short
    # relative name from inside the tmp dir.
    monkeypatch.chdir(tmp_path)
    path = "spoke.sock"
    sock = _make_uds_socket(path)
    try:
        mode = stat.S_IMODE(Path(path).stat().st_mode)
        assert mode == 0o600, oct(mode)
    finally:
        sock.close()
        Path(path).unlink()


# ----------------------------------------------- serve_process + _serve (one engine)


def test_serve_process_delegates_to_one_serve(monkeypatch: Any) -> None:
    """Every path runs through ``asyncio.run(_serve(...))`` — no bare branches.

    ``serve_process`` composes the args (threading ``runtime.serve_services``)
    and delegates; there is no longer a transport-specific branch in it.
    """
    from a2kit.packages import serve as serve_mod
    from a2kit.runtime import build

    captured: dict[str, Any] = {}

    async def _fake_serve(rt: Any, **kw: Any) -> None:
        captured["rt"] = rt
        captured.update(kw)

    monkeypatch.setattr(serve_mod, "_serve", _fake_serve)
    serve_mod.serve_process(build(_build_di_app()), transport="http", host="h", port=7, internal_uds="sentinel.sock", mcp_options={})
    assert captured["transport"] == "http"
    assert captured["host"] == "h"
    assert captured["port"] == 7
    assert captured["uds_path"] == "sentinel.sock"
    assert captured["services"] == ()  # no services registered on this app


def test_public_listener_stdio_uses_run_stdio_async(monkeypatch: Any) -> None:
    """stdio public listener → ``build_mcp_server(own_app_lifecycle=False).run_stdio_async()``."""
    import a2kit.packages.mcp as mcp_pkg
    from a2kit.packages.serve import _public_listener
    from a2kit.runtime import build

    captured: dict[str, Any] = {}

    class _Srv:
        def run_stdio_async(self) -> Any:
            async def _co() -> None: ...

            return _co()

    def _spy(rt: Any, **kw: Any) -> Any:
        captured.update(kw)
        return _Srv()

    monkeypatch.setattr(mcp_pkg, "build_mcp_server", _spy)
    co = _public_listener(build(_build_di_app()), transport="stdio", host="h", port=0, mcp_options={"compact": True})
    try:
        assert captured["own_app_lifecycle"] is False
        assert captured["compact"] is True
    finally:
        co.close()


def test_public_listener_http_uses_parent_enter_runtime_false(monkeypatch: Any) -> None:
    """http public listener → ``build_parent_app(enter_runtime=False)`` under uvicorn."""
    from a2kit.packages import serve as serve_mod
    from a2kit.runtime import build

    captured: dict[str, Any] = {}
    real = serve_mod.build_parent_app

    def _spy(rt: Any, **kw: Any) -> Any:
        captured.update(kw)
        return real(rt, **kw)

    monkeypatch.setattr(serve_mod, "build_parent_app", _spy)
    co = serve_mod._public_listener(build(_build_di_app()), transport="http", host="127.0.0.1", port=0, mcp_options={})
    try:
        assert captured.get("enter_runtime") is False
    finally:
        co.close()


@pytest.mark.asyncio
async def test_serve_runs_public_and_uds(tmp_path: Any, monkeypatch: Any) -> None:
    """`_serve` (http) serves both the parent and the UDS spoke under one runtime."""
    import asyncio
    from pathlib import Path

    import httpx

    from a2kit.packages.serve import _serve
    from a2kit.runtime import build

    monkeypatch.chdir(tmp_path)
    runtime = build(_build_di_app())
    task = asyncio.create_task(
        _serve(
            runtime,
            transport="http",
            host="127.0.0.1",
            port=0,
            uds_path="spoke.sock",
            services=(),
            mcp_options={},
        )
    )
    try:
        for _ in range(500):
            if Path("spoke.sock").exists():
                break
            await asyncio.sleep(0.01)
        assert Path("spoke.sock").exists()

        # No internal auth on this app → the spoke dispatches openly.
        transport = httpx.AsyncHTTPTransport(uds="spoke.sock")
        async with httpx.AsyncClient(transport=transport, base_url="http://spoke") as c:
            resp = None
            for _ in range(200):
                try:
                    resp = await c.post("/demo_echo", json={"msg": "hi"})
                    break
                except httpx.HTTPError:
                    await asyncio.sleep(0.02)
            assert resp is not None and resp.status_code == 200, getattr(resp, "text", "no response")
            assert resp.json() == {"msg": "hi", "tag": "store-ok"}
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    # `_cleanup_uds` removed the socket node on shutdown.
    assert not Path("spoke.sock").exists()
