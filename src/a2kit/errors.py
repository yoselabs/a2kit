"""Deprecated — use `a2kit.enrichers` instead.

v0.11 renamed `a2kit.errors` → `a2kit.enrichers` to clarify the library's
vocabulary (`a2kit.exceptions` is exception *classes*; this module is
enrichment *functions*). This shim re-exports everything from `a2kit.enrichers`
plus the v0.10-era `ConnectionInfoLike` / `ConnectionStoreLike` Protocols
(canonical home is now `a2kit.connections`).

The shim is scheduled for removal in **v0.13**. Update imports to
`from a2kit.enrichers import ...` (or `from a2kit.connections import ...`
for the Protocols).
"""

from __future__ import annotations

import warnings as _warnings

# Re-exports — keep `from a2kit.errors import EnricherFn, chain, ...` working.
from a2kit.connections import ConnectionInfoLike, ConnectionStoreLike
from a2kit.enrichers import EnricherFn, chain, connection_enricher

_warnings.warn(
    "`a2kit.errors` was renamed to `a2kit.enrichers` in v0.11 and will be removed in v0.13. "
    "Update imports to `from a2kit.enrichers import ...` (or `from a2kit.connections import ...` "
    "for `ConnectionInfoLike` / `ConnectionStoreLike`).",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ConnectionInfoLike",
    "ConnectionStoreLike",
    "EnricherFn",
    "chain",
    "connection_enricher",
]
