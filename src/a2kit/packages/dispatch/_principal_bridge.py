"""The named bridge between substrate authentication and the DI scope.

Carries the per-request ``Principal`` from the substrate's
authentication boundary (HTTP `Security` guard, FastAPI middleware,
FastMCP middleware, APIKey ASGI middleware) into the per-call DI
scope opened by dispatch stages. Stdlib `contextvars` is the bridge
mechanism — robust, async-safe, well-understood.

Discipline this module enforces:

- The underlying ContextVar (``_request_principal``) is module-private
  and MUST NOT be re-exported. Writers use the named functions
  ``set_request_principal`` / ``reset_request_principal``; readers
  use ``current_request_principal``.
- Stage code (``DispatchHookStage``, ``AuthorizeGateStage``,
  ``LddStateStage``) consumes Principal via DI — it reads the bridge
  once and explicitly publishes via ``Container.seed_scoped``. There
  is no other ambient path.
- Adding a new writer means importing the named writer API from this
  module, not the raw ContextVar. The import path is structural; no
  grep gate is needed.

See ``openspec/specs/principal-bridge`` for the locked contract.
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING

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


__all__ = [
    "current_request_principal",
    "reset_request_principal",
    "set_request_principal",
]
