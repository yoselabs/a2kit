"""McpConfig.instructions threads into the FastMCP server (friction #6)."""

from __future__ import annotations

import a2kit
from a2kit.config import A2kitConfig, McpConfig
from a2kit.packages.mcp.server import build_mcp_server

_GUIDANCE = "Use entity_* for memory ops."


def _app_with_instructions(text: str | None) -> a2kit.App:
    cfg = A2kitConfig(mcp=McpConfig(instructions=text)) if text is not None else A2kitConfig()
    return a2kit.App("memo", config=cfg)


def test_mcp_config_has_instructions() -> None:
    cfg = McpConfig(instructions=_GUIDANCE)
    assert cfg.instructions == _GUIDANCE


def test_build_threads_instructions() -> None:
    server = build_mcp_server(_app_with_instructions(_GUIDANCE))
    assert server.instructions == _GUIDANCE


def test_default_none_preserves_today() -> None:
    """No instructions set → FastMCP default (None) preserved."""
    default_server = build_mcp_server(a2kit.App("memo"))
    assert default_server.instructions is None


def test_caller_fastmcp_kwarg_wins() -> None:
    """An explicit fastmcp_kwargs['instructions'] is the escape hatch and wins."""
    server = build_mcp_server(_app_with_instructions(_GUIDANCE), instructions="override")
    assert server.instructions == "override"
