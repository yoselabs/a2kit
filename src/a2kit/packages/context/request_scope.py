"""Single typed substrate-to-dispatch bridge for request-scoped values.

Replaces the former per-type ``ContextVar`` bridges (``_request_principal``,
``_a2kit_request_scope``, the log state) with one shared shape:
substrate writers call :func:`publish` at the request boundary;
dispatch stages and other readers call :func:`get` / :func:`try_get`.
A precise :class:`RequestScopeMissing` exception surfaces precondition
failures at the earliest read site instead of degrading to silent
``None``.

The N+1 cost of the next request-scoped value (TenantId, TraceContext,
RequestId) drops to zero: one ``publish`` at the writer, one ``get``
at the reader, no new ContextVar, no new bridge module.
"""

from __future__ import annotations

import contextvars
from typing import Any, TypeVar

T = TypeVar("T")

ScopeToken = contextvars.Token["dict[type, Any] | None"]


class RequestScopeMissing(LookupError):
    """Raised by :func:`get` when no value of the requested type is published.

    The ``requested_type`` attribute carries the type that was requested;
    the message points at substrate middleware ordering as the most
    common cause.
    """

    def __init__(self, t: type[Any]) -> None:
        super().__init__(
            f"RequestScope has no value of type {t.__name__!r}. "
            "Substrate middleware did not publish() it; check the "
            "middleware order at the transport boundary."
        )
        self.requested_type = t


# Module-private slot. Substrate writers (auth middleware, request-scope
# middleware, call-scope opener) :func:`publish`; dispatch stages and
# other readers :func:`get` or :func:`try_get`.
_scope: contextvars.ContextVar[dict[type, Any] | None] = contextvars.ContextVar(
    "_a2kit_request_scope_seeds",
    default=None,
)


def publish(*values: object) -> ScopeToken:
    """Publish typed seeds for the current request scope.

    Each value is registered by its concrete ``type(value)``. The
    returned token clears EVERY seed this call added when passed to
    :func:`reset`. Multiple values of the same type within a single
    publish (or across publishes within the same scope) follow
    last-write-wins semantics, matching ``Container.provide``.
    """
    current = _scope.get()
    new_state: dict[type, Any] = dict(current) if current is not None else {}
    for value in values:
        new_state[type(value)] = value
    return _scope.set(new_state)


def get(t: type[T]) -> T:
    """Return the published value of type ``t``; raise on absence.

    :raises RequestScopeMissing: when no scope is open OR no value of
        type ``t`` has been published.
    """
    state = _scope.get()
    if state is None or t not in state:
        raise RequestScopeMissing(t)
    return state[t]


def try_get(t: type[T]) -> T | None:
    """Return the published value of type ``t`` or ``None`` (never raises)."""
    state = _scope.get()
    if state is None:
        return None
    return state.get(t)


def all_seeds() -> dict[type, Any]:
    """Return a defensive copy of the current scope's seeds.

    Used by :class:`a2kit.packages.di.container.Container.call_scope`
    to thread framework-tier published values into the per-call child
    container. Mutating the returned dict does NOT mutate the scope.
    """
    state = _scope.get()
    if state is None:
        return {}
    return dict(state)


def reset(token: ScopeToken) -> None:
    """Reset every seed the :func:`publish` returning ``token`` added."""
    _scope.reset(token)


__all__ = (
    "RequestScopeMissing",
    "ScopeToken",
    "all_seeds",
    "get",
    "publish",
    "reset",
    "try_get",
)
