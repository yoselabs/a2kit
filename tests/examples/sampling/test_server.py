"""Sampling example — MCP path returns a summary; CLI path raises ``MCPOnlyError``.

Gherkin-flavored scenarios:

  Scenario: MCP client provides a summary via sampling_handler
    Given an MCP client with a sampling_handler returning "It is a test."
    When `text.summarize` is called with text="long text..."
    Then the response.summary is "It is a test."

  Scenario: CLI invocation fails with MCPOnlyError
    When `text summarize --text ...` is invoked over CLI
    Then the runner exits non-zero
    And stderr mentions "requires MCP transport"
"""

from __future__ import annotations

import asyncio
from typing import Any

from click.testing import CliRunner
from fastmcp import Client
from mcp import types as mcp_types

from a2kit.packages.cli.builder import build_full_cli
from a2kit.packages.mcp.server import build_mcp_server
from examples.sampling.server import app


# --- MCP path --- #


async def _call_summarize_with_handler(handler: Any, text: str) -> Any:
    server = build_mcp_server(app)
    async with Client(transport=server, sampling_handler=handler) as client:
        return await client.call_tool("text_summarize", {"text": text})


def test_mcp_path_returns_summary() -> None:
    async def handler(messages: Any, params: Any, context: Any) -> str:  # noqa: ARG001
        return "It is a test."

    result = asyncio.run(_call_summarize_with_handler(handler, "very long text..."))
    payload = result.data if hasattr(result, "data") else result.structured_content
    assert payload == {"summary": "It is a test."}


# --- CLI path --- #


def test_cli_path_raises_mcp_only_error() -> None:
    cli = build_full_cli(app)
    result = CliRunner().invoke(
        cli,
        ["text", "summarize", "--text", "hello world"],
        catch_exceptions=True,
    )
    # Exit code is non-zero (the tool body raised).
    assert result.exit_code != 0
    # The MCPOnlyError message is surfaced on stderr (or the click runner output).
    combined = (result.output or "") + (str(result.exception) if result.exception else "")
    assert "MCP transport" in combined or "MCPOnlyError" in combined


# Reference unused mcp_types so the import is non-trivial — keeps lint quiet
# while leaving the symbol available if future scenarios expand handler shapes.
_ = mcp_types
