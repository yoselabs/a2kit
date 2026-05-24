"""Auth — author-facing wrappers for MCP OAuth and HTTP API keys / JWT.

Per ``auth-spec`` capability: this package provides the
:class:`AuthSpec` base, the bundled concrete wrappers (``APIKeyAuth``,
``JwtAuth``, ``GoogleAuth``), and the testing seam
(``authenticated_as`` / ``make_principal``). The :class:`Principal`
type, the per-request contextvar, and the ``AuthorizeGateStage`` that
enforces ``authorize=`` already live in ``packages.context`` /
``packages.dispatch`` (landed by ``propagate-principal-and-authorize``).

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
    from a2kit.packages.auth.testing import authenticated_as, make_principal


def __getattr__(name: str) -> Any:
    """PEP 562 lazy loader for the bundled wrappers + test seam."""
    if name in ("APIKeyAuth", "ApiKey", "build_api_key_middleware"):
        from a2kit.packages.auth import api_key

        return getattr(api_key, name)
    if name in ("authenticated_as", "make_principal"):
        from a2kit.packages.auth import testing

        return getattr(testing, name)
    raise AttributeError(f"module 'a2kit.packages.auth' has no attribute {name!r}")


__all__ = [
    "APIKeyAuth",
    "ApiKey",
    "AppAuthRegistry",
    "AuthSpec",
    "AuthTarget",
    "authenticated_as",
    "make_principal",
]
