"""get_conn_factory — Depends-compatible connection factory for tool DI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, cast

from a2kit.packages.connections.config import ConnectionConfig
from a2kit.packages.connections.exceptions import ConnectionNotFound

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from a2kit.app import App

C = TypeVar("C", bound=ConnectionConfig)


def _resolve_connection_key(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    msg = f"connection param must be str|tuple|list, got {type(value).__name__}"
    raise TypeError(msg)


def get_conn_factory(app: App, conn_type: type[C]) -> Callable[..., Awaitable[C]]:
    """Return a `Depends(get_conn)` factory bound to `app`'s store for `conn_type`."""
    store = app.get_store(conn_type)

    async def get_conn(*, connection: str | tuple[str, ...] | list[str]) -> C:
        key = _resolve_connection_key(connection)
        if store is None:
            raise ConnectionNotFound(key)
        info = await store.load(key)
        return cast("C", info)

    return get_conn


__all__ = ["get_conn_factory"]
