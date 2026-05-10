"""Elicitation example — CLI (stdin) and MCP (in-memory test client) parity.

Gherkin-flavored scenarios covered:

  Scenario: CLI user provides a username via stdin
    Given the elicitation example app
    When `users greet` is invoked with stdin "alice"
    Then the response contains "hello alice"

  Scenario: CLI user declines the elicitation
    When stdin reads "--decline"
    Then the response action is "decline"

  Scenario: MCP client provides a username
    Given an MCP client with an elicitation_handler returning "bob"
    When `users.greet` is called via tools/call
    Then the response contains "hello bob"
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from click.testing import CliRunner
from fastmcp import Client

from a2kit.packages.cli.builder import build_full_cli
from a2kit.packages.mcp.server import build_mcp_server
from examples.elicitation.server import app


# --- CLI path: stdin feeds the elicit() prompt --- #


def test_cli_accepts_username_from_stdin() -> None:
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["users", "greet"], input="alice\n")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.splitlines()[-1])
    assert payload == {"status": "ok", "greeting": "hello alice"}


def test_cli_decline_returns_no_name_status() -> None:
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["users", "greet"], input="--decline\n")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.splitlines()[-1])
    assert payload == {"status": "no name", "kind": "decline"}


# --- MCP path: in-memory FastMCP test client --- #


async def _call_greet_with_handler(handler: Any) -> Any:
    server = build_mcp_server(app)
    async with Client(transport=server, elicitation_handler=handler) as client:
        return await client.call_tool("greet", {})


def test_mcp_path_accepts_username_via_client_handler() -> None:
    async def handler(message: str, response_type: Any, params: Any, context: Any) -> Any:  # noqa: ARG001
        return "bob"

    result = asyncio.run(_call_greet_with_handler(handler))
    payload = result.data if hasattr(result, "data") else result.structured_content
    assert payload == {"status": "ok", "greeting": "hello bob"}
