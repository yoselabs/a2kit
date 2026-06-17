"""``APIKeyAuth`` — long-lived API keys on the HTTP sub-app.

Authors configure a set of keys (literal iterable or zero-arg callable
for env / secrets-manager sourcing). The middleware reads the
configured header, looks up the key, synthesises a :class:`Principal`,
and publishes it via the dispatch principal bridge
(:mod:`a2kit.packages.dispatch._principal_bridge`) so
:class:`AuthorizeGateStage` and tool bodies resolve
``principal: Principal`` by type.

Missing or unknown keys return 401 with a stable JSON envelope.
Never echoes registered keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from a2kit.packages.auth._asgi import send_401
from a2kit.packages.auth.spec import AsgiFactory, AuthSpec, AuthTarget

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


@dataclass(frozen=True)
class ApiKey:
    """One registered key with its identity payload.

    ``value`` is the secret string clients send in the configured
    header. ``subject`` is the operator-named identity (carried on
    the resolved ``Principal.subject``). ``scopes`` is the per-key
    capability set the ``authorize=`` gate evaluates against.
    """

    value: str
    subject: str
    scopes: frozenset[str] = field(default_factory=frozenset)


@dataclass
class APIKeyAuth(AuthSpec):
    """API-key authentication for the FastAPI sub-app.

    ``keys`` may be a literal iterable of :class:`ApiKey` or a
    zero-arg callable that returns one (resolved once at middleware
    build, not per request — change the registered keys by restarting
    the process or rotating via secrets-manager + restart).

    ``header`` defaults to ``X-API-Key``; override for clients that
    insist on a different header name.
    """

    keys: Iterable[ApiKey] | Callable[[], Iterable[ApiKey]]
    header: str = "X-API-Key"
    target: ClassVar[AuthTarget] = "api"

    def build_middleware(self) -> AsgiFactory:
        """Return an ASGI middleware factory that authenticates by API key.

        The factory takes the inner ASGI app and produces an ASGI3
        callable. Non-HTTP scopes (``lifespan`` / ``websocket``) pass
        through untouched. Keys are materialised once here (not per
        request); the per-request hot path is a dict lookup.
        """
        from a2kit.packages.context import request_scope

        keys_by_value = _materialise_keys(self)
        header_bytes = self.header.encode("ascii").lower()

        def factory(app: Any) -> Any:
            async def middleware(scope: dict[str, Any], receive: Any, send: Any) -> None:
                if scope.get("type") != "http":
                    await app(scope, receive, send)
                    return
                header_value: str | None = None
                for k, v in scope.get("headers", ()):
                    if k == header_bytes:
                        header_value = v.decode("latin-1")
                        break
                if header_value is None:
                    await send_401(send, "missing API key")
                    return
                key = keys_by_value.get(header_value)
                if key is None:
                    await send_401(send, "invalid API key")
                    return
                principal = _principal_from_key(key)
                token = request_scope.publish(principal)
                try:
                    await app(scope, receive, send)
                finally:
                    request_scope.reset(token)

            return middleware

        return factory


def _materialise_keys(spec: APIKeyAuth) -> dict[str, ApiKey]:
    """Resolve ``spec.keys`` (iterable or callable) to a value -> ApiKey map.

    Materialisation happens once at middleware-build time. Per-request
    hot path is a dict lookup, not a list scan.
    """
    src: Any = spec.keys
    raw: Iterable[ApiKey] = src() if callable(src) else src
    return {k.value: k for k in raw}


def _principal_from_key(key: ApiKey) -> Any:
    """Build the :class:`Principal` carried by a request authenticated with ``key``.

    ``raw_token`` is ``None`` — keys MUST NOT be echoed onto the
    propagated identity (the registered set is operator-secret).
    """
    from a2kit.packages.context import Principal

    return Principal(
        subject=key.subject,
        scopes=frozenset(key.scopes),
        claims={},
        issued_by="api-key",
        raw_token=None,
    )


__all__ = ["APIKeyAuth", "ApiKey"]
