"""`get_conn` factory — the v0.15 idiom for connection injection.

v0.14 still ships the legacy `*, info: ConnT` autodetect path inside the
core tool decorator. v0.15 deletes that path; this module is the
replacement.

Usage:

    app = a2kit.App("tracker")
    app.connect(TrackerConn)
    get_conn = a2kit.contrib.connections.get_conn_factory(app, TrackerConn)

    @MyRouter.read()
    async def get_task(*, conn: Annotated[TrackerConn, Depends(get_conn)],
                       task_id: str) -> Task: ...

The factory reads the runtime `connection: str` kwarg from `call_ctx`
(forwarded by `resolve_annotated_deps`) and looks up the connection from
the `ConnectionStore` registered on the App.

Tests override via `app.dependency_overrides[get_conn] = fake_get_conn`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, cast

from a2kit.connections import ConnectionConfig
from a2kit.contrib.connections._helpers import (
    lookup_connection_async,
    resolve_connection_key,
    resolve_info_strings,
)
from a2kit.exceptions import ConnectionNotFound

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from a2kit.app import App

C = TypeVar("C", bound=ConnectionConfig)


def get_conn_factory(app: App, conn_type: type[C]) -> Callable[..., Awaitable[C]]:
    """Return a `get_conn` factory bound to `app`'s store for `conn_type`.

    The returned callable matches the `Depends(...)` factory shape —
    declares `connection: str` as a kwonly param so the resolver forwards
    the call-site value.

    Raises ``ValueError`` at factory-build time if `conn_type` isn't
    registered on the App. Raises ``ConnectionNotFound`` at call time if
    the resolved key has no saved connection.
    """
    store = next((s for s in app._stores if s.connection_class is conn_type), None)  # noqa: SLF001 — App composition root, contrib helper
    if store is None:
        msg = f"App has no ConnectionStore for {conn_type.__name__}. Call `app.connect({conn_type.__name__})` first."
        raise ValueError(msg)

    async def get_conn(*, connection: str | tuple[str, ...] | list[str]) -> C:
        key = resolve_connection_key(connection)
        info = await lookup_connection_async(key, store)
        if info is None:
            raise ConnectionNotFound(key)
        return cast("C", resolve_info_strings(info, registry=None))

    return get_conn


__all__ = ["get_conn_factory"]
