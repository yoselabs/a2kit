"""``build_rest_app(app) -> Starlette`` — the REST surface as an ASGI sub-app.

The multiplexed server (:mod:`a2kit.packages.serve`) mounts the returned
app under ``/api``. This module is imported only on the
``serve --transport=http`` path — never at ``import a2kit`` (cold-start
budget). Starlette is already transitive via fastmcp; no new dependency.

This is the surface's *minimal slice*: a health route and an OpenAPI
document with an empty ``paths`` object. Per-tool route projection
(verb -> HTTP method, ``Accept``-header content negotiation) is a later
requirement on the ``rest-surface`` capability, deferred to the
``add-rest-surface`` change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from starlette.requests import Request

    from a2kit.app import App


def build_rest_app(app: App) -> Starlette:
    """Build the minimal REST sub-application from an ``a2kit.App``.

    Serves ``/health`` (liveness) and ``/openapi.json`` (an OpenAPI 3.1
    document whose ``info`` is derived from ``app.name``). The author
    writes no route code to obtain this.
    """
    from a2kit.packages.health import app_version

    # Built once, not per request: `app.name` is set at construction and
    # `app.version` (if any) before serving — the document is fixed for the
    # process lifetime.
    openapi_doc = {
        "openapi": "3.1.0",
        "info": {"title": app.name, "version": app_version(app)},
        "paths": {},
    }

    async def health(_request: Request) -> JSONResponse:
        # Liveness only — 200 whenever the process is up. Readiness /
        # degraded-state aggregation (the `@app.health_check` registry,
        # surfaced as the `_meta.health` MCP tool) is `add-rest-surface` scope.
        return JSONResponse({"status": "ok"})

    async def openapi(_request: Request) -> JSONResponse:
        return JSONResponse(openapi_doc)

    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/openapi.json", openapi, methods=["GET"]),
        ]
    )


__all__ = ["build_rest_app"]
