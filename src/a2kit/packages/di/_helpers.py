"""Pure helper functions shared by ``Container`` resolution.

Extracted from ``container.py`` to keep that file under the A2K014
SLOC budget. None of these helpers depend on ``Container`` state — they
are static utilities over annotations / instance values.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


def lazy_inner_type(ann: Any) -> type | None:  # noqa: PLR0911
    """If ``ann`` is ``Lazy[T]`` / ``Callable[[], Awaitable[T]]``, return ``T``.

    Recognizes the user-facing ``a2kit.Lazy`` alias plus the equivalent
    raw ``Callable[[], Awaitable[T]]`` shape. Returns ``None`` for any
    other annotation.
    """
    import typing as _typing
    from collections.abc import Awaitable as _Awaitable
    from collections.abc import Callable as _Callable

    origin = _typing.get_origin(ann)
    if origin is None:
        return None
    if origin not in (_Callable, _typing.Callable):  # type: ignore[attr-defined]
        return None
    args = _typing.get_args(ann)
    if len(args) != 2:
        return None
    callable_args, ret = args
    if callable_args != []:
        return None
    ret_origin = _typing.get_origin(ret)
    if ret_origin not in (_Awaitable, _typing.Awaitable):  # type: ignore[attr-defined]
        return None
    inner = _typing.get_args(ret)
    if len(inner) != 1:
        return None
    t = inner[0]
    if isinstance(t, type):
        return t
    return None


def looks_like_basesettings(type_: Any) -> bool:
    """Duck-typed detection of ``pydantic_settings.BaseSettings`` subclasses.

    Walks ``type_.__mro__`` looking for a class whose ``__module__`` starts
    with ``pydantic_settings`` and whose ``__name__`` is ``BaseSettings``.
    Duck-typed on purpose: the container stays usable without the optional
    settings dependency installed.
    """
    if not inspect.isclass(type_):
        return False
    for base in type_.__mro__:
        mod = getattr(base, "__module__", "") or ""
        name = getattr(base, "__name__", "")
        if name == "BaseSettings" and mod.startswith("pydantic_settings"):
            return True
    return False


async def enter_lifecycle(result: Any) -> tuple[Any, Callable[..., Any] | None]:
    """Single-protocol entry: only ``__aenter__``/``__aexit__`` is honored.

    Returns ``(instance, aexit_callable_or_None)``. The ``aexit`` callable
    forwards ``(exc_type, exc, tb)`` to the resource's ``__aexit__`` so
    per-call resources see the propagating body exception (matching the
    Python ``async with`` protocol).

    ``aclose`` / ``close`` are NOT auto-detected — wrap such resources in
    a class with ``__aenter__``/``__aexit__`` or use ``@asynccontextmanager``.

    Partial-entry safety: nothing is returned to the caller until
    ``__aenter__`` succeeded.
    """
    if hasattr(result, "__aenter__") and hasattr(result, "__aexit__"):
        instance = await result.__aenter__()

        async def _aexit(exc_type: Any = None, exc: Any = None, tb: Any = None) -> None:
            await result.__aexit__(exc_type, exc, tb)

        return instance, _aexit
    return result, None


__all__ = ["enter_lifecycle", "lazy_inner_type", "looks_like_basesettings"]
