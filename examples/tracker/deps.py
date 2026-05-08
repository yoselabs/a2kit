"""Dependency wiring for the tracker example.

The Annotated[Conn, Depends(get_conn)] idiom captures the `get_conn`
reference at decoration time (when `routers.py` is imported). To keep
the routers decoupled from the App, we expose a stable module-level
`get_conn` that delegates to a slot the composition root fills in.

`server.py` wires this slot via `set_get_conn(get_conn_factory(app, ...))`.
Test code can override directly: `app.dependency_overrides[get_conn] = fake`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .connection import TrackerConn

_impl: Callable[..., Awaitable[TrackerConn]] | None = None


async def get_conn(*, connection: str) -> TrackerConn:
    """Resolve the saved tracker connection by key.

    Wired to the actual factory by `server.main()` via `set_get_conn`.
    """
    if _impl is None:  # pragma: no cover — composition root always wires this
        msg = "tracker get_conn is not wired; call set_get_conn() first"
        raise RuntimeError(msg)
    return await _impl(connection=connection)


def set_get_conn(fn: Callable[..., Awaitable[TrackerConn]]) -> None:
    """Wire the real factory in (called from the composition root)."""
    global _impl  # noqa: PLW0603 — slot pattern
    _impl = fn
