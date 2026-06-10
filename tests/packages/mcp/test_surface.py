"""``McpSurface`` — author-side ``@app.mcp.tool/.prompt/.resource``."""

from __future__ import annotations

import pytest

from a2kit.packages.mcp.surface import McpRegistration, McpSurface


def test_tool_records_registration() -> None:
    surface = McpSurface()

    @surface.tool(name="hello")
    async def _hello() -> dict[str, str]:
        return {"v": "hi"}

    assert len(surface.registrations) == 1
    reg = surface.registrations[0]
    assert isinstance(reg, McpRegistration)
    assert reg.kind == "tool"
    assert reg.fastmcp_kwargs == {"name": "hello"}


def test_prompt_and_resource() -> None:
    surface = McpSurface()

    @surface.prompt(name="summarize")
    async def _p() -> list[dict[str, str]]:
        return []

    @surface.resource(uri="memo://x")
    async def _r() -> list[dict[str, str]]:
        return []

    kinds = [r.kind for r in surface.registrations]
    assert kinds == ["prompt", "resource"]


def test_surfaces_kwarg_rejected() -> None:
    surface = McpSurface()
    with pytest.raises(TypeError, match=r"surfaces="):

        @surface.tool(surfaces=["mcp"])
        async def _h() -> None:
            return None


def test_authorize_kwarg_captured() -> None:
    surface = McpSurface()

    async def _gate() -> bool:
        return True

    @surface.tool(authorize=_gate)
    async def _h() -> None:
        return None

    reg = surface.registrations[0]
    assert reg.authorize is _gate
    assert "authorize" not in reg.fastmcp_kwargs


def test_fastmcp_server_starts_unset() -> None:
    surface = McpSurface()
    assert surface.fastmcp_server is None
