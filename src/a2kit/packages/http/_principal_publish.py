"""Per-tool-wrap helper: scrape `Principal` from FastAPI-Security kwargs and publish to `request_scope`.

The substrate-side companion to `packages/auth/api_key.py`'s already-existing
wire-layer publish. FastAPI `Security(...)` guards (e.g.
``Annotated[Principal, Security(my_guard)]``) produce the Principal AFTER
all Starlette middlewares have run, so a wire-layer middleware can't see
it. The per-tool wrapper calls this helper before folding the pipeline.

Idempotent vis-a-vis the API-key middleware: if API-key auth already
published a Principal, the kwarg-scrape returns the same instance and the
duplicate publish is a no-op (the dispatch principal bridge uses contextvar
publish/reset semantics; a nested publish of the same value reseats it
identically).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.packages.context import Principal, request_scope

if TYPE_CHECKING:
    import contextvars


def publish_principal_from_kwargs(kwargs: dict[str, Any]) -> contextvars.Token[Any] | None:
    """Scan ``kwargs`` for a ``Principal`` instance and publish it; return the reset token.

    Returns ``None`` when no ``Principal`` is found, in which case the caller
    SHALL NOT call ``request_scope.reset``. The token MUST be reset in a
    ``finally`` block on the calling per-tool wrapper.
    """
    principal = next((v for v in kwargs.values() if isinstance(v, Principal)), None)
    if principal is None:
        return None
    return request_scope.publish(principal)


__all__ = ["publish_principal_from_kwargs"]
