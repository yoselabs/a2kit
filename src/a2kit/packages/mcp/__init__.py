from __future__ import annotations

from typing import TYPE_CHECKING

from a2kit._lazy_module import lazy_attr

if TYPE_CHECKING:
    from a2kit.packages.mcp.server import build_mcp_server


# NOTE: Surface registration is no longer performed at import time. Per
# `bootstrap-surfaces-explicit`, surfaces are composed explicitly at
# `runtime.build()` time from its `surfaces=` tuple (defaulting to the
# bundled `McpSurface` + `ApiSurface` pair). Importing this package has
# zero side effects on any registry.


_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "build_mcp_server": ("a2kit.packages.mcp.server", "build_mcp_server"),
}

__getattr__ = lazy_attr(__name__, _LAZY_ATTRS)
del lazy_attr


__all__ = ["build_mcp_server"]
