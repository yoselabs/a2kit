"""MCP middleware that publishes the request `Principal` for a2kit DI.

FastMCP's authentication chain produces an access token on the request-bound
`Context` (or framework-equivalent attribute). This middleware extracts it,
constructs a substrate-neutral `Principal`, and sets the
`_a2kit_request_principal` contextvar around `call_next`. Inner stages
(`DispatchHookStage`, `AuthorizeGateStage`) seed it as SCOPED into the
per-call DI scope so tool bodies and `authorize=` callables can resolve
it by type alone.

When no token is present (unauthenticated transport / public tool), the
contextvar stays unset and downstream stages skip the SCOPED-write.
"""

from __future__ import annotations

from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from a2kit.packages.context import Principal, _a2kit_request_principal


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
    """Publish the request `Principal` on `_a2kit_request_principal` for the call."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: Any,
    ) -> Any:
        principal = _principal_from_context(getattr(context, "fastmcp_context", None))
        if principal is None:
            return await call_next(context)
        token = _a2kit_request_principal.set(principal)
        try:
            return await call_next(context)
        finally:
            _a2kit_request_principal.reset(token)


__all__ = ["PrincipalMiddleware"]
