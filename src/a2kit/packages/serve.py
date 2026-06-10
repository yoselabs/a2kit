"""``build_parent_app(app) -> Starlette`` — the multiplex parent.

Under ``serve --transport=http`` a2kit runs a single process on a single
port. This module builds the a2kit-owned parent ASGI application that
mounts each populated surface as an independent sub-app via the
``Surface`` Protocol: each surface owns its own ``bind(runtime, ...)``
build path and is mounted at ``/{surface.name}``.

**Auto-mount** (post-add-multi-surface + remove-substrate-literal):
each registered :data:`SURFACE_REGISTRY` surface mounts only when the
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
    from collections.abc import AsyncIterator

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


def build_parent_app(app: App | AppRuntime) -> Starlette:
    """Build the multiplex parent app, auto-mounting populated surfaces.

    Walks :data:`SURFACE_REGISTRY` (preserving registration order) and
    mounts each surface with non-empty registrations at `/{surface.name}`
    via `surface.bind(runtime, ...)`. The App is built into a single
    `AppRuntime` once; the parent's lifespan enters that runtime
    exactly once and forwards every mounted surface's lifespan.

    Raises `ValueError` if no registered surface has registrations.
    """
    from a2kit.runtime import build

    # One runtime for the whole process — every surface shares it and
    # the parent owns its single lifecycle. ``build`` is idempotent on
    # an ``AppRuntime``, so downstream `surface.bind` reuses it. The
    # runtime carries the per-runtime surface registry composed at
    # build time (default: McpSurface + ApiSurface).
    runtime = build(app)

    mounts: list[tuple[str, Starlette]] = []
    for surface in runtime.surfaces:
        if not _surface_has_registrations(runtime, surface.name):
            continue
        sub_app = surface.bind(runtime)
        # MCP's `bind` returns a FastMCP instance; its ASGI app is
        # `.http_app(path="/")`. Other surfaces return a Starlette-shaped
        # ASGI app directly.
        if surface.name == "mcp":
            sub_app = sub_app.http_app(path="/")
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
