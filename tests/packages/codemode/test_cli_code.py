"""BDD: the global `code` CLI subcommand (code-execution-surface §6)."""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

import a2kit
from a2kit.packages.cli.builder import build_full_cli


def test_code_subcommand_runs_source(gate_app: a2kit.App) -> None:
    """`<app> code '<source>'` runs the source in the sandbox and prints the result."""
    cli = build_full_cli(gate_app)
    result = CliRunner().invoke(cli, ["code", 'await call_tool("ping", {})'])
    assert result.exit_code == 0, result.output
    assert "pong" in result.output


def test_code_subcommand_gates_destructive(gate_app: a2kit.App) -> None:
    """The destructive gate applies to the CLI surface identically to MCP."""
    cli = build_full_cli(gate_app)
    result = CliRunner().invoke(cli, ["code", 'await call_tool("wipe", {})'])
    assert result.exit_code != 0


def test_code_subcommand_allow_destructive(gate_app: a2kit.App) -> None:
    """`--allow-destructive` opens destructive tools to the CLI sandbox."""
    cli = build_full_cli(gate_app)
    result = CliRunner().invoke(cli, ["code", "--allow-destructive", 'await call_tool("wipe", {})'])
    assert result.exit_code == 0, result.output
    assert "wiped" in result.output


def test_code_subcommand_listed_in_help(gate_app: a2kit.App) -> None:
    """The `code` subcommand appears in the top-level CLI help."""
    cli = build_full_cli(gate_app)
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "code" in result.output


def test_code_subcommand_absent_without_extra(gate_app: a2kit.App, monkeypatch: pytest.MonkeyPatch) -> None:
    """A lean install without the `a2kit[code-mode]` extra omits `code`."""
    import importlib.util

    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, package: str | None = None) -> object:
        if name == "pydantic_monty":
            return None
        return real_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    cli = build_full_cli(gate_app)
    assert isinstance(cli, click.Group)
    assert "code" not in cli.commands
    assert "serve" in cli.commands
