"""``build_parent_app(app) -> Starlette`` — the multiplex parent.

Under ``serve --transport=http`` a2kit runs a single process on a single
port. This module builds the a2kit-owned parent ASGI application that
mounts each populated surface as an independent sub-app via the
``Surface`` Protocol: each surface owns its own ``bind(runtime, ...)``
build path and is mounted at ``/{surface.name}``.

**Auto-mount** (post-add-multi-surface + remove-substrate-literal):
each surface in the active :class:`SurfaceRegistry` mounts only when the
runtime carries registrations for it. The bundled surfaces (``mcp``,
``api``) self-register at lazy front-door load; future surfaces register
the same way and mount here without serve-side edits. Projection tools
(``@app.read``/``@app.list``/``@app.write``) default to both bundled
substrates; ``@app.api.<method>`` is FastAPI-only;
``@app.mcp.<feature>`` is FastMCP-only. If no surface has
registrations, the function raises ``ValueError`` — a server with
nothing to serve is a config bug.

The parent owns the **one** ``async with app:`` for the whole process.
Each mounted surface contributes only its transport-scoped lifespan,
forwarded by the parent (a Starlette ``Mount``'s lifespan does not run
unless the parent forwards it). A per-surface ``async with app:`` would
couple shutdowns — the first surface to exit would drain the shared DI
container out from under the others.

Imported only on the ``serve --transport=http`` path — never at
``import a2kit``.
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.routing import Mount

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from typing import Any

    from a2kit.app import App
    from a2kit.runtime import AppRuntime


def _surface_has_registrations(runtime: AppRuntime, surface_name: str) -> bool:
    """True if `runtime` has anything to expose on `surface_name`.

    Honours per-tool `surfaces=`: a projection tool registered with
    `@app.read(surfaces=("mcp",))` does NOT count towards `/api`. Author-
    written surface-native registrations (e.g. `@app.api.<method>` on
    `runtime.api_surface`, `@app.mcp.<feature>` on `runtime.mcp_surface`)
    always count.

    For surfaces beyond the bundled `api`/`mcp` pair we only check the
    per-tool `expose` filter — future surfaces that publish native
    registrations through their own accumulator will need to extend the
    runtime to expose them, then the same filter pattern applies.
    """
    if any(surface_name in d.expose for d in runtime.tools()):
        return True
    if surface_name == "api":
        api = runtime.api_surface
        return api is not None and bool(api.registrations)
    if surface_name == "mcp":
        mcp = runtime.mcp_surface
        return mcp is not None and bool(mcp.registrations)
    return False


def build_parent_app(
    app: App | AppRuntime,
    *,
    enter_runtime: bool = True,
    mcp_options: Mapping[str, Any] | None = None,
) -> Starlette:
    """Build the multiplex parent app, auto-mounting populated surfaces.

    Walks the active :class:`SurfaceRegistry` (preserving registration
    order) and mounts each surface with non-empty registrations at `/{surface.name}`
    via `surface.bind(runtime, ...)`. The App is built into a single
    `AppRuntime` once; the parent's lifespan enters that runtime
    exactly once and forwards every mounted surface's lifespan.

    ``enter_runtime`` (default ``True``): the parent owns the single
    ``async with runtime:``. Set ``False`` when the **caller** owns the
    runtime lifecycle — e.g. the spoke serve path that runs the public
    parent and the UDS listener under one shared ``async with runtime:``
    so the two listeners share one DI root container (one ``SINGLETON``
    store handle). When ``False`` the parent's lifespan forwards only the
    mounted surfaces' lifespans.

    ``mcp_options``: build kwargs threaded into the MCP surface's
    ``build_mcp_server`` (``compact`` / ``tool_selection`` / ``code_mode``
    / ``code_mode_allow_destructive``). The CLI `serve` knobs reach the
    multiplex this way instead of silently defaulting. ``None`` keeps the
    surface's default build (identical to ``McpSurface.bind``).

    Raises `ValueError` if no registered surface has registrations.
    """
    from a2kit.runtime import build

    # One runtime for the whole process — every surface shares it and
    # (by default) the parent owns its single lifecycle. ``build`` is
    # idempotent on an ``AppRuntime``, so downstream `surface.bind` reuses
    # it. The runtime carries the per-runtime surface registry composed at
    # build time (default: McpSurface + ApiSurface).
    runtime = build(app)

    mounts: list[tuple[str, Starlette]] = []
    for surface in runtime.surfaces:
        if not _surface_has_registrations(runtime, surface.name):
            continue
        # MCP's `bind` returns a FastMCP instance; its ASGI app is
        # `.http_app(path="/")`. Other surfaces return a Starlette-shaped
        # ASGI app directly. When `mcp_options` is supplied we build the
        # MCP server directly to thread the serve knobs (the default-path
        # `surface.bind` builds with defaults); both pass
        # `own_app_lifecycle=False` so the parent owns the single lifecycle.
        if surface.name == "mcp":
            if mcp_options:
                from a2kit.packages.mcp import build_mcp_server

                mcp_server = build_mcp_server(runtime, own_app_lifecycle=False, **mcp_options)
            else:
                mcp_server = surface.bind(runtime)
            sub_app = mcp_server.http_app(path="/")
        else:
            sub_app = surface.bind(runtime)
        mounts.append((f"/{surface.name}", sub_app))

    if not mounts:
        msg = (
            "build_parent_app: no registered surface has registrations to "
            "expose. Register at least one projection tool "
            "(@app.read/list/write), an @app.api.<method>(...) route, or "
            "an @app.mcp.<feature>(...) registration."
        )
        raise ValueError(msg)

    @asynccontextmanager
    async def _parent_lifespan(parent: Starlette) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            # The runtime enters first, exits last — surfaces stop serving
            # before the shared DI container drains. When the caller owns
            # the runtime (`enter_runtime=False`) the parent forwards only
            # the surface lifespans.
            if enter_runtime:
                await stack.enter_async_context(runtime)
            for _path, sub_app in mounts:
                await stack.enter_async_context(sub_app.router.lifespan_context(parent))
            yield

    return Starlette(
        routes=[Mount(path, app=sub_app) for path, sub_app in mounts],
        lifespan=_parent_lifespan,
    )


def serve_process(
    runtime: AppRuntime,
    *,
    transport: str,
    host: str,
    port: int,
    internal_uds: str | None,
    mcp_options: Mapping[str, Any] | None,
) -> None:
    """Run the a2kit server process for ``runtime`` (blocking).

    The single serve entry point for the CLI. Composes the public
    listener from ``transport`` (``stdio`` → MCP over the pipe; ``http``
    → the ``build_parent_app`` multiplex of every populated surface) and,
    when ``internal_uds`` is set, a **co-resident** spoke listener over a
    ``0600`` Unix domain socket — both sharing the **one** ``runtime`` (one
    DI root container, one ``SINGLETON`` store handle).

    ``mcp_options`` threads the serve knobs (``compact`` / ``tool_selection``
    / ``code_mode`` / ``code_mode_allow_destructive``) into the MCP build on
    both the multiplex and stdio paths.
    """
    import uvicorn

    if internal_uds is None:
        # Single-listener paths (no spoke) — unchanged topology.
        if transport == "stdio":
            from a2kit.packages.mcp import build_mcp_server

            build_mcp_server(runtime, **(mcp_options or {})).run(transport="stdio")
        else:
            parent = build_parent_app(runtime, mcp_options=mcp_options)
            uvicorn.run(parent, host=host, port=port)
        return

    # Spoke present → run the public listener and the UDS spoke in parallel
    # under one shared runtime lifecycle.
    import asyncio

    asyncio.run(
        _serve_with_spoke(
            runtime,
            transport=transport,
            host=host,
            port=port,
            uds_path=internal_uds,
            mcp_options=mcp_options,
        )
    )


async def _serve_with_spoke(
    runtime: AppRuntime,
    *,
    transport: str,
    host: str,
    port: int,
    uds_path: str,
    mcp_options: Mapping[str, Any] | None,
) -> None:
    """Serve the public listener + the UDS spoke under one ``async with runtime:``.

    The runtime is entered **once** here (so both listeners share its DI
    root container / ``SINGLETON`` store); the public parent is built with
    ``enter_runtime=False`` so it does not re-enter it. Both run under one
    ``asyncio.gather`` — the spoke over a ``0600`` AF_UNIX socket, the
    public side over TCP (http) or the stdio pipe.
    """
    import asyncio

    import uvicorn

    from a2kit.packages.http import build_http_app

    spoke_app = build_http_app(runtime, auth_target="internal")
    sock = _make_uds_socket(uds_path)
    spoke_server = uvicorn.Server(uvicorn.Config(spoke_app, log_level="info"))

    async with runtime:
        coros = [spoke_server.serve(sockets=[sock])]
        if transport == "stdio":
            from a2kit.packages.mcp import build_mcp_server

            mcp_server = build_mcp_server(runtime, own_app_lifecycle=False, **(mcp_options or {}))
            coros.append(mcp_server.run_stdio_async())
        else:
            parent = build_parent_app(runtime, enter_runtime=False, mcp_options=mcp_options)
            public_server = uvicorn.Server(uvicorn.Config(parent, host=host, port=port, log_level="info"))
            coros.append(public_server.serve())
        try:
            await asyncio.gather(*coros)
        finally:
            _cleanup_uds(uds_path)


def _make_uds_socket(path: str) -> Any:
    """Create a listening AF_UNIX socket at ``path`` with ``0600`` permissions.

    The umask is narrowed across the ``bind`` so the socket node is created
    private (owner-only); ``chmod`` after is belt-and-suspenders against a
    permissive inherited umask. A stale socket file at ``path`` is removed
    first (a left-over node from an unclean prior exit).
    """
    import os
    import socket
    from pathlib import Path

    node = Path(path)
    if node.exists():
        node.unlink()
    prev = os.umask(0o177)
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(path)
    finally:
        os.umask(prev)
    node.chmod(0o600)
    sock.listen()
    return sock


def _cleanup_uds(path: str) -> None:
    """Remove the spoke socket node on shutdown (best-effort)."""
    from pathlib import Path

    node = Path(path)
    if node.exists():
        node.unlink()


__all__ = ["build_parent_app", "serve_process"]
