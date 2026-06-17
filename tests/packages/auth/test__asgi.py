"""Mirror tests for `a2kit.packages.auth._asgi` — the shared 401 helper."""

from __future__ import annotations

import asyncio
import json

from a2kit.packages.auth._asgi import build_401, send_401


def test_build_401_envelope_shape() -> None:
    """401 body is the stable JSON envelope; headers declare JSON + length."""
    body, headers = build_401("missing token")
    payload = json.loads(body)
    assert payload == {"error": "authentication_failed", "reason": "missing token"}
    header_map = dict(headers)
    assert header_map[b"content-type"] == b"application/json"
    assert header_map[b"content-length"] == str(len(body)).encode("ascii")


def test_send_401_emits_start_then_body() -> None:
    """`send_401` drives ASGI `send` with a 401 start message then the body."""
    sent: list[dict] = []

    async def _send(message: dict) -> None:
        sent.append(message)

    asyncio.run(send_401(_send, "invalid token"))

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 401
    assert sent[1]["type"] == "http.response.body"
    assert json.loads(sent[1]["body"])["reason"] == "invalid token"
