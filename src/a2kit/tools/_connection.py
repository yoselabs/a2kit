"""Connection lookup, key coercion, and typed-info DI detection.

Sync and async paths share the same store contract — `_lookup_connection_sync`
drives the async coroutine via anyio's 3-tier drain.
`_safe_list_connection_keys` runs at decoration time to populate the canonical
connection-param docstring with available keys.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from a2kit.exceptions import ConnectionNotFound

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


def _detect_info_param(fn: Any, sig: inspect.Signature) -> tuple[str, type] | None:
    """Type-driven info DI — find a `ConnectionInfo`-typed param on `fn`.

    Returns ``(param_name, info_class)`` if exactly one such param exists;
    ``None`` if zero. Raises if more than one.
    """
    from a2kit.connections import ConnectionInfo  # noqa: PLC0415

    try:
        hints = inspect.get_annotations(fn, eval_str=True)
    except (NameError, AttributeError):  # pragma: no cover — forward-ref fallback
        hints = getattr(fn, "__annotations__", {})

    matches: list[tuple[str, type]] = []
    for name in sig.parameters:
        anno = hints.get(name)
        if isinstance(anno, type) and issubclass(anno, ConnectionInfo):
            matches.append((name, anno))
    if not matches:
        return None
    if len(matches) > 1:
        names = [m[0] for m in matches]
        msg = (
            f"Tool {fn.__name__!r} declares multiple ConnectionInfo-typed "
            f"parameters {names}. Only one info-injection target is supported "
            "per tool; use `Router.context.info()` from a helper for "
            "cross-context access."
        )
        raise ValueError(msg)
    return matches[0]


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
    import anyio  # noqa: PLC0415
    import anyio.from_thread  # noqa: PLC0415

    async def _run() -> Any:
        return await store.load(key)

    try:
        return anyio.from_thread.run(_run)
    except RuntimeError:
        pass
    try:
        return anyio.run(_run)
    except RuntimeError:
        import concurrent.futures  # noqa: PLC0415

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(anyio.run, _run).result()


def _resolve_info_strings(info: ConnectionInfo, registry: ResolverRegistry | None) -> ConnectionInfo:
    """Return a copy of `info` with every str field resolved through `registry`.

    Pydantic v2 frozen models support `.model_copy(update={...})`. We collect
    the str-typed fields, resolve each, and produce one new instance.
    """
    from a2kit.tokens import resolve_token  # noqa: PLC0415

    update: dict[str, str] = {}
    for name, value in info.model_dump().items():
        if isinstance(value, str) and name != "key":
            update[name] = resolve_token(value, registry=registry)
    if not update:
        return info
    return info.model_copy(update=update)


def _safe_list_connection_keys(store: object) -> list[str] | None:
    """Best-effort list of saved connection keys for schema enrichment.

    Returns ``None`` if the store can't list (no method, missing dir, etc.) so
    the docstring builder uses the generic phrasing instead. Note: keys are
    captured at decoration time — `login` calls made after server build do
    not refresh the docstring.

    v0.11: `store.list_connections` is async; decoration time has no event
    loop, so we drive the coroutine through `anyio.run`. If decoration ever
    happens *inside* a running loop (rare — module imports usually predate
    `anyio.run(main)`), `anyio.run` raises and we degrade gracefully.
    """
    from a2kit.connections import ConnectionStoreLike  # noqa: PLC0415

    if not isinstance(store, ConnectionStoreLike):
        return None
    import anyio  # noqa: PLC0415

    try:
        infos = anyio.run(store.list_connections)
        return ["-".join(info.key) for info in infos]
    except (OSError, AttributeError, ValueError, RuntimeError):
        return None


__all__ = [
    "_detect_info_param",
    "_lookup_connection_async",
    "_lookup_connection_sync",
    "_resolve_connection_key",
    "_resolve_info_strings",
    "_safe_list_connection_keys",
]
