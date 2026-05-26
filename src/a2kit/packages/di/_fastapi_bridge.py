"""FastAPI bridge resolvers — extracted to keep `container.py` under the SLOC budget.

The HTTP middleware in `packages/http/build.py` opens a per-request a2kit
child container and publishes it on the `_a2kit_request_scope` contextvar
(DI-local, so the DI package stays standalone-shippable) AND on the
shared `request_scope` bridge (so dispatch stages can `get(Container)`).
`_make_resolver(T)` returns a zero-arg async callable that reads the
contextvar and awaits `scope.get(T)` — usable as a FastAPI `Depends(...)`
dependency. Cached on the container (see `Container.expose_as_fastapi_depends`)
so identical-type calls return the same callable object and FastAPI's
`Depends` key-based deduplication works.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.packages.di._request_scope import _a2kit_request_scope

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.packages.di.container import Container


def _make_resolver(type_: type) -> Callable[[], Any]:
    async def _resolve_a2kit_dep() -> Any:
        scope = _a2kit_request_scope.get()
        if scope is None:
            msg = (
                "a2kit Depends resolver called outside call_scope: "
                "FastAPI evaluated this dependency before a2kit's "
                "request-scope middleware ran."
            )
            raise RuntimeError(msg)
        return await scope.get(type_)

    return _resolve_a2kit_dep


def resolver_for(container: Container, type_: type) -> Callable[[], Any]:
    """Container-cached resolver factory; identity-stable per (container, type)."""
    cache: dict[type, Callable[[], Any]] = container.__dict__.setdefault("_fastapi_depends_cache", {})
    if type_ not in cache:
        cache[type_] = _make_resolver(type_)
    return cache[type_]


__all__ = ["_make_resolver", "resolver_for"]
