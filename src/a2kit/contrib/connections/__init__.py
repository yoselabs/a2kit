"""`a2kit.contrib.connections` — connection-aware wiring as a contrib module.

Per the v0.13 plan ("Pull connections out of core (the big one)"), all
connection vocabulary moves out of `a2kit.tools._decorator` and into this
package. The core decorator gains a generic Provider-resolution pass; the
connection store, the `login` / `logout` / `connections list` tools, the
`WriteNotAllowed` enforcement, and the `--register` CLI subcommand all live
here.

v0.13 phase 3 status (incremental):

- Helpers (`_resolve_connection_key`, `_lookup_connection_async`,
  `_resolve_info_strings`) re-exported from `a2kit.tools._connection` so
  contrib code can import them from one canonical place. The legacy import
  paths still work for v0.12 tests; they are scheduled to disappear in
  v0.14.
- `WriteEnforce` middleware available for routers that opt into the new
  middleware-chain wiring. The default tool decorator path still enforces
  inline (kept for v0.12 test parity).
- `make(conn_type)` factory matches the locked v0.13 surface
  (`app.use(*connections.make(TodoConn))`); today it routes back to
  `app.connect(conn_type)` for compatibility, so authors can adopt the new
  call shape without waiting for the underlying SubApp/mount work.

Phase 6 deletes the legacy paths; the contrib package then becomes the
sole connection surface.
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
    "make",
    "resolve_connection_key",
    "resolve_info_strings",
    "write_enforce_factory",
]


def make(conn_type: type, *, config_dir: object = None) -> object:
    """v0.13 factory shape: `app.use(*connections.make(TodoConn))`.

    v0.13 phase 3 (incremental) returns a tuple holding only the connection
    type + config_dir; `App.use` doesn't yet accept this form, so authors
    keep using `app.connect(conn_type)` (which has identical effect). Phase
    6 swaps the implementation in place once the SubApp / mount API lands.
    """
    return (conn_type, config_dir)
