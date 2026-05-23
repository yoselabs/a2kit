"""``build_http_app(runtime) -> fastapi.FastAPI`` — the FastAPI sub-app builder.

Walks the runtime's tool descriptors and ``ApiSurface`` registrations,
installs each via ``install_substrate_signature(fn, "fastapi", container)``,
and registers them on a fresh FastAPI instance:

- **Projection tools** (``@app.read``/``@app.list``/``@app.write``) are
  exposed as ``POST /api/<tool_name>`` (RPC-shape, mirroring MCP's
  ``tools/call``; see ``http-surface`` spec for rationale).
- **Author-written ``@app.api.<method>(path)`` routes** are registered
  at their declared paths with their declared methods.

The result is mounted by ``packages.serve.build_parent_app`` under
``/api``. The default ``/api/health`` and ``/api/openapi.json`` routes
remain available; FastAPI's auto-generated Swagger UI is served at
``/api/docs``.

Cold-start: this module imports ``fastapi`` at module scope; it is
only loaded when the ``serve --transport=http`` path imports
``packages.http``. ``import a2kit`` does not reach here.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Annotated
from typing import Any as _Any

from fastapi import Body, FastAPI

from a2kit.packages.dispatch import install_substrate_signature, split_signature

if TYPE_CHECKING:
    from a2kit.packages.http.api import ApiSurface
    from a2kit.runtime import AppRuntime


def build_http_app(runtime: AppRuntime, api_surface: ApiSurface | None = None) -> FastAPI:
    """Build the FastAPI sub-app for ``runtime``.

    ``api_surface``: when omitted, defaults to ``runtime.api_surface``
    (populated by ``build()`` from the source ``App``'s ``api`` property).
    Explicit passing is still supported for tests and ad-hoc tooling.

    Each tool descriptor's ``fn`` is wrapped by
    ``install_substrate_signature`` so the FastAPI introspector sees
    only wire + reserved params and a2kit DI is resolved per call.
    """
    if api_surface is None:
        api_surface = runtime.api_surface
    container = runtime.container()
    app = FastAPI(
        title=runtime.name,
        version=_runtime_version(runtime),
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # Default liveness — matches the existing rest.py stub's contract.
    # Liveness only; the `_meta.health` MCP tool covers degraded-state
    # readiness aggregation.
    @app.get("/health")
    async def _health() -> dict[str, str]:
        return {"status": "ok"}

    # Projection tools as POST /api/<name>. Default expose semantics
    # (both surfaces) are honoured by including every descriptor; the
    # per-tool `expose` filter lands in Phase 4 when ToolDescriptor
    # carries the `expose` field.
    for desc in runtime.tools():
        wrapped = install_substrate_signature(desc.fn, "fastapi", container)
        _force_body_binding_for_wire_params(wrapped, desc.fn, container)
        app.add_api_route(
            path=f"/{desc.name}",
            endpoint=wrapped,
            methods=["POST"],
            name=desc.name,
        )

    # Author-written @app.api.<method>(path) routes.
    if api_surface is not None:
        for route in api_surface.routes:
            wrapped = install_substrate_signature(route.fn, "fastapi", container)
            app.add_api_route(
                path=route.path,
                endpoint=wrapped,
                methods=[route.method],
                **route.fastapi_kwargs,
            )
        api_surface.fastapi_app = app

    return app


def _force_body_binding_for_wire_params(wrapper: _Any, fn: _Any, container: _Any) -> None:
    """Mark every wire parameter on ``wrapper.__signature__`` as ``Body``-bound.

    Projection tools take their wire params from the JSON request body
    (RPC shape, mirroring MCP's ``tools/call``). FastAPI defaults simple
    types (``str``/``int``/``bool``) to query params; without an override
    a tool ``async def fetch(*, id: str)`` would serve ``POST /api/fetch?id=x``
    instead of accepting ``{"id": "x"}`` in the body.

    Rewrites the wrapper's surface ``__signature__``: each wire param's
    annotation becomes ``Annotated[T, Body(embed=True)]``. Reserved
    params (``Request``/``Response``/etc.) are left untouched —
    substrates own their routing decisions for those.
    """
    split = split_signature(fn, "fastapi", container)
    sig = wrapper.__signature__
    new_params: list[inspect.Parameter] = []
    for param in sig.parameters.values():
        if param.name in split.wire:
            ann = wrapper.__annotations__.get(param.name, param.annotation)
            new_ann = Annotated[ann, Body(embed=True)]
            new_params.append(param.replace(annotation=new_ann))
        else:
            new_params.append(param)
    wrapper.__signature__ = inspect.Signature(parameters=new_params, return_annotation=sig.return_annotation)


def _runtime_version(runtime: AppRuntime) -> str:
    """Pull the runtime's app version, mirroring the rest.py stub's lookup."""
    from a2kit.packages.health import app_version

    return app_version(runtime)


__all__ = ["build_http_app"]
