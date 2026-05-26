"""Auth — author-facing wrappers for MCP OAuth and HTTP API keys / JWT.

Per ``auth-spec`` capability: this package provides the
:class:`AuthSpec` base, the bundled concrete wrappers (``APIKeyAuth``,
``JwtAuth``, ``GoogleAuth``), and the testing helper
:func:`make_principal`. The :class:`Principal` type lives in
``packages.context``; the per-request bridge that carries Principal
from substrate auth into the per-call DI scope lives in
``packages.dispatch._principal_bridge``; the ``AuthorizeGateStage``
that enforces ``authorize=`` lives in ``packages.dispatch``.

Cold-start invariant: ``import a2kit.packages.auth`` SHALL NOT pull
``fastmcp.server.auth.providers.*``, ``jose`` / ``python-jose``,
``httpx``, ``cryptography``. The lazy ``__getattr__`` below loads
each provider's submodule only when its name is requested.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.packages.auth.registry import AppAuthRegistry
from a2kit.packages.auth.spec import AuthSpec, AuthTarget

if TYPE_CHECKING:
    from a2kit.packages.auth.api_key import ApiKey, APIKeyAuth
    from a2kit.packages.auth.testing import make_principal


def __getattr__(name: str) -> Any:
    """PEP 562 lazy loader for the bundled wrappers + test seam."""
    if name in ("APIKeyAuth", "ApiKey", "build_api_key_middleware"):
        from a2kit.packages.auth import api_key

        return getattr(api_key, name)
    if name == "make_principal":
        from a2kit.packages.auth import testing

        return testing.make_principal
    if name == "discover_api_key_providers":
        from a2kit.packages.auth import discovery

        return discovery.discover_api_key_providers
    raise AttributeError(f"module 'a2kit.packages.auth' has no attribute {name!r}")


__all__ = [
    "APIKeyAuth",
    "ApiKey",
    "AppAuthRegistry",
    "AuthSpec",
    "AuthTarget",
    "discover_api_key_providers",
    "make_principal",
]
