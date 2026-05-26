"""API-key auth provider — pilot manifest for the framework's plugin shape.

The factory takes a per-app context (an iterable of :class:`ApiKey` or
a zero-arg callable returning one) and constructs an
:class:`APIKeyAuth` instance. Returns ``Unavailable("no keys")`` when
the context carries no keys, so the provider never lands in the
registry on an unconfigured deploy.

This is the only side-effect-free statement set permitted in a
manifest module: import, factory definition, MANIFEST assignment. No
top-level network calls, no env reads, no registry mutation.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, cast

from a2kit.packages._plugin import PluginManifest, Unavailable
from a2kit.packages.auth.api_key import APIKeyAuth

if TYPE_CHECKING:
    from a2kit.packages.auth.api_key import ApiKey


def _factory(context: object) -> APIKeyAuth | Unavailable:
    """Construct an ``APIKeyAuth`` from ``context`` or return Unavailable.

    Two accepted context shapes:
      * an iterable of :class:`ApiKey` (resolved once at boot);
      * a zero-arg callable returning one (resolved at middleware build).

    Empty / missing keys → ``Unavailable("no api keys configured")``.
    """
    if context is None:
        return Unavailable("no api keys configured")
    if callable(context):
        keys_callable = cast("Callable[[], Iterable[ApiKey]]", context)
        return APIKeyAuth(keys=keys_callable)
    if isinstance(context, Iterable):
        # The caller is responsible for passing the right element type;
        # the framework treats `context` opaquely per PluginManifest contract.
        materialised: tuple[Any, ...] = tuple(context)
        if not materialised:
            return Unavailable("no api keys configured")
        return APIKeyAuth(keys=materialised)
    return Unavailable(f"unsupported context type {type(context).__name__}")


MANIFEST = PluginManifest(
    name="api_key",
    protocol=APIKeyAuth,
    factory=_factory,
)
