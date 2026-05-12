"""Mirror tests for ``a2kit.surface``."""

from __future__ import annotations

import a2kit
from a2kit.metadata import get_meta
from a2kit.surface import Surface


def test_flag_arithmetic_composes() -> None:
    assert Surface.CLI | Surface.MCP == Surface.ALL
    assert Surface.CLI in Surface.ALL
    assert Surface.MCP in Surface.ALL


def test_individual_membership() -> None:
    assert Surface.CLI in (Surface.CLI | Surface.MCP)
    assert Surface.MCP not in Surface.CLI


def test_exposed_on_top_level_namespace() -> None:
    assert a2kit.Surface is Surface


def test_default_decorator_surface_is_all() -> None:
    @a2kit.read()
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = get_meta(f)
    assert meta is not None
    assert meta.extras.surfaces == Surface.ALL


def test_explicit_cli_only_preserved() -> None:
    @a2kit.read(surfaces=Surface.CLI)
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = get_meta(f)
    assert meta is not None
    assert meta.extras.surfaces == Surface.CLI


def test_explicit_mcp_only_preserved() -> None:
    @a2kit.write(surfaces=Surface.MCP)
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = get_meta(f)
    assert meta is not None
    assert meta.extras.surfaces == Surface.MCP


def test_list_decorator_carries_surface() -> None:
    @a2kit.list_(surfaces=Surface.CLI)
    async def f() -> list[dict[str, int]]:
        return [{"k": 1}]

    meta = get_meta(f)
    assert meta is not None
    assert meta.extras.surfaces == Surface.CLI


def test_tool_decorator_carries_surface() -> None:
    from a2kit.tool import tool as tool_decorator

    @tool_decorator(surfaces=Surface.MCP)
    async def f() -> dict[str, int]:
        return {"k": 1}

    meta = get_meta(f)
    assert meta is not None
    assert meta.extras.surfaces == Surface.MCP
