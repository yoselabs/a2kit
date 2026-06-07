"""Single-mode wire rule for MCP rendering (Group 14).

Success: ``content[0].text`` only, ``structuredContent`` omitted when
both channels would carry the same info.
Error: prose in ``content[0].text`` + ``structuredContent.error`` carrying
the envelope dict, ``isError = true``.
"""

from __future__ import annotations

from typing import Annotated

import a2kit
from a2effect import AppError, Raises
from a2kit.packages.mcp.server import build_mcp_server
from a2kit.runtime import build


class _NotFound(AppError):
    kind = "input"
    http_status = 404
    hint = "verify the id from list_memories"


async def test_success_returns_without_typed_error_channel() -> None:
    """Success path: `structured_content` does NOT carry an `error` key."""
    from fastmcp import Client

    class R(a2kit.Router):
        slug = "echo"

        @a2kit.read()
        async def ping(self, *, msg: str) -> dict:
            return {"msg": msg}

    app = a2kit.App("t").add_router(R())
    server = build_mcp_server(build(app), code_mode=False)
    async with Client(server) as client:
        result = await client.call_tool("ping", {"msg": "hi"})

    assert result.is_error is False
    # The typed-error envelope channel is NOT touched on success.
    if result.structured_content is not None:
        assert "error" not in result.structured_content


async def test_error_emits_prose_plus_structured_envelope() -> None:
    from fastmcp import Client

    class R(a2kit.Router):
        slug = "mem"

        @a2kit.read()
        async def fetch(self, *, id: str) -> Annotated[dict, Raises(_NotFound)]:
            raise _NotFound(f"memory id {id!r} does not exist", details={"id": id})

    app = a2kit.App("t").add_router(R())
    server = build_mcp_server(build(app), code_mode=False)
    async with Client(server) as client:
        result = await client.call_tool("fetch", {"id": "abc"}, raise_on_error=False)

    assert result.is_error is True
    # Prose contains kind label + type + message + hint
    text = result.content[0].text
    assert "Input error (_NotFound):" in text
    assert "memory id 'abc' does not exist" in text
    assert "Hint: verify the id from list_memories" in text
    # structuredContent carries the envelope dict
    assert result.structured_content is not None
    envelope = result.structured_content["error"]
    assert envelope["type"] == "_NotFound"
    assert envelope["kind"] == "input"
    assert envelope["base_kind"] == "input"
    assert envelope["details"] == {"id": "abc"}
    assert envelope["hint"] == "verify the id from list_memories"
    assert envelope["envelope_version"] == "1"


async def test_non_app_error_quarantined_as_unexpected_defect() -> None:
    from fastmcp import Client

    class R(a2kit.Router):
        slug = "broken"

        @a2kit.read()
        async def boom(self, *, x: int) -> int:
            raise KeyError(f"bad-{x}")

    app = a2kit.App("t").add_router(R())
    server = build_mcp_server(build(app), code_mode=False)
    async with Client(server) as client:
        result = await client.call_tool("boom", {"x": 1}, raise_on_error=False)

    assert result.is_error is True
    text = result.content[0].text
    assert "Internal error (UnexpectedDefect):" in text
    envelope = result.structured_content["error"]
    assert envelope["type"] == "UnexpectedDefect"
    assert envelope["kind"] == "bug"
    assert envelope["retryable"] is False
