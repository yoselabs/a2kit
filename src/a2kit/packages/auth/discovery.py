"""Manifest-driven discovery helpers for auth providers.

Thin wrappers over :func:`a2kit.packages._plugin.load_surface` that
bind the surface path + protocol per discoverable surface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2kit.packages._plugin import load_surface

if TYPE_CHECKING:
    from a2kit.packages.auth.api_key import APIKeyAuth


def discover_api_key_providers(context: object) -> dict[str, APIKeyAuth]:
    """Discover manifest-declared API-key auth providers under ``_providers/``.

    Returns ``{name: APIKeyAuth}``. ``context`` is forwarded to each
    manifest's factory (today: an iterable of :class:`ApiKey` or a
    zero-arg callable returning one). Providers whose factory returns
    :class:`Unavailable` are dropped before reaching the caller.

    Imperative registration via ``App.auth(APIKeyAuth(...))`` continues
    to work; manifest discovery is an additive, opt-in path.
    """
    from a2kit.packages.auth.api_key import APIKeyAuth

    return load_surface("a2kit.packages.auth._providers", APIKeyAuth, context)


__all__ = ["discover_api_key_providers"]
