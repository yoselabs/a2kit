"""``ApiSurface`` — the ``@app.api.<method>(...)`` decorator accumulator.

Bound to an ``App`` via the ``App.api`` lazy property (Phase 4 wiring).
Each decorator method (``get``/``post``/``put``/``delete``/``patch``/
``options``/``head``) returns a decorator that records an
``ApiRoute`` registration on the surface; at ``build_http_app`` time
the recorded routes are installed on the FastAPI sub-app, each wrapped
by ``install_substrate_signature`` for a2kit DI.

The ``fastapi_app`` lazy property exposes the underlying FastAPI app
once it has been built, so authors can call ``add_middleware``,
``include_router``, etc. — escape hatch, not a normal authoring path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

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
    fastapi_kwargs: dict[str, Any]
    authorize: Callable[..., Any] | None = None


@dataclass
class ApiSurface:
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

    routes: list[ApiRoute] = field(default_factory=list)
    fastapi_app: FastAPI | None = None

    # --- decorator methods --------------------------------------------- #

    def _decorator(self, method: HttpMethod, path: str, **fastapi_kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Build a single ``(path, **kwargs)`` decorator for ``method``.

        Pops ``authorize`` from ``fastapi_kwargs`` so it does not leak
        into FastAPI's route-construction kwargs. ``expose`` is rejected
        here — the projection family owns multi-surface exposure; on
        ``@app.api.*`` it is always FastAPI-only.
        """
        if "expose" in fastapi_kwargs:
            msg = (
                f"@app.api.{method.lower()}({path!r}, expose=...): expose= is "
                f"only valid on projection decorators (@app.read/list/write). "
                f"@app.api.* is single-surface by construction."
            )
            raise TypeError(msg)
        authorize = fastapi_kwargs.pop("authorize", None)

        def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.routes.append(
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


__all__ = ["ApiRoute", "ApiSurface", "HttpMethod"]
