"""Connection type — the typed shape of one saved tracker endpoint.

The connection IS the resource handle. `TrackerConn` carries `db_path`
(a JSONL file on disk) and an optional `token`. Tools receive a fully
loaded `TrackerConn` via typed DI: `*, conn: TrackerConn`.

`token` demonstrates token resolution: any string of the form `${ENV_VAR}`
or `op://...` is auto-resolved by the kit before reaching tool bodies. A
plain string passes through unchanged.
"""

from __future__ import annotations

import a2kit


class TrackerConn(a2kit.ConnectionInfo):
    """One saved tracker endpoint.

    Each saved connection points at its own JSONL file, so different
    saved keys (`prod`, `staging`, `personal`) get isolated data.

    Fields:
        db_path:    JSONL file path (string — TOML doesn't serialise Path).
        token:      Optional auth token. Supports `${ENV}` / `op://` syntax.
        read_only:  If True, write tools refuse to mutate this connection.
    """

    db_path: str
    token: str = ""
    read_only: bool = False
