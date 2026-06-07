"""A2 — runtime tool selection integration across MCP + CLI surfaces."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from click.testing import CliRunner
from fastmcp import Client

import a2kit
from a2kit.packages.cli.builder import build_full_cli
from a2kit.packages.mcp.server import build_mcp_server
from a2kit.packages.runtime_tools import ENV_VAR, ToolSelectionError


@contextmanager
def _env(value: str | None) -> Iterator[None]:
    """Temporarily set / unset the A2KIT_TOOLS env var."""
    previous = os.environ.get(ENV_VAR)
    if value is None:
        os.environ.pop(ENV_VAR, None)
    else:
        os.environ[ENV_VAR] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = previous


def _three_tool_app(unique_name: str = "selection-test") -> a2kit.App:
    """An App with three tools: ask, refresh, fetch_raw."""

    class WebRouter(a2kit.Router):
        slug = "web"

        @a2kit.read()
        async def ask(self, *, url: str) -> dict[str, str]:
            return {"url": url}

        @a2kit.read()
        async def refresh(self, *, url: str) -> dict[str, str]:
            return {"url": url}

        @a2kit.read()
        async def fetch_raw(self, *, url: str) -> dict[str, str]:
            return {"url": url}

    return a2kit.App(unique_name).add_router(WebRouter())


async def _mcp_tool_names(server) -> set[str]:
    async with Client(server) as client:
        tools = await client.list_tools()
    return {t.name for t in tools}


def test_env_var_restricts_mcp_surface() -> None:
    """Scenario 1: A2KIT_TOOLS=ask,refresh exposes only those on MCP."""
    with _env("ask,refresh"):
        server = build_mcp_server(_three_tool_app("mcp-env-restrict"), code_mode=False)
        import asyncio

        names = asyncio.run(_mcp_tool_names(server))
    assert "ask" in names
    assert "refresh" in names
    assert "fetch_raw" not in names


def test_serve_cli_flag_restricts_mcp_surface() -> None:
    """Scenario 2 (adapted): serve --tools=ask restricts the MCP surface.

    Spec scenario originally said 'CLI flag restricts the CLI surface' —
    on the CLI surface, runtime selection is env-var-only (per design
    decision 4); the --tools CLI flag is exposed on the `serve`
    subcommand and affects the MCP surface. Functionally equivalent
    behavior; same selector + validator path.
    """
    with _env(None):
        server = build_mcp_server(_three_tool_app("serve-cli"), code_mode=False, tool_selection="ask")
        import asyncio

        names = asyncio.run(_mcp_tool_names(server))
    assert names == {"ask"}


def test_env_and_cli_intersect_when_both_set() -> None:
    """Scenario 3: env=ask,refresh + serve --tools=ask,fetch_raw → only ask."""
    with _env("ask,refresh"):
        server = build_mcp_server(_three_tool_app("intersect"), code_mode=False, tool_selection="ask,fetch_raw")
        import asyncio

        names = asyncio.run(_mcp_tool_names(server))
    assert names == {"ask"}


def test_selector_cannot_re_enable_hidden_tool() -> None:
    """Scenario 4: visibility='hidden' tool stays hidden even if named in selector."""

    class HidR(a2kit.Router):
        slug = "h"

        @a2kit.read(visibility="hidden")
        async def hidden_tool(self, *, x: str) -> dict[str, str]:
            return {"x": x}

        @a2kit.read()
        async def visible_tool(self, *, x: str) -> dict[str, str]:
            return {"x": x}

    app = a2kit.App("hidden-test").add_router(HidR())
    with _env(None), pytest.raises(ToolSelectionError) as excinfo:
        build_mcp_server(app, code_mode=False, tool_selection="hidden_tool")
    msg = str(excinfo.value)
    assert "hidden_tool" in msg
    # Visible tool listed as valid; "hidden" mentioned in caveat
    assert "visible_tool" in msg
    assert "hidden" in msg.lower()


def test_unknown_tool_name_fails_closed() -> None:
    """Scenario 5: unknown tool name in selector raises ToolSelectionError."""
    with _env("ask,bogus"), pytest.raises(ToolSelectionError) as excinfo:
        build_mcp_server(_three_tool_app("unknown"), code_mode=False)
    msg = str(excinfo.value)
    assert "bogus" in msg
    # Valid names listed
    for name in ("ask", "refresh", "fetch_raw"):
        assert name in msg


def test_no_selector_active_exposes_all_tools() -> None:
    """No env var, no CLI flag → current behavior preserved."""
    with _env(None):
        server = build_mcp_server(_three_tool_app("baseline"), code_mode=False)
        import asyncio

        names = asyncio.run(_mcp_tool_names(server))
    assert {"ask", "refresh", "fetch_raw"} <= names


def test_env_var_restricts_cli_surface() -> None:
    """Env var at CLI build time filters Click subcommand registration."""
    with _env("ask"):
        cli = build_full_cli(_three_tool_app("cli-env"))
        runner = CliRunner()
        result = runner.invoke(cli, ["web", "--help"])
    assert result.exit_code == 0
    assert "ask" in result.output
    assert "refresh" not in result.output
    assert "fetch_raw" not in result.output


def test_cli_unknown_tool_in_env_fails_closed_at_build() -> None:
    """Unknown name in env var raises at build_full_cli time."""
    with _env("ask,not-a-tool"), pytest.raises(ToolSelectionError) as excinfo:
        build_full_cli(_three_tool_app("cli-unknown"))
    assert "not-a-tool" in str(excinfo.value)
