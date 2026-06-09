"""Public surface for ``a2kit.packages.log`` — THE author emission surface.

Lets tools import the discoverable surface as
``from a2kit.log import info, debug, warning, error``. Implementation lives in
``a2kit.packages.log`` to keep the canonical layout under ``packages/``.

``current_surface`` / ``current_surface_client_id`` are the read accessors for
the dispatching surface's identity (ctx-surface-identity, ADR 0028): a tool
body calls ``a2kit.log.current_surface()`` to learn whether it was invoked over
MCP, ``/api``, or the CLI. Both return None outside a dispatch.
"""

from __future__ import annotations

from a2kit.packages.log import (
    current_surface,
    current_surface_client_id,
    debug,
    error,
    info,
    warning,
)

__all__ = [
    "current_surface",
    "current_surface_client_id",
    "debug",
    "error",
    "info",
    "warning",
]
