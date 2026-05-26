"""Per-request ``Principal`` bridge between substrate auth and the DI scope.

Stdlib ``contextvars`` carries the identity published by a substrate
authentication boundary into the per-call DI scope opened by dispatch
stages. The ContextVar itself is module-private; writers/readers use
the named functions below.

See ``openspec/specs/principal-bridge`` for the locked contract.
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from a2kit.packages.context import Principal


_request_principal: contextvars.ContextVar[Principal | None] = contextvars.ContextVar(
    "a2kit_request_principal",
    default=None,
)


def set_request_principal(principal: Principal) -> contextvars.Token[Principal | None]:
    """Publish ``principal`` for the current async context.

    Returns a token the caller MUST pass to :func:`reset_request_principal`
    in a ``finally`` block to restore the prior state.
    """
    return _request_principal.set(principal)


def reset_request_principal(token: contextvars.Token[Principal | None]) -> None:
    """Restore the state captured by a prior :func:`set_request_principal`."""
    _request_principal.reset(token)


def current_request_principal() -> Principal | None:
    """Return the substrate-published Principal for the current context, or None."""
    return _request_principal.get()


def current_request_principal_seeds() -> dict[type, Any]:
    """Return ``{Principal: p}`` when published, else ``{}`` — ready for ``scoped_seeds=``."""
    from a2kit.packages.context import Principal as _Principal

    principal = _request_principal.get()
    return {_Principal: principal} if principal is not None else {}


__all__ = [
    "current_request_principal",
    "current_request_principal_seeds",
    "reset_request_principal",
    "set_request_principal",
]
