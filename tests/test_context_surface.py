"""Inventory test — every public ``fastmcp.Context`` method has a story on the CLI stub.

Either the method is implemented on :class:`StderrToolContext` (LDD primitives,
state, file:// resources, primitive elicitation), or it appears in the
documented ``MCP_ONLY`` allowlist (sampling, prompts, roots, notifications,
session-shaped attrs that don't make sense client-side).

This is the failing test promised in ``tasks.md`` 1.3 / 5.8 — keeps the stub
honest as fastmcp evolves.
"""

from __future__ import annotations

from fastmcp import Context

from a2kit.packages.cli.context import StderrToolContext

# Documented MCP-only surface — methods/attrs that have no CLI semantics by design.
# Stub may either raise MCPOnlyError on call or simply not implement
# (e.g. server/session-shaped properties).
MCP_ONLY: frozenset[str] = frozenset(
    {
        # LLM sampling — needs MCP client
        "sample",
        "sample_step",
        # Server-managed registries
        "list_resources",
        "list_prompts",
        "get_prompt",
        "list_roots",
        # Notifications protocol
        "send_notification",
        "close_sse_stream",
        # Session/transport-shaped properties — read-only attrs, not methods
        "client_id",
        "client_supports_extension",
        "fastmcp",
        "is_background_task",
        "lifespan_context",
        "origin_request_id",
        "request_context",
        "request_id",
        "session",
        "session_id",
        "task_id",
        "transport",
        # Component visibility — server-side admin
        "disable_components",
        "enable_components",
        "reset_visibility",
    }
)


def test_stub_covers_fastmcp_context_surface() -> None:
    """Every public ``fastmcp.Context`` member is on the stub or in MCP_ONLY."""
    public = {m for m in dir(Context) if not m.startswith("_")}
    stub_attrs = {m for m in dir(StderrToolContext) if not m.startswith("_")}
    missing = public - stub_attrs - MCP_ONLY
    assert not missing, (
        f"fastmcp.Context exposes {missing!r} which is neither implemented on "
        f"StderrToolContext nor allowlisted in MCP_ONLY. Either implement it "
        f"or add it to MCP_ONLY with a comment explaining why."
    )
