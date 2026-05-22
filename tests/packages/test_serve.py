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

import pytest

import a2kit
from a2kit.packages.serve import build_parent_app
from a2kit.runtime import AppRuntime


# --------------------------------------------------------------- DI test app


class _Store:
    tag = "store-ok"


def _build_di_app() -> a2kit.App:
    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def echo(self, *, msg: str, store: _Store) -> dict[str, Any]:
            return {"msg": msg, "tag": store.tag}

        tools = (echo,)

    return a2kit.App("multiplex-demo").add_router(R()).provide(_Store, lambda: _Store())


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


def test_build_parent_app_mounts_both_surfaces() -> None:
    parent = build_parent_app(a2kit.App("test"), mcp=True, rest=True)
    assert _mount_paths(parent) == {"/mcp", "/api"}


def test_build_parent_app_mcp_only_mounts_mcp_alone() -> None:
    parent = build_parent_app(a2kit.App("test"), mcp=True, rest=False)
    assert _mount_paths(parent) == {"/mcp"}


def test_build_parent_app_rest_only_mounts_rest_alone() -> None:
    parent = build_parent_app(a2kit.App("test"), mcp=False, rest=True)
    assert _mount_paths(parent) == {"/api"}


def test_build_parent_app_requires_a_surface() -> None:
    with pytest.raises(ValueError, match="at least one surface"):
        build_parent_app(a2kit.App("test"), mcp=False, rest=False)


# --------------------------------------------------------------- end-to-end


def test_rest_only_parent_starts_and_serves_health() -> None:
    """A ``rest=True, mcp=False`` parent runs its lifespan and serves /api.

    ``TestClient`` as a context manager drives the parent lifespan — the
    ``AsyncExitStack`` path with one non-FastMCP mount — proving the
    REST-only topology starts cleanly without an MCP session manager.
    """
    from starlette.testclient import TestClient

    parent = build_parent_app(a2kit.App("rest-only"), mcp=False, rest=True)
    with TestClient(parent) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_multiplexed_serve_health_di_tool_and_single_lifecycle() -> None:
    """One process serves /api health + /mcp DI tool; App enters exactly once."""
    import httpx
    from fastmcp import Client

    app = _build_di_app()
    parent = build_parent_app(app, mcp=True, rest=True)

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
                result = await client.call_tool("echo", {"msg": "hi"})

    assert health.status_code == 200
    payload = result.data if getattr(result, "data", None) is not None else result.structured_content
    assert payload == {"msg": "hi", "tag": "store-ok"}

    # The parent app builds one AppRuntime and owns its single lifecycle —
    # neither the MCP nor the REST mount entered or exited it themselves.
    assert len(enters) == 1, f"AppRuntime entered {len(enters)} times — expected 1"
    assert len(exits) == 1, f"AppRuntime exited {len(exits)} times — expected 1"
