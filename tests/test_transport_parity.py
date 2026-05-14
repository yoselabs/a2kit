"""Transport-parity matrix for CLI and MCP — pins the v0.32 blocker.

The v0.32.x MCP transport regression: tools that declared both a
container-resolved DI param (``state: T`` via ``app.singleton``) AND
``ctx: a2kit.ToolContext`` errored 100% of the time over MCP with
``TypeError: missing 1 required keyword-only argument: 'ctx'``. CLI
on the same tool worked fine.

Root cause: ``_wrap_with_dispatch_hook`` rewrote ``__signature__`` to
expose only wire kwargs, stripping both DI injectables and ``ctx``.
FastMCP introspected the rewritten signature, never bound ``ctx``,
and the body crashed missing the required kwarg.

This file pins the contract that every (state-DI, ctx-DI) combination
behaves identically across both transports. The MCP leg uses
``fastmcp.Client(transport=build_mcp_server(app))`` so the real
production wrapper chain is exercised (the in-process test client
bypasses it by design).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastmcp import Client

import a2kit
from a2kit.packages.mcp.server import build_mcp_server
from a2kit.packages.testing.client import client as _make_test_client


# --------------------------------------------------------------------- fixture


class _State:
    """A trivial container-resolved DI singleton used by the parity matrix."""

    tag = "S"


def _build_parity_app() -> a2kit.App:
    """One App, four tools covering the (state, ctx) declaration matrix."""

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def tool_none(self, *, msg: str) -> dict[str, Any]:
            return {"msg": msg}

        @a2kit.read()
        async def tool_state(self, *, msg: str, state: _State) -> dict[str, Any]:
            return {"msg": msg, "state_tag": state.tag}

        @a2kit.read()
        async def tool_ctx(self, *, msg: str, ctx: a2kit.ToolContext) -> dict[str, Any]:
            return {"msg": msg, "has_ctx": ctx is not None}

        @a2kit.read()
        async def tool_both(self, *, msg: str, state: _State, ctx: a2kit.ToolContext) -> dict[str, Any]:
            return {"msg": msg, "state_tag": state.tag, "has_ctx": ctx is not None}

        @a2kit.read()
        async def tool_ctx_emits_event(self, *, ctx: a2kit.ToolContext) -> dict[str, int]:
            from a2kit.packages import ldd

            # Use ldd.info — exercises ambient ctx binding via the same
            # LDD primitive surface as ldd.event but without the
            # event-payload `name` field that collides with Python
            # LogRecord's reserved `name` attribute (a pre-existing
            # cross-transport issue, out of scope here).
            await ldd.info("tick", n=1)  # type: ignore[attr-defined]
            return {"ok": 1}

        @a2kit.read()
        async def tool_raises_value_error(self) -> dict[str, Any]:
            raise ValueError("boom")

        tools = (
            tool_none,
            tool_state,
            tool_ctx,
            tool_both,
            tool_ctx_emits_event,
            tool_raises_value_error,
        )

    app = a2kit.App("parity")
    app.add_router(R())
    app.provide(_State, lambda: _State())
    return app


# ----------------------------------------------------------- transport helpers


def _normalize_mcp_payload(result: Any) -> Any:
    """Unwrap the FastMCP client result into a plain dict (or pass through)."""
    if hasattr(result, "data") and result.data is not None:
        return result.data
    if hasattr(result, "structured_content") and result.structured_content is not None:
        return result.structured_content
    if hasattr(result, "content"):
        # Fallback: a text block with the JSON serialization
        import json as _json

        return _json.loads(result.content[0].text)
    return result


async def _call_mcp_async(app: a2kit.App, tool_name: str, **kwargs: Any) -> Any:
    server = build_mcp_server(app)
    async with Client(transport=server) as c:
        result = await c.call_tool(tool_name, kwargs)
    return _normalize_mcp_payload(result)


def _call_mcp(app: a2kit.App, tool_name: str, **kwargs: Any) -> Any:
    return asyncio.run(_call_mcp_async(app, tool_name, **kwargs))


async def _call_cli_async(app: a2kit.App, tool_name: str, **kwargs: Any) -> Any:
    """Drive the tool via the in-process test client.

    The test client dispatches through the hook (DI resolution, ambient
    LDD state binding) without rebuilding the MCP wrapper chain — which
    is the correct CLI-side reference for parity (CLI also lacks the
    MCP wrapper chain).
    """
    async with _make_test_client(app) as c:
        return await c.invoke(tool_name, **kwargs)


def _call_cli(app: a2kit.App, tool_name: str, **kwargs: Any) -> Any:
    return asyncio.run(_call_cli_async(app, tool_name, **kwargs))


# ---------------------------------------------------------------- parity cases


def test_case1_tool_none_parity() -> None:
    app = _build_parity_app()
    expected = {"msg": "x"}
    assert _call_cli(app, "tool_none", msg="x") == expected
    assert _call_mcp(app, "tool_none", msg="x") == expected


def test_case2_tool_state_parity() -> None:
    app = _build_parity_app()
    expected = {"msg": "x", "state_tag": "S"}
    assert _call_cli(app, "tool_state", msg="x") == expected
    assert _call_mcp(app, "tool_state", msg="x") == expected


def test_case3_tool_ctx_parity() -> None:
    app = _build_parity_app()
    expected = {"msg": "x", "has_ctx": True}
    assert _call_cli(app, "tool_ctx", msg="x") == expected
    assert _call_mcp(app, "tool_ctx", msg="x") == expected


def test_case4_tool_both_parity_v032_blocker() -> None:
    """THE v0.32 BLOCKER REGRESSION TEST.

    Pre-fix this assertion fails on the MCP leg with
    ``TypeError: missing 'ctx'`` because the wrapper chain stripped
    ctx from the rewritten signature.
    """
    app = _build_parity_app()
    expected = {"msg": "x", "state_tag": "S", "has_ctx": True}
    assert _call_cli(app, "tool_both", msg="x") == expected
    assert _call_mcp(app, "tool_both", msg="x") == expected


def test_case5_unknown_kwarg_parity() -> None:
    """Both transports reject unknown kwargs.

    Post ``rebuild-test-client-on-real-context``, the CLI-side test
    client routes through the real MCP transport and FastMCP's wire
    validation surfaces unknown kwargs as ``ToolError`` on both
    legs.
    """
    app = _build_parity_app()
    with pytest.raises(Exception):  # noqa: B017,BLE001 -- ToolError or TypeError
        _call_cli(app, "tool_none", msg="x", extra="y")
    with pytest.raises(Exception):  # noqa: B017,BLE001
        _call_mcp(app, "tool_none", msg="x", extra="y")


def test_case6_missing_required_raises_on_both() -> None:
    """Missing-required-kwarg surfaces as an error on both transports.

    Post ``rebuild-test-client-on-real-context`` the CLI-side test client
    goes through the real MCP transport; missing kwargs surface as a
    FastMCP pydantic validation error wrapped in ``ToolError`` on both
    transports. (Pre-rebuild, the CLI side raised Python ``TypeError``;
    the new client is more rigorous and catches the missing-arg case
    earlier, in FastMCP's wire validation.)
    """
    app = _build_parity_app()
    with pytest.raises(Exception):  # noqa: B017,BLE001
        _call_cli(app, "tool_state")
    with pytest.raises(Exception):  # noqa: B017,BLE001
        _call_mcp(app, "tool_state")


def test_case7_ctx_emits_event_round_trips_both() -> None:
    """Ambient ctx must be bound on both transports so LDD primitives work."""
    app = _build_parity_app()
    expected = {"ok": 1}
    assert _call_cli(app, "tool_ctx_emits_event") == expected
    assert _call_mcp(app, "tool_ctx_emits_event") == expected


def test_case8_value_error_surfaces_on_both() -> None:
    """User-raised exception class is parseable via the wire envelope.

    After ``mcp-structured-wire-error-envelope`` and
    ``rebuild-test-client-on-real-context``, both transports surface
    tool-body exceptions as ``fastmcp.exceptions.ToolError`` carrying
    ``{"class": "ValueError", "message": "boom"}`` JSON.
    """
    import json as _json

    from fastmcp.exceptions import ToolError

    app = _build_parity_app()
    for caller in (_call_cli, _call_mcp):
        with pytest.raises(ToolError) as ei:
            caller(app, "tool_raises_value_error")
        payload = _json.loads(str(ei.value))
        assert payload["class"] == "ValueError"
        assert payload["message"] == "boom"


def test_case9_optional_ctx_rejected_at_decoration() -> None:
    """Declaring ``ctx: ToolContext | None`` raises at decorator time."""
    from a2kit.exceptions import A2KitInvalidContextAnnotation

    with pytest.raises(A2KitInvalidContextAnnotation):

        class _R(a2kit.Router):
            slug = "bad"

            @a2kit.read()
            async def bad_ctx(self, *, ctx: a2kit.ToolContext | None = None) -> dict[str, int]:
                return {"ok": 1}

            tools = (bad_ctx,)
