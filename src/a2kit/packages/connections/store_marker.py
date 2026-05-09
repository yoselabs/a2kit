"""``a2kit.Store[ConnT]`` — type-system anchor for ``Depends(StoreT)`` injection.

Stores wrap one connection. The runtime needs to know *which* connection
class to load before instantiating the store; this marker exposes that
binding via the standard `Generic` machinery so type checkers see it
natively.

Authors can also (or instead) declare ``conn_type: type[ConnT] = TrackerConn``
as a class attribute. The signature resolver checks the attribute first,
then falls back to the Generic parameter — both shapes work; pick whichever
reads cleaner.

This module ships zero behavior. It is a marker class plus a lookup helper.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar, get_args, get_origin

ConnT = TypeVar("ConnT")


class Store(Generic[ConnT]):
    """Marker base for store classes. ``class TrackerStore(Store[TrackerConn]):``."""


def store_conn_type(store_cls: type) -> type | None:
    """Resolve the connection type a store class wraps.

    Order of checks:
    1. ``store_cls.conn_type`` class attribute (explicit, retrofit-friendly).
    2. ``Store[ConnT]`` Generic parameter on ``__orig_bases__``.

    Returns ``None`` if neither marker is present.
    """
    explicit = getattr(store_cls, "conn_type", None)
    if isinstance(explicit, type):
        return explicit
    for base in getattr(store_cls, "__orig_bases__", ()):
        if get_origin(base) is None:
            continue
        args = get_args(base)
        if not args:
            continue
        candidate: Any = args[0]
        if isinstance(candidate, type):
            return candidate
    return None


__all__ = ["Store", "store_conn_type"]
