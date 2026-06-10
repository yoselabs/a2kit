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

from a2effect import AppError
from a2effect.defect import quarantine
from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse

from a2kit.packages.dispatch import (
    ToolBuildSpec,
    fold_pipeline,
    install_substrate_signature,
    split_signature,
)
from a2kit.packages.http._error_render_stage import HttpErrorRenderStage

if TYPE_CHECKING:
    from a2kit.packages.http.api import ApiSurface
    from a2kit.runtime import AppRuntime


def _http_mountable(desc: _Any) -> bool:
    """Whether a tool descriptor may be mounted on the HTTP surface.

    HTTP is a network surface: a tool mounts only when it is advertised
    (LISTED) on the ``"api"`` surface per the projection matrix (ADR 0028
    Wave 2). ABSENT and UNLISTED verbs are not exposed on ``/api`` — no
    route, no DI override — mirroring the MCP surface, so the two network
    surfaces apply one rule. (An UNLISTED-on-api verb is callable in
    principle but the FastAPI projection does not yet implement a
    hidden-route mode, so it is treated as not mounted here.)
    """
    from a2kit._surfaces import advertised_on, matrix_for

    meta = desc._meta  # noqa: SLF001 -- mirrors mcp/server.py matrix read
    if meta is None:
        return "api" in desc.expose
    return advertised_on(matrix_for(meta.extras), "api")


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
    # so tools explicitly opted out (e.g. `@app.read(surfaces=("mcp",))`)
    # do not surface on the FastAPI sub-app.
    api_surface_obj = runtime.surfaces.get("api")
    for desc in runtime.tools():
        if not _http_mountable(desc):
            continue
        wrapped = _wrap_with_pipeline(
            fn=desc.fn,
            meta=desc._meta,  # noqa: SLF001 -- mirrors mcp/server.py:_build_one_tool
            authorize=desc.authorize,
            runtime=runtime,
            container=container,
            surface=api_surface_obj,
        )
        _force_body_binding_for_wire_params(wrapped, desc.fn, container, api_surface_obj)
        # Flat path = the canonical name (`/api/{slug}_{leaf}`); the router
        # slug rides in `tags` to cluster paths in OpenAPI/Swagger (ADR 0028
        # §4), keeping the wire identifier identical across surfaces.
        slug = getattr(desc.router, "slug", None)
        app.add_api_route(
            path=f"/{desc.name}",
            endpoint=wrapped,
            methods=["POST"],
            name=desc.name,
            tags=[slug] if slug else None,
        )

    # Author-written @app.api.<method>(path) routes.
    if api_surface is not None:
        for route in api_surface.routes:
            wrapped = _wrap_with_pipeline(
                fn=route.fn,
                meta=_synthetic_meta_for_api_route(route.fn, route.authorize),
                authorize=route.authorize,
                runtime=runtime,
                container=container,
                surface=api_surface_obj,
            )
            app.add_api_route(
                path=route.path,
                endpoint=wrapped,
                methods=[route.method],
                **route.fastapi_kwargs,
            )
        api_surface.fastapi_app = app

    return app


def _synthetic_meta_for_api_route(fn: _Any, authorize: _Any) -> _Any:
    """Build a minimal ``A2KitMeta`` for an ``@app.api.<method>`` route.

    Projection tools carry their authorize on ``desc.meta.extras.authorize``
    — ``AuthorizeGateStage`` reads it from there. Author-written
    ``@app.api.*`` routes capture authorize on ``route.authorize`` instead,
    so the pipeline can't find it. This helper synthesises an
    ``A2KitMeta`` whose ``extras.authorize`` matches the route's, so the
    same gate code path covers both kinds of registration. Other meta
    fields (``tool_name``, ``tags``, etc.) are filled with safe defaults
    — the stages that read them either self-skip or don't apply on the
    HTTP route path.
    """
    from a2kit.metadata import A2KitMeta, A2KitMetaExtras

    return A2KitMeta(
        tool_name=getattr(fn, "__name__", "<api_route>"),
        verb="read",  # type: ignore[arg-type] -- placeholder; verb is not consulted on @app.api.* paths
        tags=frozenset(),
        extras=A2KitMetaExtras(authorize=authorize),
    )


def _wrap_with_pipeline(
    *,
    fn: _Any,
    meta: _Any,
    authorize: _Any,
    runtime: _Any,
    container: _Any,
    surface: _Any,
) -> _Any:
    """Wrap ``fn`` for FastAPI route registration: pipeline + error render, inside substrate signature.

    Wrap order, innermost-first:

    1. ``HttpErrorRenderStage`` (innermost-of-the-pipeline-outer-block) —
       opens the ``_render_state`` side channel around the call; reads it
       on the way out to render ``CapturedError`` -> ``JSONResponse``.
    2. ``fold_pipeline(fn, spec)`` — transport-neutral stages:
       ``TimeoutStage``, ``EnricherStage``, ``ErrorEnvelopeStage`` (writes
       to ``_render_state``), ``RouterLazyEnterStage``,
       ``DispatchHookStage``, ``AuthorizeGateStage``, ``CallScopeStage``,
       ``ErrorCaptureStage``. ``AuthorizeGateStage`` reads ``Principal``
       from ``request_scope`` — which is published by ``install_substrate_signature``
       (step 3) BEFORE this chain runs.
    3. ``install_substrate_signature(chained, surface, container)`` outermost
       — substrate-facing wrapper. FastAPI introspects its
       ``__signature__`` (wire + reserved params only). The wrapper:
       (a) splits substrate kwargs, (b) publishes ``Principal`` from the
       reserved bucket to ``request_scope``, (c) opens its own
       ``call_scope`` to resolve DI for wire kwargs, (d) calls ``chained``
       with merged kwargs.

    Ordering rationale: Principal publication (step 3b) MUST happen before
    ``AuthorizeGateStage`` (in step 2) reads from ``request_scope``. The
    only way to guarantee that without rewriting ``install_substrate_signature``
    is to nest the pipeline INSIDE the substrate wrapper (this order).
    ``DispatchHookStage`` in the pipeline ALSO opens a ``call_scope`` —
    nested under the substrate wrapper's. Both inherit ``framework_seeds``
    from ``request_scope.all_seeds()``; SCOPED instances are shared via
    the request-scope-published Container. The extra scope open is a
    known minor inefficiency, tracked separately (ADR-0020 / S5: "two
    parallel signature installers" deferred).

    Pre-refactor (2026-05-27, S13) this function did NOT fold the pipeline
    — `AuthorizeGateStage`'s logic ran from a hand-rolled
    `_apply_authorize_gate` per route. Now the gate, error envelope, and
    every other dispatch concern flow through the same single pipeline.
    """
    spec = ToolBuildSpec(
        app=runtime,
        router=None,
        meta=meta,
        surface=getattr(surface, "name", "api"),
    )
    chained = fold_pipeline(fn, spec=spec)
    chained = HttpErrorRenderStage().wrap(chained, spec)
    # `install_substrate_signature` inspects chained's signature; chained
    # carries `fn`'s signature via `functools.wraps`, so the split is
    # identical to `install_substrate_signature(fn, ...)` would have been.
    return install_substrate_signature(chained, surface, container)


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


def _install_typed_error_handlers(app: FastAPI) -> None:
    """Install fallback exception handlers for AppErrors that bypass the pipeline.

    The primary path is now ``HttpErrorRenderStage`` (per ``dispatch-pipeline-parity-on-http``):
    every projection-tool and ``@app.api.*`` route folds the pipeline,
    and ``HttpErrorRenderStage`` reads ``RenderedError`` from the
    ``_render_state`` side channel populated by ``ErrorEnvelopeStage``,
    returning a ``JSONResponse`` directly.

    These handlers cover three remaining paths:

    1. ``AppError`` raised by code OUTSIDE a folded per-tool wrap (e.g.
       in custom middleware, or in an ``@app.api.*`` route's body before
       FastAPI hands off to the wrapper). The pipeline never ran, so
       ``_render_state`` is empty. Defensive — re-derives the envelope
       via ``exc.to_envelope_dict()`` and computes status via the
       canonical ``http_status_for`` helper.
    2. ``HttpErrorRenderStage``'s own defensive-fallback re-raise (when
       ``get_rendered_error`` returns ``None`` despite the wrap — should
       never fire in production).
    3. Non-``AppError`` exceptions: quarantined to ``UnexpectedDefect``
       and rendered via the same handler path.

    The ``kind -> status`` mapping itself lives once in
    ``packages.http._error_render_stage.http_status_for`` — the
    substrate-side canonical helper. This module imports it; there is
    no duplicate map here.
    """
    from a2kit.packages.http._error_render_stage import http_status_for

    @app.exception_handler(AppError)
    async def _typed_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=http_status_for(exc),
            content={"error": exc.to_envelope_dict()},
        )

    @app.exception_handler(Exception)
    async def _quarantine(_request: Request, exc: Exception) -> JSONResponse:
        wrapped = quarantine(exc)
        return JSONResponse(
            status_code=http_status_for(wrapped),
            content={"error": wrapped.to_envelope_dict()},
        )


def _install_request_scope_middleware(app: FastAPI, container: _Any) -> None:
    """Open a per-request a2kit child container and publish it on the contextvar.

    The `Container.expose_as_fastapi_depends`-generated resolvers read this
    contextvar to find the active scope. Runs *before* FastAPI's dependency
    resolution because middlewares wrap the entire request lifecycle.
    """
    # Dual write: publish on the shared request_scope (dispatch reads
    # Container via request_scope.get(Container)) AND set the DI-local
    # contextvar (FastAPI Depends bridge reads from there; keeps DI
    # package standalone-shippable per di-container-package).
    from a2kit.packages.context import request_scope
    from a2kit.packages.di import _a2kit_request_scope

    @app.middleware("http")
    async def _open_request_scope(request: Request, call_next: _Any) -> _Any:
        child = container.child()
        async with child as scope:
            rs_token = request_scope.publish(scope)
            di_token = _a2kit_request_scope.set(scope)
            try:
                return await call_next(request)
            finally:
                _a2kit_request_scope.reset(di_token)
                request_scope.reset(rs_token)


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
        if not _http_mountable(desc):
            continue
        split = split_signature(desc.fn, runtime.surfaces.get("api"), container)
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


def _force_body_binding_for_wire_params(wrapper: _Any, fn: _Any, container: _Any, api_surface_obj: _Any) -> None:
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
    split = split_signature(fn, api_surface_obj, container)
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
