"""``build_parent_app(app) -> Starlette`` — the multiplex parent.

Under ``serve --transport=http`` a2kit runs a single process on a single
port. This module builds the a2kit-owned parent ASGI application that
mounts each populated surface as an independent sub-app: the FastMCP
streamable-HTTP app under ``/mcp``, the FastAPI sub-app under ``/api``.

**Auto-mount** (post-add-multi-surface): each substrate's sub-app is
mounted only when the runtime carries registrations for it. Projection
tools (``@app.read``/``@app.list``/``@app.write``) default to both
substrates; ``@app.api.<method>`` is FastAPI-only; ``@app.mcp.<feature>``
is FastMCP-only. If neither substrate has registrations, the function
raises ``ValueError`` — a server with nothing to serve is a config bug.

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
    from collections.abc import AsyncIterator

    from a2kit.app import App
    from a2kit.runtime import AppRuntime


def _has_api_registrations(runtime: AppRuntime) -> bool:
    """True if any projection tool or author-written ``@app.api.*`` route exists.

    Projection tools default to exposing on both substrates; the per-tool
    ``expose`` filter (Phase 4 task 4.5) will narrow this. ``@app.api.*``
    routes always count.
    """
    if runtime.tools():
        return True
    api = runtime.api_surface
    return api is not None and bool(api.routes)


def _has_mcp_registrations(runtime: AppRuntime) -> bool:
    """True if any projection tool or author-written ``@app.mcp.*`` exists."""
    if runtime.tools():
        return True
    mcp = runtime.mcp_surface
    return mcp is not None and bool(mcp.registrations)


def build_parent_app(app: App | AppRuntime) -> Starlette:
    """Build the multiplex parent app, auto-mounting populated surfaces.

    The substrate sub-apps mount based on the runtime's registrations:

    - ``/mcp`` mounts when ``_has_mcp_registrations(runtime)`` is true
      (any projection tool — defaults to both surfaces — or any
      ``@app.mcp.<feature>``).
    - ``/api`` mounts when ``_has_api_registrations(runtime)`` is true
      (any projection tool or any ``@app.api.<method>``).

    The App is built into a single ``AppRuntime`` once; the parent's
    lifespan enters that runtime exactly once and forwards every mounted
    surface's lifespan.

    Raises ``ValueError`` if neither substrate has registrations.
    """
    from a2kit.runtime import build

    # One runtime for the whole process — both surfaces share it and the
    # parent owns its single lifecycle. ``build`` is idempotent on an
    # ``AppRuntime``, so the downstream ``build_mcp_server`` reuses it.
    runtime = build(app)

    mcp_mount = _has_mcp_registrations(runtime)
    api_mount = _has_api_registrations(runtime)
    if not (mcp_mount or api_mount):
        msg = (
            "build_parent_app: no surfaces have registrations to expose. "
            "Register at least one projection tool (@app.read/list/write), "
            "an @app.api.<method>(...) route, or an @app.mcp.<feature>(...) "
            "registration."
        )
        raise ValueError(msg)

    # (mount-path, sub-app) pairs — the single source for both the route
    # table and the lifespans the parent must forward.
    mounts: list[tuple[str, Starlette]] = []

    if mcp_mount:
        from a2kit.packages.mcp import build_mcp_server

        # own_app_lifecycle=False: the mount carries only transport-scoped
        # setup; this parent owns the single `async with runtime:`.
        mcp_server = build_mcp_server(runtime, own_app_lifecycle=False)
        mounts.append(("/mcp", mcp_server.http_app(path="/")))

    if api_mount:
        from a2kit.packages.http import build_http_app

        mounts.append(("/api", build_http_app(runtime)))

    @asynccontextmanager
    async def _parent_lifespan(parent: Starlette) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            # The runtime enters first, exits last — surfaces stop serving
            # before the shared DI container drains.
            await stack.enter_async_context(runtime)
            for _path, sub_app in mounts:
                await stack.enter_async_context(sub_app.router.lifespan_context(parent))
            yield

    return Starlette(
        routes=[Mount(path, app=sub_app) for path, sub_app in mounts],
        lifespan=_parent_lifespan,
    )


__all__ = ["build_parent_app"]
