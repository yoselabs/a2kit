"""Stable identity for ``Depends(get_conn)`` in the tracker tools.

The composition root binds the real factory via ``app.use_factory(...)``.
This module exists so router-level ``Depends(get_conn)`` references resolve
to a single canonical callable identity regardless of which factory the App
is configured with.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import TrackerConn


async def get_conn(*, connection: str) -> TrackerConn:
    """Stub identity. The real factory is bound via ``app.use_factory``.

    If invoked unbound, raises — composition root forgot to wire the App.
    """
    msg = (
        "tracker get_conn is not bound; the composition root must call `app.use_factory(get_conn_factory(app, TrackerConn), as_=get_conn)`."
    )
    raise RuntimeError(msg)
