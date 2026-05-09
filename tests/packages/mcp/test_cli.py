"""``serve`` Click command basic dispatch."""

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


def test_serve_dispatches_http_transport() -> None:
    app = a2kit.App("test")
    cmd = build_serve_command(app)
    runner = CliRunner()
    with patch("a2kit.packages.mcp.server.FastMCP") as mock_fastmcp:
        instance = mock_fastmcp.return_value
        instance.add_tool.return_value = None
        instance.add_middleware.return_value = None
        instance.run.return_value = None
        result = runner.invoke(cmd, ["--transport", "http", "--host", "0.0.0.0", "--port", "9999"])
    assert result.exit_code == 0, result.output
    instance.run.assert_called_once_with(transport="http", host="0.0.0.0", port=9999)


def test_build_serve_command_returns_click_command() -> None:
    cmd = build_serve_command(a2kit.App("test"))
    assert isinstance(cmd, click.Command)
    assert cmd.name == "serve"
