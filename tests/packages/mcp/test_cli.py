"""``serve`` Click command basic dispatch."""

from __future__ import annotations

from unittest.mock import patch

import click
from click.testing import CliRunner

import a2kit
from a2kit.packages.cli.app_ctx import _APP_CTX
from a2kit.packages.mcp.cli import serve_command


def test_serve_help_lists_options() -> None:
    runner = CliRunner()
    result = runner.invoke(serve_command, ["--help"])
    assert result.exit_code == 0
    assert "--transport" in result.output
    assert "stdio" in result.output
    assert "http" in result.output
    assert "--host" in result.output
    assert "--port" in result.output


def test_serve_dispatches_stdio_transport() -> None:
    app = a2kit.App("test")
    token = _APP_CTX.set(app)
    try:
        runner = CliRunner()
        with patch("a2kit.packages.mcp.server.FastMCP") as mock_fastmcp:
            instance = mock_fastmcp.return_value
            instance.add_tool.return_value = None
            instance.add_middleware.return_value = None
            instance.run.return_value = None
            result = runner.invoke(serve_command, [])
        assert result.exit_code == 0, result.output
        instance.run.assert_called_once_with(transport="stdio")
    finally:
        _APP_CTX.reset(token)


def test_serve_dispatches_http_transport() -> None:
    app = a2kit.App("test")
    token = _APP_CTX.set(app)
    try:
        runner = CliRunner()
        with patch("a2kit.packages.mcp.server.FastMCP") as mock_fastmcp:
            instance = mock_fastmcp.return_value
            instance.add_tool.return_value = None
            instance.add_middleware.return_value = None
            instance.run.return_value = None
            result = runner.invoke(serve_command, ["--transport", "http", "--host", "0.0.0.0", "--port", "9999"])
        assert result.exit_code == 0, result.output
        instance.run.assert_called_once_with(transport="http", host="0.0.0.0", port=9999)
    finally:
        _APP_CTX.reset(token)


def test_app_ctx_is_a_contextvar() -> None:
    from contextvars import ContextVar

    assert isinstance(_APP_CTX, ContextVar)
    assert _APP_CTX.name == "_APP_CTX"


def test_serve_command_is_click_command() -> None:
    assert isinstance(serve_command, click.Command)
    assert serve_command.name == "serve"
