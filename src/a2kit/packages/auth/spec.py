"""``AuthSpec`` — the author-facing auth-registration base type.

Subclasses live in sibling modules and load their heavy substrate
dependencies (``fastmcp.server.auth.providers.*``, ``jose``, ``httpx``)
inside helper methods rather than at module import. ``AuthSpec``
itself is a pure dataclass-base contract — it imports nothing from
substrate libraries.

Per ``auth-spec`` capability, ``target`` declares which surface a
spec applies to so ``build_http_app`` / ``build_mcp_server`` can pick
out matching specs from the App's auth registry without per-class
isinstance chains.
"""

from __future__ import annotations

from typing import ClassVar, Literal

AuthTarget = Literal["api", "mcp"]


class AuthSpec:
    """Base class for author-facing auth configurations.

    Concrete subclasses (``GoogleAuth``, ``APIKeyAuth``, ``JwtAuth``)
    declare the surface they target via the ``target`` ClassVar so
    substrate builders can filter the registry uniformly.
    """

    target: ClassVar[AuthTarget]


__all__ = ["AuthSpec", "AuthTarget"]
