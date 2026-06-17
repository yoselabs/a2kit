"""Shared ASGI helpers for auth middlewares — the 401 envelope + emit.

Every HTTP auth strategy (``APIKeyAuth``, ``TokenAuth``) rejects an
unauthenticated request with the same stable JSON 401 envelope. This
module is the single home for that response shape so the strategies do
not each carry their own copy (``no redundancy``, AGENTS.md §2).

Never echoes the presented secret onto the response.
"""

from __future__ import annotations

import json
from typing import Any


def build_401(reason: str) -> tuple[bytes, list[tuple[bytes, bytes]]]:
    """Build the 401 ASGI response body + headers for an auth failure."""
    body = json.dumps({"error": "authentication_failed", "reason": reason}).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    return body, headers


async def send_401(send: Any, reason: str) -> None:
    """Emit a 401 JSON response over ASGI ``send``."""
    body, headers = build_401(reason)
    await send({"type": "http.response.start", "status": 401, "headers": headers})
    await send({"type": "http.response.body", "body": body})


__all__ = ["build_401", "send_401"]
