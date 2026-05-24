from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.packages.dispatch import SURFACE_REGISTRY
from a2kit.packages.mcp.surface import McpSurface

if TYPE_CHECKING:
    from a2kit.packages.mcp.server import build_mcp_server


# Self-register the MCP Surface at front-door import. Guard with a
# membership check so re-imports within one interpreter remain
# idempotent (the registry rejects duplicates by `ValueError`).
if "mcp" not in SURFACE_REGISTRY:
    SURFACE_REGISTRY.register_surface(McpSurface())


def __getattr__(name: str) -> Any:
    if name == "build_mcp_server":
        from a2kit.packages.mcp.server import build_mcp_server

        return build_mcp_server
    raise AttributeError(f"module 'a2kit.packages.mcp' has no attribute {name!r}")


__all__ = ["build_mcp_server"]
