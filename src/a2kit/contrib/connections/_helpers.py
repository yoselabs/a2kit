"""Connection-aware helpers — public re-exports for contrib consumers.

These are the same functions the v0.12 tool decorator imports from
`a2kit.tools._connection` (private). Re-exported here under public names so
that:

  * `a2kit.contrib.connections` is a self-contained surface — phase 6 can
    move the implementations without touching every import site;
  * test code and external consumers (third-party Routers in `contrib.*`)
    have one canonical path.

The legacy private paths still resolve so the v0.12 internal call sites
keep working through phase 6.
"""

from __future__ import annotations

from a2kit.tools._connection import (
    _lookup_connection_async,
    _resolve_connection_key,
    _resolve_info_strings,
)

# Public, explicit aliases — the underscore-prefixed originals stay because
# the tool decorator imports them today. Phase 6 swaps the call sites and
# deletes the originals.
lookup_connection_async = _lookup_connection_async
resolve_connection_key = _resolve_connection_key
resolve_info_strings = _resolve_info_strings


__all__ = [
    "lookup_connection_async",
    "resolve_connection_key",
    "resolve_info_strings",
]
