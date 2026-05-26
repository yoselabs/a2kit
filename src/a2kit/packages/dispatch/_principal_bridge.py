"""Deprecation-shim wrappers for the Principal request-scope bridge.

The Principal bridge moved into the unified
:mod:`a2kit.packages.dispatch.request_scope` per
``generalise-context-bridges`` (2026-05-27). This module exists for one
release to keep out-of-tree callers of ``set_request_principal`` /
``reset_request_principal`` / ``current_request_principal`` /
``current_request_principal_seeds`` working. New code SHOULD use
``request_scope.publish(principal)`` / ``request_scope.get(Principal)``
directly.

Each function emits :class:`DeprecationWarning` on call.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

from a2kit.packages.context import request_scope

if TYPE_CHECKING:
    from a2kit.packages.context import Principal

_DEPRECATION_MESSAGE = (
    "a2kit.packages.dispatch._principal_bridge is a deprecation shim; use a2kit.packages.dispatch.request_scope.publish/get/reset directly."
)


def set_request_principal(principal: Principal) -> request_scope.ScopeToken:
    """Publish ``principal`` via :func:`request_scope.publish`. Deprecated."""
    warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
    return request_scope.publish(principal)


def reset_request_principal(token: request_scope.ScopeToken) -> None:
    """Reset the token returned by :func:`set_request_principal`. Deprecated."""
    warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
    request_scope.reset(token)


def current_request_principal() -> Principal | None:
    """Read the published ``Principal`` for the current context. Deprecated."""
    warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
    from a2kit.packages.context import Principal as _Principal

    return request_scope.try_get(_Principal)


def current_request_principal_seeds() -> dict[type, Any]:
    """Return ``{Principal: p}`` when published, else ``{}``. Deprecated."""
    warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
    from a2kit.packages.context import Principal as _Principal

    principal = request_scope.try_get(_Principal)
    return {_Principal: principal} if principal is not None else {}


__all__ = [
    "current_request_principal",
    "current_request_principal_seeds",
    "reset_request_principal",
    "set_request_principal",
]
