"""Regression tests — `_meta.*` tool hiding via FastMCP-3 `server.disable`.

Pins the contract documented in `operational-contracts` and `health-probe`
specs and the call-site fix in `src/a2kit/packages/mcp/server.py`. The
prior implementation called per-tool `tool.disable()`, which FastMCP 3
removed; every `build_mcp_server(app)` against an app with the health
tool installed crashed with `NotImplementedError`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import warnings
from typing import Any

import pytest

import a2kit
from a2kit.metadata import get_meta, set_meta
from a2kit.packages.mcp.server import build_mcp_server


def _install_h(app: a2kit.App) -> a2kit.App:
    """Install the synthetic `_meta.health` router on ``app`` and return it.

    v0.35: the explicit ``health_tool=True`` constructor flag was
    removed; tests that want the tool present without an explicit
    ``@app.health_check`` registration touch the internal seam directly.
    """
    app._install_health_tool()  # noqa: SLF001 -- test seam
    return app


class _Pinger(a2kit.Router):
    slug = "_pinger"

    @a2kit.read()
    async def ping(self) -> dict[str, Any]:
        return {"pong": True}

    tools = (ping,)


def _app_with_health() -> a2kit.App:
    app = a2kit.App("t")
    app.add_router(_Pinger())
    return _install_h(app)


def test_build_mcp_server_with_health_tool_does_not_raise() -> None:
    """Repro of the round-6 P0: the old code crashed here."""
    build_mcp_server(_app_with_health())


def test_meta_health_registered_in_server_registry() -> None:
    """The disable transform hides `_meta.health` from `list_tools`,
    but the raw registry (via `_get_tool`) still holds it."""
    server = build_mcp_server(_app_with_health(), code_mode=False)

    async def go() -> None:
        raw = await server._get_tool("_meta.health")  # noqa: SLF001
        assert raw is not None
        assert raw.name == "_meta.health"

    asyncio.run(go())


def test_default_list_tools_omits_meta() -> None:
    server = build_mcp_server(_app_with_health(), code_mode=False)

    async def go() -> None:
        listed = await server.list_tools()
        names = {t.name for t in listed}
        assert "ping" in names
        assert not any(n.startswith("_meta.") for n in names), names

    asyncio.run(go())


def test_meta_health_not_callable_via_mcp_wire() -> None:
    """FastMCP-3 `server.disable()` blocks both list and call.
    The CLI surface (`<app> _meta health`) bypasses the MCP wire."""
    from fastmcp.exceptions import NotFoundError

    server = build_mcp_server(_app_with_health(), code_mode=False)

    async def go() -> None:
        with pytest.raises(NotFoundError):
            await server._call_tool_mcp("_meta.health", {})  # noqa: SLF001

    asyncio.run(go())


def test_user_meta_tool_rejected_at_build() -> None:
    """Decoration-time guard already rejects literal `_meta.*` names;
    this exercises the registration-time guard for the metadata-mutation
    bypass path."""

    class _Sneaky(a2kit.Router):
        slug = "_sneaky"

        @a2kit.read()
        async def normal(self) -> dict[str, Any]:
            return {"ok": True}

        tools = (normal,)

    router = _Sneaky()
    app = a2kit.App("sneaky").add_router(router)

    # Force the tool's resolved name into the reserved namespace, bypassing
    # the decoration-time guard. This is the only realistic way a user
    # could land a `_meta.*` tool in the registry today.
    descriptor = next(iter(app.tools()))
    tool_fn = descriptor.fn
    # `app.tools()` yields ToolDescriptors; the metadata lives on the
    # underlying function object (via descriptor.fn → __func__).
    target = getattr(tool_fn, "__func__", tool_fn)
    meta = get_meta(target)
    assert meta is not None
    mutated = dataclasses.replace(meta, tool_name="_meta.custom")
    set_meta(target, mutated)

    with pytest.raises(ValueError, match="reserved namespace"):
        build_mcp_server(app)


def test_no_fastmcp_deprecation_warning_on_build() -> None:
    """`FunctionTool` import path stays on the canonical `fastmcp.tools`
    re-export; building the server must not surface FastMCP's
    deprecation warning."""
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        build_mcp_server(_app_with_health())

    deprecations = [w for w in recorded if "fastmcp" in str(w.filename).lower() and "deprecat" in str(w.category).lower()]
    assert not deprecations, [str(w.message) for w in deprecations]
