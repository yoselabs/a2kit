"""Tests for ``@a2kit.read/write/list_(timeout=...)``.

Verifies parsing (float / int / string with unit suffix), MCP wire
behavior (TimeoutError → structured envelope), CLI parity, meta
surfacing, and the no-op path when timeout is unset.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastmcp import Client

import a2kit
from a2kit.metadata import get_meta
from a2kit.packages.mcp.server import build_mcp_server
from a2kit.tool import _parse_timeout


# ----------------------------------------------------------- _parse_timeout


def test_parse_timeout_none_returns_none() -> None:
    assert _parse_timeout(None) is None


def test_parse_timeout_float_passes_through() -> None:
    assert _parse_timeout(60.5) == 60.5


def test_parse_timeout_int_becomes_float() -> None:
    result = _parse_timeout(60)
    assert result == 60.0
    assert isinstance(result, float)


def test_parse_timeout_bare_string_seconds() -> None:
    assert _parse_timeout("60") == 60.0


def test_parse_timeout_s_suffix() -> None:
    assert _parse_timeout("60s") == 60.0


def test_parse_timeout_m_suffix() -> None:
    assert _parse_timeout("2m") == 120.0


def test_parse_timeout_ms_suffix() -> None:
    assert _parse_timeout("500ms") == 0.5


def test_parse_timeout_ms_checked_before_s() -> None:
    """The ``ms`` suffix must take precedence over the bare ``s`` suffix."""
    assert _parse_timeout("250ms") == 0.25


def test_parse_timeout_invalid_string_raises_typeerror() -> None:
    with pytest.raises(TypeError, match="not a valid"):
        _parse_timeout("2 hours")


def test_parse_timeout_bool_rejected() -> None:
    with pytest.raises(TypeError, match="bool"):
        _parse_timeout(True)  # type: ignore[arg-type]  # noqa: FBT003


def test_parse_timeout_other_type_rejected() -> None:
    with pytest.raises(TypeError):
        _parse_timeout([60])  # type: ignore[arg-type]


# ----------------------------------------------------------- decorator stamps


def test_read_decorator_stamps_timeout_seconds() -> None:
    @a2kit.read(timeout="60s")
    async def fn() -> dict[str, int]:
        return {"k": 1}

    meta = get_meta(fn)
    assert meta is not None
    assert meta.extras.timeout_seconds == 60.0


def test_read_decorator_string_form_parses() -> None:
    @a2kit.read(timeout="500ms")
    async def fn() -> dict[str, int]:
        return {"k": 1}

    meta = get_meta(fn)
    assert meta is not None
    assert meta.extras.timeout_seconds == 0.5


def test_read_decorator_no_timeout_means_none() -> None:
    @a2kit.read()
    async def fn() -> dict[str, int]:
        return {"k": 1}

    meta = get_meta(fn)
    assert meta is not None
    assert meta.extras.timeout_seconds is None


def test_invalid_timeout_string_raises_at_decoration() -> None:
    with pytest.raises(TypeError, match="not a valid"):

        @a2kit.read(timeout="indefinitely")
        async def _bad() -> dict[str, int]:
            return {"k": 1}


# ----------------------------------------------------------- MCP transport


def _build_app_with(tool_fn: Any) -> a2kit.App:
    class _R(a2kit.Router):
        slug = "demo"
        tools = (tool_fn,)

    setattr(_R, tool_fn.__name__, tool_fn)
    app = a2kit.App("t").add_router(_R())
    return app


async def _call_mcp(app: a2kit.App, name: str) -> Any:
    server = build_mcp_server(app)
    async with Client(transport=server) as c:
        return await c.call_tool(name, {}, raise_on_error=False)


def test_timeout_fires_over_mcp_returns_envelope() -> None:
    @a2kit.read(timeout=0.05)
    async def slow(self) -> dict[str, int]:  # noqa: ARG001
        await asyncio.sleep(0.5)
        return {"k": 1}

    app = _build_app_with(slow)
    result = asyncio.run(_call_mcp(app, "slow"))
    assert result.is_error is True
    payload = json.loads(result.content[0].text)
    assert payload["class"] == "TimeoutError"


def test_no_timeout_runs_to_completion_over_mcp() -> None:
    @a2kit.read()
    async def fast(self) -> dict[str, int]:  # noqa: ARG001
        await asyncio.sleep(0.01)
        return {"k": 42}

    app = _build_app_with(fast)
    result = asyncio.run(_call_mcp(app, "fast"))
    assert result.is_error is False
    payload = result.structured_content
    assert payload == {"k": 42}


def test_timeout_does_not_fire_when_body_completes_in_time() -> None:
    @a2kit.read(timeout=1.0)
    async def quick(self) -> dict[str, int]:  # noqa: ARG001
        await asyncio.sleep(0.01)
        return {"k": 9}

    app = _build_app_with(quick)
    result = asyncio.run(_call_mcp(app, "quick"))
    assert result.is_error is False
    assert result.structured_content == {"k": 9}


# ----------------------------------------------------------- CLI transport


def test_timeout_fires_over_in_process_test_client() -> None:
    """The in-process test client routes through real MCP transport
    (post ``rebuild-test-client-on-real-context``), so the timeout
    wrapper is exercised end-to-end.
    """
    from fastmcp.exceptions import ToolError

    from a2kit.testing import client

    @a2kit.read(timeout=0.05)
    async def slow(self) -> dict[str, int]:  # noqa: ARG001
        await asyncio.sleep(0.5)
        return {"k": 1}

    app = _build_app_with(slow)

    async def go() -> None:
        async with client(app) as c:
            with pytest.raises(ToolError) as ei:
                await c.invoke("slow")
            payload = json.loads(str(ei.value))
            assert payload["class"] == "TimeoutError"

    asyncio.run(go())
