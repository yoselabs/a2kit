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

from typing import TYPE_CHECKING

from a2kit._lazy_module import lazy_attr
from a2kit.packages.auth.registry import AppAuthRegistry
from a2kit.packages.auth.spec import AuthSpec, AuthTarget

if TYPE_CHECKING:
    from a2kit.packages.auth.api_key import ApiKey, APIKeyAuth
    from a2kit.packages.auth.testing import make_principal


_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "APIKeyAuth": ("a2kit.packages.auth.api_key", "APIKeyAuth"),
    "ApiKey": ("a2kit.packages.auth.api_key", "ApiKey"),
    "build_api_key_middleware": ("a2kit.packages.auth.api_key", "build_api_key_middleware"),
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
    "discover_api_key_providers",
    "make_principal",
]
