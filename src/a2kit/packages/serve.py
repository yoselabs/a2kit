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

from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.routing import Mount

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Coroutine, Mapping
    from typing import Any

    from a2kit.app import App
    from a2kit.runtime import AppRuntime


@dataclass(frozen=True)
class ServeContext:
    """The serve-only context handed to each on-serve service.

    ``internal_uds`` is the bound ``--internal-uds`` path (``None`` when no
    spoke); ``transport`` is ``"stdio"`` or ``"http"``. Minimal on purpose:
    a service reaches the live core over the loopback spoke
    (``internal_uds``), never the DI container, so it needs only the
    loopback address and the transport. See ADR 0030.
    """

    internal_uds: str | None
    transport: str


#: An on-serve service: a coroutine function the App registers via the
#: ``serve_services`` ClassVar. ``serve`` invokes it as ``service(ctx)``
#: inside the one ``async with runtime:`` and supervises the resulting task.
ServeService = Callable[[ServeContext], Awaitable[None]]


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

    The single serve entry point for the CLI, and the **one** serve engine:
    every path — stdio, http, with or without a spoke, with or without
    registered ``serve_services`` — runs through :func:`_serve` under one
    ``async with runtime:``. There are no separate bare single-listener
    paths (ADR 0030 collapsed them; the spoke path was already the general
    form).

    Composes the public listener from ``transport`` (``stdio`` → MCP over
    the pipe; ``http`` → the ``build_parent_app`` multiplex), optionally a
    **co-resident** spoke listener over a ``0600`` Unix domain socket when
    ``internal_uds`` is set, and every App-registered on-serve service —
    all sharing the **one** ``runtime`` (one DI root container, one
    ``SINGLETON`` store handle).

    ``mcp_options`` threads the serve knobs (``compact`` / ``tool_selection``
    / ``code_mode`` / ``code_mode_allow_destructive``) into the MCP build.
    """
    import asyncio

    asyncio.run(
        _serve(
            runtime,
            transport=transport,
            host=host,
            port=port,
            uds_path=internal_uds,
            services=tuple(runtime.serve_services),
            mcp_options=mcp_options,
        )
    )


async def _serve(
    runtime: AppRuntime,
    *,
    transport: str,
    host: str,
    port: int,
    uds_path: str | None,
    services: tuple[ServeService, ...],
    mcp_options: Mapping[str, Any] | None,
) -> None:
    """Serve the public listener (+ optional spoke) + services under one runtime.

    The runtime is entered **once** here (so every listener and service
    shares its DI root container / ``SINGLETON`` store); the public listener
    is built with ``enter_runtime=False`` / ``own_app_lifecycle=False`` so it
    does not re-enter it. Listeners and services are then supervised by
    :func:`_supervise` — a listener exiting ends serve, any task raising
    tears it down, a service finishing cleanly is a non-event. The spoke
    socket (when present) is cleaned up on teardown.
    """
    import uvicorn

    ctx = ServeContext(internal_uds=uds_path, transport=transport)

    async with runtime:
        listeners: list[Coroutine[Any, Any, Any]] = [
            _public_listener(runtime, transport=transport, host=host, port=port, mcp_options=mcp_options)
        ]
        on_teardown: Callable[[], None] | None = None
        if uds_path is not None:
            from a2kit.packages.http import build_http_app

            spoke_app = build_http_app(runtime, auth_target="internal")
            sock = _make_uds_socket(uds_path)
            spoke_server = uvicorn.Server(uvicorn.Config(spoke_app, log_level="info"))
            listeners.append(spoke_server.serve(sockets=[sock]))
            on_teardown = lambda: _cleanup_uds(uds_path)  # noqa: E731

        service_coros: list[Awaitable[Any]] = [svc(ctx) for svc in services]
        await _supervise(listeners, service_coros, on_teardown=on_teardown)


def _public_listener(
    runtime: AppRuntime,
    *,
    transport: str,
    host: str,
    port: int,
    mcp_options: Mapping[str, Any] | None,
) -> Coroutine[Any, Any, Any]:
    """Build the public-listener coroutine for ``transport``.

    Both forms run with the caller owning the one ``async with runtime:``
    (``own_app_lifecycle=False`` / ``enter_runtime=False``): stdio → FastMCP
    ``run_stdio_async()`` over the pipe; http → the ``build_parent_app``
    multiplex under a uvicorn ``Server.serve()``.
    """
    import uvicorn

    if transport == "stdio":
        from a2kit.packages.mcp import build_mcp_server

        mcp_server = build_mcp_server(runtime, own_app_lifecycle=False, **(mcp_options or {}))
        return mcp_server.run_stdio_async()

    parent = build_parent_app(runtime, enter_runtime=False, mcp_options=mcp_options)
    public_server = uvicorn.Server(uvicorn.Config(parent, host=host, port=port, log_level="info"))
    return public_server.serve()


async def _supervise(
    listeners: list[Coroutine[Any, Any, Any]],
    services: list[Awaitable[Any]],
    *,
    on_teardown: Callable[[], None] | None,
) -> None:
    """Supervise serve's listeners and services with asymmetric shutdown.

    Serve's lifetime is the **listener's** lifetime. The two kinds are
    treated asymmetrically (ADR 0030 D3):

    - a **listener** completing (cleanly on signal/EOF, or by raising) ends
      serve;
    - **any** task raising tears serve down and re-raises (nonzero exit);
    - a **service** finishing cleanly is a non-event — the listeners keep
      serving (e.g. a2kay's scheduler returns immediately when there is no
      spoke to drive).

    The primitive is ``asyncio.wait(FIRST_COMPLETED)`` in a loop that drops
    cleanly-finished services and keeps waiting — **not** ``asyncio.gather``
    (which would hang on a never-returning service after the listener exits)
    and **not** ``asyncio.TaskGroup`` (wait-for-all, same hang). On teardown
    every outstanding task is cancelled and drained, then ``on_teardown``
    runs (the spoke socket cleanup).
    """
    import asyncio

    listener_tasks = {asyncio.ensure_future(c) for c in listeners}
    pending = set(listener_tasks) | {asyncio.ensure_future(c) for c in services}
    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                exc = task.exception()
                if exc is not None:
                    raise exc
                if task in listener_tasks:
                    return
                # A service finished cleanly → non-event; keep serving.
    finally:
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if on_teardown is not None:
            on_teardown()


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


__all__ = ["ServeContext", "ServeService", "build_parent_app", "serve_process"]
