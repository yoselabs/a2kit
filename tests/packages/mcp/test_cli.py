"""``serve`` Click command — transport dispatch.

Substrate mounts on ``--transport=http`` are determined by App
registrations (auto-mount per ``add-multi-surface``). The legacy
``--mcp-only`` / ``--rest-only`` flags are removed; ``--select 'surface=...'``
is the documented surface-narrowing path (lands with ``add-tool-select``).
"""

from __future__ import annotations

from unittest.mock import patch

import click
from click.testing import CliRunner

from a2kit.packages.mcp.cli import build_serve_command
from a2kit.testing import app_of


def test_serve_help_lists_options() -> None:
    cmd = build_serve_command(app_of("test"))
    runner = CliRunner()
    result = runner.invoke(cmd, ["--help"])
    assert result.exit_code == 0
    assert "--transport" in result.output
    assert "stdio" in result.output
    assert "http" in result.output
    assert "--host" in result.output
    assert "--port" in result.output


def test_serve_help_does_not_advertise_removed_flags() -> None:
    """``--mcp-only`` / ``--rest-only`` are gone post add-multi-surface."""
    cmd = build_serve_command(app_of("test"))
    result = CliRunner().invoke(cmd, ["--help"])
    assert "--mcp-only" not in result.output
    assert "--rest-only" not in result.output


def test_serve_dispatches_stdio_transport() -> None:
    app = app_of("test")
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


def test_serve_rejects_unknown_flag() -> None:
    """The removed ``--mcp-only`` flag now raises a Click usage error."""
    cmd = build_serve_command(app_of("test"))
    result = CliRunner().invoke(cmd, ["--mcp-only"])
    assert result.exit_code != 0
    assert "no such option" in result.output.lower() or "unrecognized" in result.output.lower()


def test_serve_http_invokes_build_parent_app_kwargless() -> None:
    """The HTTP path calls ``build_parent_app(app)`` with no surface kwargs."""
    app = app_of("test")

    # Need at least one registration so build_parent_app doesn't ValueError
    # before uvicorn.run is invoked — give the app one @app.api route.
    @app.api.get("/probe")
    async def _p() -> dict[str, str]:
        return {"ok": "1"}

    cmd = build_serve_command(app)
    runner = CliRunner()
    with (
        patch("a2kit.packages.serve.build_parent_app") as mock_build,
        patch("uvicorn.run") as mock_run,
    ):
        result = runner.invoke(cmd, ["--transport", "http", "--host", "0.0.0.0", "--port", "9999"])
    assert result.exit_code == 0, result.output
    mock_build.assert_called_once()
    # No mcp= / rest= kwargs; the App alone is passed positionally.
    assert mock_build.call_args.kwargs == {}
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs == {"host": "0.0.0.0", "port": 9999}


def test_build_serve_command_returns_click_command() -> None:
    cmd = build_serve_command(app_of("test"))
    assert isinstance(cmd, click.Command)
    assert cmd.name == "serve"
