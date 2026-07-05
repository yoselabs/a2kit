"""Auth — author-facing wrappers for HTTP-surface authentication.

Per ``auth-spec`` capability: this package provides the
:class:`AuthSpec` base, the bundled concrete wrappers (``APIKeyAuth``
for long-lived API keys on the HTTP sub-app, ``TokenAuth`` for
per-request lease validation on the internal spoke), and the testing
helper :func:`make_principal`. The :class:`Principal` type lives in
``packages.context``; the per-request bridge that carries Principal
from substrate auth into the per-call DI scope lives in
``packages.dispatch._principal_bridge``; the ``AuthorizeGateStage``
that enforces ``authorize=`` lives in ``packages.dispatch``.

**MCP OAuth (Google et al.) is deliberately not wrapped here.** Per
ADR 0010 a2kit is auth-agnostic on the MCP surface: an author hands a
FastMCP provider straight to ``FastMCP(auth=...)`` — the ``auth=``
kwarg flows through ``build_mcp_server`` and the ``serve`` multiplex's
``mcp_options``. The blessed Google recipe is
``docs/patterns/mcp-auth.md`` (ADR 0011), not shipped code. There is
no ``GoogleAuth`` / ``JwtAuth`` symbol in this package.

Cold-start invariant: ``import a2kit.packages.auth`` SHALL NOT pull
``fastmcp.server.auth.providers.*``, ``jose`` / ``python-jose``,
``httpx``, ``cryptography``. The lazy ``__getattr__`` below loads
each provider's submodule only when its name is requested.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2kit._lazy_module import lazy_attr
from a2kit.packages.auth.registry import AppAuthRegistry
from a2kit.packages.auth.spec import AuthSpec, AuthTarget

if TYPE_CHECKING:
    from a2kit.packages.auth.api_key import ApiKey, APIKeyAuth
    from a2kit.packages.auth.testing import make_principal
    from a2kit.packages.auth.tokenauth import TokenAuth


_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "APIKeyAuth": ("a2kit.packages.auth.api_key", "APIKeyAuth"),
    "ApiKey": ("a2kit.packages.auth.api_key", "ApiKey"),
    "TokenAuth": ("a2kit.packages.auth.tokenauth", "TokenAuth"),
    "make_principal": ("a2kit.packages.auth.testing", "make_principal"),
    "discover_api_key_providers": ("a2kit.packages.auth.discovery", "discover_api_key_providers"),
}

__getattr__ = lazy_attr(__name__, _LAZY_ATTRS)
del lazy_attr


__all__ = [
    "APIKeyAuth",
    "ApiKey",
    "AppAuthRegistry",
    "AuthSpec",
    "AuthTarget",
    "TokenAuth",
    "discover_api_key_providers",
    "make_principal",
]
