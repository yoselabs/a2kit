"""Connection lookup + key coercion.

Sync and async paths share the same store contract — `_lookup_connection_sync`
drives the async coroutine via anyio's 3-tier drain.
"""

from __future__ import annotations

import concurrent.futures
from typing import TYPE_CHECKING, Any

import anyio
import anyio.from_thread

from a2kit.exceptions import ConnectionNotFound
from a2kit.tokens import resolve_token

if TYPE_CHECKING:
    from a2kit.connections import ConnectionInfo, ConnectionStore
    from a2kit.tokens import ResolverRegistry


def _resolve_connection_key(value: Any) -> tuple[str, ...]:
    """Coerce a connection arg into a tuple-key. Supports str / tuple / list."""
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    msg = f"connection param must be str|tuple|list, got {type(value).__name__}"
    raise TypeError(msg)


async def _lookup_connection_async(
    key: tuple[str, ...],
    store: ConnectionStore[Any] | None,
) -> Any:
    """Look up a connection from the (now async) store."""
    if store is None:
        raise ConnectionNotFound(key)
    return await store.load(key)


def _lookup_connection_sync(
    key: tuple[str, ...],
    store: ConnectionStore[Any] | None,
) -> Any:
    """Sync-context wrapper around `_lookup_connection_async`.

    3-tier drain via anyio: `from_thread.run` (worker thread under a host
    loop) → `anyio.run` (no loop in scope) → fresh worker thread (loop on
    this thread). Each tier mints a fresh coroutine since coroutines are
    single-use.
    """
    if store is None:
        raise ConnectionNotFound(key)

    async def _run() -> Any:
        return await store.load(key)

    try:
        return anyio.from_thread.run(_run)
    except RuntimeError:
        pass
    try:
        return anyio.run(_run)
    except RuntimeError:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(anyio.run, _run).result()


def _resolve_info_strings(info: ConnectionInfo, registry: ResolverRegistry | None) -> ConnectionInfo:
    """Return a copy of `info` with every str field resolved through `registry`.

    Pydantic v2 frozen models support `.model_copy(update={...})`. We collect
    the str-typed fields, resolve each, and produce one new instance.
    """
    update: dict[str, str] = {}
    for name, value in info.model_dump().items():
        if isinstance(value, str) and name != "key":
            update[name] = resolve_token(value, registry=registry)
    if not update:
        return info
    return info.model_copy(update=update)


__all__ = [
    "_lookup_connection_async",
    "_lookup_connection_sync",
    "_resolve_connection_key",
    "_resolve_info_strings",
]
