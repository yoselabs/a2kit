"""MCP middleware that publishes the request `Principal` on the dispatch bridge.

Extracts identity from the FastMCP request context (direct
``.principal`` attribute, falling back to ``.access_token`` claims) and
publishes it around ``call_next``. Downstream dispatch stages seed it
into the per-call DI scope. Unauthenticated calls leave the bridge
unset and pass through untouched.
"""

from __future__ import annotations

from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from a2kit.packages.context import Principal
from a2kit.packages.dispatch import (
    reset_request_principal,
    set_request_principal,
)


def _principal_from_context(fastmcp_context: Any) -> Principal | None:
    """Best-effort extract a `Principal` from the FastMCP request context.

    Probes (in order):
      1. `context.principal` -- present once auth-builder lands and stamps it.
      2. `context.access_token` -- FastMCP's `AccessToken` shape:
         `.client_id`, `.scopes` (list[str]), `.claims` (dict).

    Returns `None` when neither path produces a usable identity. The
    exact attribute will be pinned by the `add-auth` change.
    """
    if fastmcp_context is None:
        return None
    direct = getattr(fastmcp_context, "principal", None)
    if isinstance(direct, Principal):
        return direct
    token = getattr(fastmcp_context, "access_token", None)
    if token is None:
        return None
    subject = getattr(token, "client_id", None) or getattr(token, "subject", "")
    raw_scopes = getattr(token, "scopes", ()) or ()
    return Principal(
        subject=str(subject),
        scopes=frozenset(str(s) for s in raw_scopes),
        claims=dict(getattr(token, "claims", {}) or {}),
        issued_by=str(getattr(token, "issuer", "") or ""),
        raw_token=None,
    )


class PrincipalMiddleware(Middleware):
    """Publish the request `Principal` via the dispatch bridge for the call."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: Any,
    ) -> Any:
        principal = _principal_from_context(getattr(context, "fastmcp_context", None))
        if principal is None:
            return await call_next(context)
        token = set_request_principal(principal)
        try:
            return await call_next(context)
        finally:
            reset_request_principal(token)


__all__ = ["PrincipalMiddleware"]
