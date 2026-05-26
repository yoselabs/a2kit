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

import functools as _functools
import inspect
from typing import TYPE_CHECKING, Annotated
from typing import Any as _Any

from a2effect import AppError
from a2effect.defect import quarantine
from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse

from a2kit.packages.dispatch import (
    SURFACE_REGISTRY,
    _run_authorize_gate,
    install_substrate_signature,
    split_signature,
)

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
    _install_request_scope_middleware(app, container)
    _wire_container_depends_overrides(app, runtime, container)
    _install_typed_error_handlers(app)
    _install_auth_middlewares(app, runtime)

    # Default liveness — matches the existing rest.py stub's contract.
    # Liveness only; the `_meta.health` MCP tool covers degraded-state
    # readiness aggregation.
    @app.get("/health")
    async def _health() -> dict[str, str]:
        return {"status": "ok"}

    # Projection tools as POST /api/<name>. Filter by `"api" in expose`
    # so tools explicitly opted out (e.g. `@app.read(expose=("mcp",))`)
    # do not surface on the FastAPI sub-app.
    for desc in runtime.tools():
        if "api" not in desc.expose:
            continue
        wrapped = install_substrate_signature(desc.fn, SURFACE_REGISTRY.get("api"), container)
        wrapped = _apply_authorize_gate(wrapped, desc.authorize, container)
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
            wrapped = install_substrate_signature(route.fn, SURFACE_REGISTRY.get("api"), container)
            wrapped = _apply_authorize_gate(wrapped, route.authorize, container)
            app.add_api_route(
                path=route.path,
                endpoint=wrapped,
                methods=[route.method],
                **route.fastapi_kwargs,
            )
        api_surface.fastapi_app = app

    return app


def _install_auth_middlewares(app: FastAPI, runtime: AppRuntime) -> None:
    """Mount authentication middlewares from ``runtime.auth_registry``.

    No-op when the registry is empty / ``None``: an App with no
    ``App.auth(...)`` calls SHALL produce a middleware-free sub-app
    (per ``http-surface`` capability). Middlewares mount in
    registration order; the first to publish via the dispatch
    principal bridge short-circuits subsequent authenticators.

    Only ``APIKeyAuth`` is wired today; ``JwtAuth`` is queued as a
    follow-up in the ``add-auth`` change (heavy dep footprint:
    JWKS fetcher + ``python-jose``).
    """
    registry = getattr(runtime, "auth_registry", None)
    if registry is None or len(registry) == 0:
        return
    # Lazy import: the auth package is L5 like ``http``; not pulled
    # unless the registry has content (the registry's existence is the
    # signal). Same-layer import, no `A2K-LAYER` concern.
    from a2kit.packages.auth import APIKeyAuth, build_api_key_middleware

    for spec in registry.for_target("api"):
        if isinstance(spec, APIKeyAuth):
            app.add_middleware(_BareAsgiMiddleware, factory=build_api_key_middleware(spec))


class _BareAsgiMiddleware:
    """Adapter wrapping a bare ASGI3 middleware as a Starlette ``Middleware``.

    Starlette's ``add_middleware(cls, **kw)`` expects ``cls(app, **kw)``
    to return an ASGI3 callable. Our API-key middleware factory already
    has the form ``factory(app) -> ASGI3`` — this adapter just calls it.
    """

    def __init__(self, app: _Any, *, factory: _Any) -> None:
        self._app = factory(app)

    async def __call__(self, scope: dict[str, _Any], receive: _Any, send: _Any) -> None:
        await self._app(scope, receive, send)


#: HTTP status code map from AppError kind. Per-class `http_status`
#: ClassVar overrides this. From `error-envelope-rendering`.
_KIND_HTTP_STATUS: dict[str, int] = {
    "input": 400,
    "auth": 401,
    "policy": 403,
    "infra": 503,
    "bug": 500,
}


def _http_status_for(exc: AppError) -> int:
    override = type(exc).http_status
    if override is not None:
        return override
    return _KIND_HTTP_STATUS.get(exc.base_kind, 500)


def _install_typed_error_handlers(app: FastAPI) -> None:
    """Install AppError + catch-all handlers emitting the typed envelope.

    - AppError → status from kind map (with per-class override) +
      ``{"error": <envelope dict>}`` body.
    - Anything else → `quarantine` to `UnexpectedDefect`, then same shape.

    Replaces the prior `_install_authorization_denied_handler`:
    `AuthorizationDenied` is itself an AppError now and flows through
    this handler with no special-casing.
    """

    @app.exception_handler(AppError)
    async def _typed_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=_http_status_for(exc),
            content={"error": exc.to_envelope_dict()},
        )

    @app.exception_handler(Exception)
    async def _quarantine(_request: Request, exc: Exception) -> JSONResponse:
        wrapped = quarantine(exc)
        return JSONResponse(
            status_code=_http_status_for(wrapped),
            content={"error": wrapped.to_envelope_dict()},
        )


def _apply_authorize_gate(wrapped: _Any, authorize: _Any, container: _Any) -> _Any:
    """Wrap `wrapped` so its `authorize=` callable runs before the body.

    No-op when `authorize` is None. A FastAPI ``Security`` guard's
    returned ``Principal`` lands in route kwargs; this wrapper scans for
    it, publishes via the dispatch bridge, then delegates to
    ``_run_authorize_gate``. Preserves ``__signature__`` /
    ``__annotations__`` so FastAPI's introspection still sees the
    substrate-installed surface params.
    """
    if authorize is None:
        return wrapped

    from a2kit.packages.context import Principal as _Principal
    from a2kit.packages.dispatch import (
        reset_request_principal,
        set_request_principal,
    )

    @_functools.wraps(wrapped)
    async def _gated(**kwargs: _Any) -> _Any:
        principal = next((v for v in kwargs.values() if isinstance(v, _Principal)), None)
        token = set_request_principal(principal) if principal is not None else None
        try:
            await _run_authorize_gate(authorize, container)
            return await wrapped(**kwargs)
        finally:
            if token is not None:
                reset_request_principal(token)

    sig = getattr(wrapped, "__signature__", None)
    if sig is not None:
        setattr(_gated, "__signature__", sig)  # noqa: B010 -- ty: setattr keeps both type-checkers quiet
    _gated.__annotations__ = dict(getattr(wrapped, "__annotations__", {}))
    return _gated


def _install_request_scope_middleware(app: FastAPI, container: _Any) -> None:
    """Open a per-request a2kit child container and publish it on the contextvar.

    The `Container.expose_as_fastapi_depends`-generated resolvers read this
    contextvar to find the active scope. Runs *before* FastAPI's dependency
    resolution because middlewares wrap the entire request lifecycle.
    """
    from a2kit.packages.di import _a2kit_request_scope

    @app.middleware("http")
    async def _open_request_scope(request: Request, call_next: _Any) -> _Any:
        child = container.child()
        async with child as scope:
            token = _a2kit_request_scope.set(scope)
            try:
                return await call_next(request)
            finally:
                _a2kit_request_scope.reset(token)


def _wire_container_depends_overrides(app: FastAPI, runtime: _Any, container: _Any) -> None:
    """Register a `Depends` override for every container-known type a tool references.

    Walks every descriptor's wire and substrate-dep chains; for each
    parameter whose annotation is a container-known type, registers the
    resolver returned by `container.expose_as_fastapi_depends(T)` into
    `app.dependency_overrides[T]`. FastAPI then routes any `Depends(T)`
    binding through the a2kit bridge.
    """
    seen: set[type] = set()
    for desc in runtime.tools():
        if "api" not in desc.expose:
            continue
        split = split_signature(desc.fn, SURFACE_REGISTRY.get("api"), container)
        for param in (*split.container.values(), *split.substrate_dep.values()):
            ann = param.annotation
            target = _resolved_container_type(ann, container)
            if target is None or target in seen:
                continue
            seen.add(target)
            app.dependency_overrides[target] = container.expose_as_fastapi_depends(target)


def _resolved_container_type(ann: _Any, container: _Any) -> type | None:
    """Resolve `ann` to the underlying container-known concrete type, or None."""
    from a2kit.packages.dispatch import _unwrap_annotation

    candidate = _unwrap_annotation(ann)
    if isinstance(candidate, type) and container.has_provider(candidate):
        return candidate
    if container.has_provider(ann):
        # Provider registered against the raw (possibly Annotated) form.
        return ann if isinstance(ann, type) else None
    return None


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
    split = split_signature(fn, SURFACE_REGISTRY.get("api"), container)
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
