"""``build_parent_app(app, *, mcp, rest) -> Starlette`` — the multiplex parent.

Under ``serve --transport=http`` a2kit runs a single process on a single
port. This module builds the a2kit-owned parent ASGI application that
mounts each enabled surface as an independent sub-app: the FastMCP
streamable-HTTP app under ``/mcp``, the REST app under ``/api``.

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


def build_parent_app(app: App, *, mcp: bool, rest: bool) -> Starlette:
    """Build the multiplex parent app mounting the enabled surfaces.

    ``mcp`` mounts ``build_mcp_server(runtime).http_app()`` under
    ``/mcp``; ``rest`` mounts ``build_rest_app(runtime)`` under ``/api``.
    At least one surface must be enabled. The App is built into a single
    ``AppRuntime`` once; the parent's lifespan enters that runtime
    exactly once and forwards every mounted surface's lifespan.
    """
    if not (mcp or rest):
        msg = "build_parent_app requires at least one surface enabled (mcp or rest)"
        raise ValueError(msg)

    from a2kit.runtime import build

    # One runtime for the whole process — both surfaces share it and the
    # parent owns its single lifecycle. ``build`` is idempotent on an
    # ``AppRuntime``, so the downstream ``build_mcp_server`` reuses it.
    runtime = build(app)

    # (mount-path, sub-app) pairs — the single source for both the route
    # table and the lifespans the parent must forward.
    mounts: list[tuple[str, Starlette]] = []

    if mcp:
        from a2kit.packages.mcp import build_mcp_server

        # own_app_lifecycle=False: the mount carries only transport-scoped
        # setup; this parent owns the single `async with runtime:`.
        mcp_server = build_mcp_server(runtime, own_app_lifecycle=False)
        mounts.append(("/mcp", mcp_server.http_app(path="/")))

    if rest:
        from a2kit.packages.rest import build_rest_app

        mounts.append(("/api", build_rest_app(runtime)))

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
