"""`a2kit.contrib.connections` — connection-aware wiring as a contrib module.

The connection vocabulary lives outside the core `@a2kit.tool` decorator.
This package owns:

- `get_conn_factory(app, conn_type)` — the v0.15 idiom for connection
  injection. Returns a `Depends`-shaped factory that resolves the
  current connection from the App's `ConnectionStore`.
- `write_enforce_factory()` — middleware that raises `WriteNotAllowed`
  when a write tool runs against a read-only connection.
- `resolve_connection_key`, `lookup_connection_async`,
  `resolve_info_strings` — re-exports of the same helpers consumed by
  `get_conn_factory`, surfaced here as the public path for third-party
  factories.
"""

from __future__ import annotations

from a2kit.contrib.connections._factory import get_conn_factory
from a2kit.contrib.connections._helpers import (
    lookup_connection_async,
    resolve_connection_key,
    resolve_info_strings,
)
from a2kit.contrib.connections._middleware import write_enforce_factory

__all__ = [
    "get_conn_factory",
    "lookup_connection_async",
    "resolve_connection_key",
    "resolve_info_strings",
    "write_enforce_factory",
]
