from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from a2kit.packages.mcp.server import build_mcp_server


# NOTE: Surface registration is no longer performed at import time. Per
# `bootstrap-surfaces-explicit`, surfaces are composed explicitly at
# `runtime.build()` time from its `surfaces=` tuple (defaulting to the
# bundled `McpSurface` + `ApiSurface` pair). Importing this package has
# zero side effects on any registry.


def __getattr__(name: str) -> Any:
    if name == "build_mcp_server":
        from a2kit.packages.mcp.server import build_mcp_server

        return build_mcp_server
    raise AttributeError(f"module 'a2kit.packages.mcp' has no attribute {name!r}")


__all__ = ["build_mcp_server"]
