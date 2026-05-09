from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from a2kit.packages.mcp.server import build_mcp_server


def __getattr__(name: str) -> Any:
    if name == "build_mcp_server":
        from a2kit.packages.mcp.server import build_mcp_server

        return build_mcp_server
    raise AttributeError(f"module 'a2kit.packages.mcp' has no attribute {name!r}")


__all__ = ["build_mcp_server"]
