"""``TokenAuth`` — lease-validating token auth for the internal spoke.

Unlike :class:`APIKeyAuth` (which materialises its key set **once** at
middleware-build time), ``TokenAuth`` calls a consumer-supplied
``resolve(token) -> Principal | None`` on **every request**. That makes
two properties fall out for free:

- **No fixed TTL.** A long-running caller (a day-long transcription job)
  presents the same token across the whole run; each call re-resolves
  against the live set, so a valid lease never expires mid-span.
- **Instant revocation.** When the runner drops a token from the live
  set, the next call that presents it fails with 401 — no expiry to
  wait out.

a2kit does **not** own the lease table or its lifecycle (mint at job
spawn, revoke at exit). ``TokenAuth`` holds only the ``resolve`` closure
it is handed, so the table — and any secret in it — stays outside a2kit
and outside the synced vault.

Missing or unresolvable tokens return 401 with the shared JSON envelope
(:mod:`a2kit.packages.auth._asgi`). Never echoes the presented token.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from a2kit.packages.auth._asgi import send_401
from a2kit.packages.auth.spec import AsgiFactory, AuthSpec, AuthTarget

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.packages.context import Principal


@dataclass
class TokenAuth(AuthSpec):
    """Per-request lease validation against a live, consumer-owned set.

    ``resolve`` is a zero-state callable mapping a presented token to a
    :class:`Principal` (with the lease's least-privilege scopes) or
    ``None`` for an unknown / revoked token. It is invoked once per
    request — the runner is free to mutate the underlying set between
    calls.

    ``header`` defaults to ``X-A2kit-Token``; override only to match a
    client that insists on a different header name.

    ``target`` is ``"internal"`` — the spoke surface. The generic auth
    mount (``_install_auth_middlewares``) picks this spec up via
    ``registry.for_target("internal")`` with no isinstance branch.
    """

    resolve: Callable[[str], Principal | None]
    header: str = "X-A2kit-Token"
    target: ClassVar[AuthTarget] = "internal"

    def build_middleware(self) -> AsgiFactory:
        """Return an ASGI factory that authenticates by resolving the token per request."""
        from a2kit.packages.context import request_scope

        header_bytes = self.header.encode("ascii").lower()
        resolve = self.resolve

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
                    await send_401(send, "missing token")
                    return
                # Per-request resolution: the live set may have changed
                # since the last call — this is what makes revocation
                # instant and leases TTL-free.
                principal = resolve(header_value)
                if principal is None:
                    await send_401(send, "invalid token")
                    return
                token = request_scope.publish(principal)
                try:
                    await app(scope, receive, send)
                finally:
                    request_scope.reset(token)

            return middleware

        return factory


__all__ = ["TokenAuth"]
