"""Wire-error envelope contract — pins a2kit-owned MCP wire-error bytes.

When a tool body raises an uncaught exception, the MCP wire SHALL
carry a JSON-encoded text payload of shape
``{"class": <ExceptionClassName>, "message": <str(exc)>}``, with
``"traceback"`` added when ``App(debug=True)``. The contract is
owned by a2kit's outermost tool wrapper and does NOT depend on
FastMCP's ``mask_error_details`` flag.

``FastMCPError`` and subclasses (incl. author-raised ``ToolError``)
propagate unwrapped. ``asyncio.CancelledError``,
``KeyboardInterrupt``, ``SystemExit`` propagate unwrapped (they are
``BaseException`` siblings outside ``except Exception``).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import a2kit
from a2kit.packages.mcp.server import build_mcp_server


def _build_app(*, debug: bool = False) -> a2kit.App:
    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def raises_value_error(self) -> dict[str, Any]:
            raise ValueError("boom")

        @a2kit.read()
        async def raises_type_error_special_chars(self) -> dict[str, Any]:
            raise ValueError('a\nb"c')

        @a2kit.read()
        async def raises_tool_error(self) -> dict[str, Any]:
            raise ToolError("custom message")

        @a2kit.read()
        async def raises_cancellation(self) -> dict[str, Any]:
            raise asyncio.CancelledError

        @a2kit.read()
        async def calls_bad_int_cast(self) -> dict[str, Any]:
            int("not a number")
            return {}

        tools = (
            raises_value_error,
            raises_type_error_special_chars,
            raises_tool_error,
            raises_cancellation,
            calls_bad_int_cast,
        )

    return a2kit.AppBuilder("envelope", debug=debug).add_router(R()).build()


async def _call_tool(app: a2kit.App, name: str) -> Any:
    server = build_mcp_server(app)
    async with Client(transport=server) as c:
        return await c.call_tool(name, {}, raise_on_error=False)


def _wire_text(result: Any) -> str:
    """Extract the first text content block from a CallToolResult."""
    text_blocks = [b for b in result.content if getattr(b, "type", None) == "text"]
    assert text_blocks, "expected at least one text content block"
    return text_blocks[0].text


def test_value_error_returns_structured_payload() -> None:
    """The v0.32 P1 blocker reproducer: bare wire string → structured payload."""
    app = _build_app(debug=False)
    result = asyncio.run(_call_tool(app, "raises_value_error"))
    assert result.is_error is True
    payload = json.loads(_wire_text(result))
    assert payload == {"class": "ValueError", "message": "boom"}


def test_value_error_with_debug_includes_traceback() -> None:
    app = _build_app(debug=True)
    result = asyncio.run(_call_tool(app, "raises_value_error"))
    assert result.is_error is True
    payload = json.loads(_wire_text(result))
    assert payload.keys() >= {"class", "message", "traceback"}
    assert payload["class"] == "ValueError"
    assert payload["message"] == "boom"
    assert "ValueError: boom" in payload["traceback"]


def test_author_raised_tool_error_passes_through_unwrapped() -> None:
    """``ToolError`` is a ``FastMCPError`` — passes through verbatim, not JSON-wrapped."""
    app = _build_app(debug=False)
    result = asyncio.run(_call_tool(app, "raises_tool_error"))
    assert result.is_error is True
    text = _wire_text(result)
    # Author message reaches the wire as-is. NOT a JSON envelope.
    assert text == "custom message"
    # Confirm: it does NOT parse as our envelope JSON shape.
    try:
        parsed = json.loads(text)
        assert "class" not in parsed
    except json.JSONDecodeError:
        pass  # plain string, not JSON — that's the expected shape


def test_cancellation_propagates_unwrapped() -> None:
    """``CancelledError`` must not get wrapped into the structured envelope."""
    app = _build_app(debug=False)
    with pytest.raises(BaseException) as excinfo:  # noqa: PT011
        asyncio.run(_call_tool(app, "raises_cancellation"))
    # Either the cancellation surfaces directly, or it surfaces as a
    # ToolError-shaped wire message — but in NO case should the JSON
    # envelope carry class=CancelledError (we route cancellation past
    # the envelope wrapper).
    exc_text = str(excinfo.value)
    if exc_text:
        try:
            parsed = json.loads(exc_text)
            assert parsed.get("class") != "CancelledError"
        except (json.JSONDecodeError, TypeError):
            pass


def test_type_error_class_preserved() -> None:
    app = _build_app(debug=False)
    result = asyncio.run(_call_tool(app, "calls_bad_int_cast"))
    assert result.is_error is True
    payload = json.loads(_wire_text(result))
    assert payload["class"] == "ValueError"
    assert "invalid literal" in payload["message"]


def test_message_with_special_chars_round_trips() -> None:
    app = _build_app(debug=False)
    result = asyncio.run(_call_tool(app, "raises_type_error_special_chars"))
    assert result.is_error is True
    payload = json.loads(_wire_text(result))
    assert payload["class"] == "ValueError"
    assert payload["message"] == 'a\nb"c'


def test_envelope_is_fastmcp_independent_of_debug_flag() -> None:
    """Same `class`+`message` shape with debug on or off."""
    result_off = asyncio.run(_call_tool(_build_app(debug=False), "raises_value_error"))
    result_on = asyncio.run(_call_tool(_build_app(debug=True), "raises_value_error"))
    payload_off = json.loads(_wire_text(result_off))
    payload_on = json.loads(_wire_text(result_on))
    assert payload_off["class"] == payload_on["class"]
    assert payload_off["message"] == payload_on["message"]
    assert "traceback" not in payload_off
    assert "traceback" in payload_on
