"""Spoke client — dial the internal UDS spoke and invoke verbs by name.

A first-party job spawned by the app's runner calls verbs back into the
single-writer core process over the spoke's Unix domain socket. This is
the **supported** client so jobs never import ``httpx`` internals or
hand-roll socket code.

The client carries no tool catalog of its own: it forwards the canonical
verb name straight to the spoke, whose reachable set is exactly the API
surface's projected catalog (``no second catalog``, per ``internal-spoke``).
A name the spoke does not project returns 404 → :class:`SpokeError`.

Cold-start: ``httpx`` is imported lazily on first call, not at module
import — a job that constructs the client but never invokes pays nothing.
"""

from __future__ import annotations

from typing import Any


class SpokeError(RuntimeError):
    """A spoke call returned a non-2xx response.

    ``status`` is the HTTP status; ``payload`` is the decoded JSON error
    envelope when present, else the raw response text. 401 means the
    lease token was missing or revoked; 404 means the verb name is not
    projected on the spoke.
    """

    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self.payload = payload
        super().__init__(f"spoke call failed [{status}]: {payload}")


class SpokeClient:
    """A thin, lazily-connected client over the spoke's UDS.

    ``invoke(name, **kwargs)`` posts ``kwargs`` as the verb's wire body to
    ``/{name}`` with the lease token header and returns the decoded result.
    Use as a context manager (or call :meth:`close`) to release the
    underlying connection.
    """

    def __init__(self, socket_path: str, token: str, *, header: str = "X-A2kit-Token") -> None:
        self._socket_path = socket_path
        self._token = token
        self._header = header
        self._client: Any = None

    def _ensure(self) -> Any:
        if self._client is None:
            import httpx

            transport = httpx.HTTPTransport(uds=self._socket_path)
            self._client = httpx.Client(transport=transport, base_url="http://spoke")
        return self._client

    def invoke(self, name: str, **kwargs: Any) -> Any:
        """Call verb ``name`` over the spoke; return its decoded result.

        Raises :class:`SpokeError` on any non-2xx response (auth failure,
        unknown verb, or a verb-raised typed error rendered by the
        dispatcher).
        """
        client = self._ensure()
        resp = client.post(f"/{name}", headers={self._header: self._token}, json=kwargs)
        if resp.status_code // 100 != 2:
            try:
                payload = resp.json()
            except ValueError:
                payload = resp.text
            raise SpokeError(resp.status_code, payload)
        return resp.json()

    def close(self) -> None:
        """Close the underlying connection (idempotent)."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> SpokeClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def client(socket_path: str, token: str, *, header: str = "X-A2kit-Token") -> SpokeClient:
    """Open a :class:`SpokeClient` for the spoke at ``socket_path``.

    ``token`` is the lease the runner minted for this job; ``header``
    overrides the token header only to match a non-default ``TokenAuth``.
    """
    return SpokeClient(socket_path, token, header=header)


__all__ = ["SpokeClient", "SpokeError", "client"]
