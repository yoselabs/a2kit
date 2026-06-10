"""``ApiSurface`` — the ``@app.api.<method>(...)`` decorator accumulator.

Bound to an ``App`` via the ``App.api`` lazy property (Phase 4 wiring).
Each decorator method (``get``/``post``/``put``/``delete``/``patch``/
``options``/``head``) returns a decorator that records an
``ApiRoute`` registration on the surface; at ``build_http_app`` time
the recorded routes are installed on the FastAPI sub-app, each wrapped
by ``install_substrate_signature`` for a2kit DI.

Satisfies the ``Surface`` Protocol from ``packages/dispatch/surface``:
the dispatch-layer signature splitter discovers FastAPI-reserved types
(``Request``/``Response``/``BackgroundTasks``/``WebSocket``) and
substrate-dep markers (``Depends``/``Security``) via the Surface's
ClassVars rather than a hardcoded substrate-string discriminator.
Lookups stay lazy — see ``reserved_types``/``substrate_dep_markers``
properties.

The ``fastapi_app`` lazy property exposes the underlying FastAPI app
once it has been built, so authors can call ``add_middleware``,
``include_router``, etc. — escape hatch, not a normal authoring path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from a2kit.packages.dispatch import DecoratorSurface, SurfaceKind, fastapi_dep_markers, fastapi_reserved

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI


HttpMethod = Literal["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]


@dataclass(frozen=True)
class ApiRoute:
    """One ``@app.api.<method>(path, **kwargs)`` registration.

    ``fastapi_kwargs`` is forwarded verbatim to
    ``FastAPI.add_api_route(..., **fastapi_kwargs)``: ``response_model``,
    ``status_code``, ``tags``, ``dependencies``, ``summary``, etc. all
    pass through unchanged. ``authorize`` is stamped here for the
    dispatch-time auth gate landing in ``add-auth``.
    """

    method: HttpMethod
    path: str
    fn: Callable[..., Any]
    fastapi_kwargs: dict[str, Any]  # noqa: AK214 -- forwarded verbatim to FastAPI.add_api_route; shape owned by upstream
    authorize: Callable[..., Any] | None = None


class ApiSurface(DecoratorSurface[ApiRoute]):
    """The ``@app.api.<method>`` decorator family bound to one ``App``.

    Decorator methods are *closures* over the surface: each one returns
    a decorator that appends to ``routes``. Authors stack the decorators
    they would on a FastAPI ``APIRouter``; at build time we register
    them on the FastAPI sub-app under ``/api``.

    ``fastapi_app`` starts unset and is populated by ``build_http_app``
    once the FastAPI instance exists. Authors who need to attach
    middleware before serve time can call ``app.api.fastapi_app`` after
    finalization (rare; documented escape hatch).
    """

    name: ClassVar[str] = "api"
    kind: ClassVar[SurfaceKind] = SurfaceKind.NETWORK

    fastapi_app: FastAPI | None

    def __init__(self) -> None:
        super().__init__()
        self.fastapi_app = None

    @property
    def reserved_types(self) -> frozenset[type]:  # type: ignore[override]
        return fastapi_reserved()

    @property
    def substrate_dep_markers(self) -> frozenset[type]:  # type: ignore[override]
        return fastapi_dep_markers()

    @property
    def routes(self) -> tuple[ApiRoute, ...]:
        """Backwards-compatible alias for the inherited ``registrations`` view.

        Existing callers (e.g. ``build_http_app``) read ``api_surface.routes``
        as the canonical name on the HTTP side. The accumulator itself
        lives in ``DecoratorSurface[R]._registrations``.
        """
        return self.registrations

    # --- decorator methods --------------------------------------------- #

    def _decorator(self, method: HttpMethod, path: str, **fastapi_kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Build a single ``(path, **kwargs)`` decorator for ``method``.

        Pops ``authorize`` from ``fastapi_kwargs`` so it does not leak
        into FastAPI's route-construction kwargs. ``surfaces`` is rejected
        here — the projection family owns multi-surface placement; on
        ``@app.api.*`` it is always FastAPI-only.
        """
        if "surfaces" in fastapi_kwargs:
            msg = (
                f"@app.api.{method.lower()}({path!r}, surfaces=...): surfaces= is "
                f"only valid on projection decorators (@app.read/list/write). "
                f"@app.api.* is single-surface by construction."
            )
            raise TypeError(msg)
        authorize = fastapi_kwargs.pop("authorize", None)

        def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._record(
                ApiRoute(
                    method=method,
                    path=path,
                    fn=fn,
                    fastapi_kwargs=fastapi_kwargs,
                    authorize=authorize,
                )
            )
            return fn

        return _wrap

    def get(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._decorator("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._decorator("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._decorator("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._decorator("DELETE", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._decorator("PATCH", path, **kwargs)

    def options(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._decorator("OPTIONS", path, **kwargs)

    def head(self, path: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._decorator("HEAD", path, **kwargs)

    # --- `Surface` Protocol fulfilment ---------------------------------- #

    def bind(self, runtime: Any, descriptors: Any = None) -> Any:  # noqa: ARG002
        """Build the FastAPI sub-app for ``runtime``.

        Delegates to :func:`a2kit.packages.http.build.build_http_app`.
        Reads ``runtime.api_surface`` for author-written routes: each
        App carries its own ``ApiSurface`` instance (the accumulator)
        which is what holds the registrations. The Surface registered
        in the active ``SurfaceRegistry`` (``self``) is a class-level identity
        used by the dispatch-layer signature splitter; it is NOT the
        per-App accumulator. ``descriptors`` is accepted for Protocol
        uniformity; the underlying builder walks ``runtime.tools()``
        itself.
        """
        from a2kit.packages.http.build import build_http_app

        return build_http_app(runtime)

    def install_di_bridge(self, runtime: Any, substrate_app: Any) -> None:  # noqa: ARG002
        """No-op hook: FastAPI DI bridge is installed inside ``build_http_app``.

        ``_wire_container_depends_overrides`` mounts the bridge so the
        wiring happens uniformly for both Surface-driven and direct
        ``build_http_app`` callers. Kept as a method to satisfy the
        Protocol contract and to give future bridges a hook.
        """
        return


def _api_surface_factory(_context: object) -> ApiSurface:
    """Manifest factory for the built-in API surface. Always available."""
    return ApiSurface()


from a2kit.packages._plugin import PluginManifest  # noqa: E402 -- below class def

MANIFEST = PluginManifest(name="api", protocol=ApiSurface, factory=_api_surface_factory)


__all__ = ["MANIFEST", "ApiRoute", "ApiSurface", "HttpMethod"]
