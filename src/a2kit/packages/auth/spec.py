"""``AuthSpec`` — the author-facing auth-registration base type.

Subclasses live in sibling modules and load their heavy substrate
dependencies (``fastmcp.server.auth.providers.*``, ``jose``, ``httpx``)
inside helper methods rather than at module import. ``AuthSpec``
itself is a pure dataclass-base contract — it imports nothing from
substrate libraries.

Per ``auth-spec`` capability, ``target`` declares which surface a spec
applies to, and ``build_middleware`` returns the ASGI factory that
authenticates for that surface, so substrate builders mount auth
**generically** — iterate ``registry.for_target(surface.name)`` and
call ``spec.build_middleware()``, with no per-class ``isinstance``
chain and no hardcoded surface name.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar, TypeAlias

# A surface name an auth strategy applies to. Open by design: any
# registered surface (the bundled ``"api"`` / ``"mcp"``, or an internal
# surface like ``"internal"``) can be an auth target, so a spoke or
# other consumer-defined surface mounts its own strategy through the
# same registry filter.
AuthTarget: TypeAlias = str

# An ASGI3 middleware factory: given the inner ASGI app, returns an
# ASGI3 callable that authenticates the request and publishes the
# resolved ``Principal`` before delegating inward.
AsgiFactory: TypeAlias = Callable[[Any], Any]


class AuthSpec:
    """Base class for author-facing auth configurations.

    Concrete subclasses (``APIKeyAuth``, ``TokenAuth``) declare the
    surface they target via the ``target`` ClassVar and return their
    middleware via ``build_middleware`` so substrate builders filter
    the registry and mount uniformly.

    This seam is ASGI-shaped — ``build_middleware`` returns an ASGI
    factory — and covers HTTP surfaces only. MCP OAuth is **not** an
    ``AuthSpec``: a FastMCP OAuth provider is handed to
    ``FastMCP(auth=...)`` directly (ADR 0010; see
    ``docs/patterns/mcp-auth.md``), not registered here.
    """

    target: ClassVar[AuthTarget]

    def build_middleware(self) -> AsgiFactory:
        """Return the ASGI middleware factory authenticating for this spec.

        Subclasses override this. The base raises rather than silently
        producing a no-op — an ``AuthSpec`` with no middleware is a
        construction bug, not a pass-through.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement build_middleware() returning an ASGI middleware factory.")


__all__ = ["AsgiFactory", "AuthSpec", "AuthTarget"]
