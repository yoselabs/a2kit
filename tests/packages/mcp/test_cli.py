"""``serve`` Click command — transport dispatch and surface-selection flags."""

from __future__ import annotations

from unittest.mock import patch

import click
from click.testing import CliRunner

import a2kit
from a2kit.packages.mcp.cli import build_serve_command


def test_serve_help_lists_options() -> None:
    cmd = build_serve_command(a2kit.App("test"))
    runner = CliRunner()
    result = runner.invoke(cmd, ["--help"])
    assert result.exit_code == 0
    assert "--transport" in result.output
    assert "stdio" in result.output
    assert "http" in result.output
    assert "--host" in result.output
    assert "--port" in result.output
    assert "--mcp-only" in result.output
    assert "--rest-only" in result.output


def test_serve_dispatches_stdio_transport() -> None:
    app = a2kit.App("test")
    cmd = build_serve_command(app)
    runner = CliRunner()
    with patch("a2kit.packages.mcp.server.FastMCP") as mock_fastmcp:
        instance = mock_fastmcp.return_value
        instance.add_tool.return_value = None
        instance.add_middleware.return_value = None
        instance.run.return_value = None
        result = runner.invoke(cmd, [])
    assert result.exit_code == 0, result.output
    instance.run.assert_called_once_with(transport="stdio")


def test_serve_stdio_accepts_mcp_only_as_noop() -> None:
    """``--mcp-only`` on stdio is redundant but accepted — stdio is MCP-only."""
    cmd = build_serve_command(a2kit.App("test"))
    runner = CliRunner()
    with patch("a2kit.packages.mcp.server.FastMCP") as mock_fastmcp:
        instance = mock_fastmcp.return_value
        instance.add_tool.return_value = None
        instance.add_middleware.return_value = None
        instance.run.return_value = None
        result = runner.invoke(cmd, ["--mcp-only"])
    assert result.exit_code == 0, result.output
    instance.run.assert_called_once_with(transport="stdio")


def test_serve_rest_only_with_stdio_is_rejected() -> None:
    """REST cannot ride a single-protocol stdio pipe."""
    cmd = build_serve_command(a2kit.App("test"))
    result = CliRunner().invoke(cmd, ["--rest-only"])
    assert result.exit_code != 0
    assert "stdio" in result.output.lower()
    assert "rest" in result.output.lower()


def test_serve_mcp_only_and_rest_only_together_is_rejected() -> None:
    cmd = build_serve_command(a2kit.App("test"))
    result = CliRunner().invoke(cmd, ["--transport", "http", "--mcp-only", "--rest-only"])
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output.lower()


def test_serve_http_default_mounts_both_surfaces() -> None:
    app = a2kit.App("test")
    cmd = build_serve_command(app)
    runner = CliRunner()
    with (
        patch("a2kit.packages.serve.build_parent_app") as mock_build,
        patch("uvicorn.run") as mock_run,
    ):
        result = runner.invoke(cmd, ["--transport", "http", "--host", "0.0.0.0", "--port", "9999"])
    assert result.exit_code == 0, result.output
    mock_build.assert_called_once()
    assert mock_build.call_args.kwargs == {"mcp": True, "rest": True}
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs == {"host": "0.0.0.0", "port": 9999}


def test_serve_http_mcp_only_mounts_mcp_alone() -> None:
    cmd = build_serve_command(a2kit.App("test"))
    runner = CliRunner()
    with (
        patch("a2kit.packages.serve.build_parent_app") as mock_build,
        patch("uvicorn.run"),
    ):
        result = runner.invoke(cmd, ["--transport", "http", "--mcp-only"])
    assert result.exit_code == 0, result.output
    assert mock_build.call_args.kwargs == {"mcp": True, "rest": False}


def test_serve_http_rest_only_mounts_rest_alone() -> None:
    cmd = build_serve_command(a2kit.App("test"))
    runner = CliRunner()
    with (
        patch("a2kit.packages.serve.build_parent_app") as mock_build,
        patch("uvicorn.run"),
    ):
        result = runner.invoke(cmd, ["--transport", "http", "--rest-only"])
    assert result.exit_code == 0, result.output
    assert mock_build.call_args.kwargs == {"mcp": False, "rest": True}


def test_build_serve_command_returns_click_command() -> None:
    cmd = build_serve_command(a2kit.App("test"))
    assert isinstance(cmd, click.Command)
    assert cmd.name == "serve"
