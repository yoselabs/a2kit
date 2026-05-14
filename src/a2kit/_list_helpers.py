"""``@a2kit.list_`` annotation validators + selectable-field derivation.

Extracted from ``a2kit.tool`` per ``split-oversized-core-files`` to
keep ``tool.py`` under the A2K014 SLOC budget. These helpers all run
at decoration time and must not raise on unexpected shapes (decoration
must not raise — failures degrade observably via WARN).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

_log = logging.getLogger("a2kit")

_WARN_ONCE_SELECTABLE: set[str] = set()
_WARN_ONCE_BARE_COLLECTION: set[str] = set()

_COLLECTION_ORIGINS: tuple[type, ...] = (list, tuple, set, frozenset)


def _resolve_return_annotation_for_list(fn: Callable[..., Any]) -> Any:
    """Resolve the return annotation on ``fn`` for ``@list_`` validation.

    Mirrors :func:`a2kit.tool._resolve_return_annotation` but lives here
    so the list helpers can be cleanly extracted without re-importing
    from ``tool.py`` (which would create a cycle).
    """
    import typing

    ret = fn.__annotations__.get("return")
    if ret is None or not isinstance(ret, str):
        return ret
    try:
        return typing.get_type_hints(fn).get("return")
    except Exception as exc:  # noqa: BLE001 -- decoration must not raise; degrade observably
        name = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
        _log.warning("_resolve_return_annotation_for_list failed for %s: %s", name, exc)
        return None


def check_list_return_annotation(fn: Callable[..., Any]) -> None:
    """Validate ``@a2kit.list_`` return is a collection of T.

    Raises ``TypeError`` if origin is not a supported collection or if
    no return annotation is declared. Bare collections (no type
    parameter) emit a one-time ``RuntimeWarning``.
    """
    import typing

    fn_name = getattr(fn, "__name__", "<callable>")
    ret = _resolve_return_annotation_for_list(fn)
    if ret is None and "return" not in fn.__annotations__:
        raise TypeError(
            f"@a2kit.list_: function {fn_name!r} has no return annotation; "
            "list tools require a `list[T]` (or tuple/set/frozenset of T) "
            "return annotation."
        )
    origin = typing.get_origin(ret)
    if origin in _COLLECTION_ORIGINS:
        args = typing.get_args(ret)
        if not args:
            _warn_bare(fn, fn_name)
        return
    if isinstance(ret, type) and ret in _COLLECTION_ORIGINS:
        _warn_bare(fn, fn_name)
        return
    raise TypeError(
        f"@a2kit.list_: function {fn_name!r} return annotation is {ret!r}; "
        "expected `list[T]` (or `tuple[T, ...]` / `set[T]` / `frozenset[T]`)."
    )


def _warn_bare(fn: Callable[..., Any], fn_name: str) -> None:
    import warnings

    key = getattr(fn, "__qualname__", fn_name)
    if key in _WARN_ONCE_BARE_COLLECTION:
        return
    _WARN_ONCE_BARE_COLLECTION.add(key)
    warnings.warn(
        f"@a2kit.list_: function {fn_name!r} return annotation lacks a type parameter; selectable-field derivation will be empty.",
        RuntimeWarning,
        stacklevel=4,
    )


def derive_selectable_fields(fn: Callable[..., Any]) -> tuple[str, ...]:
    """Walk a list/tuple/set/frozenset return annotation; return ``T``'s fields, or ()."""
    import typing
    from typing import get_type_hints

    try:
        hints = get_type_hints(fn)
    except Exception as exc:  # noqa: BLE001 -- decoration must not raise; degrade observably
        name = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
        if name not in _WARN_ONCE_SELECTABLE:
            _WARN_ONCE_SELECTABLE.add(name)
            _log.warning("derive_selectable_fields: get_type_hints failed for %s: %s", name, exc)
        return ()
    ret = hints.get("return")
    origin = typing.get_origin(ret) if ret is not None else None
    if origin not in (list, tuple, set, frozenset):
        return ()
    args = typing.get_args(ret) if ret is not None else ()
    if not args:
        return ()
    inner = args[0]
    fields_attr = getattr(inner, "__pydantic_fields__", None)
    if fields_attr is not None:
        return tuple(fields_attr.keys())
    import dataclasses

    if dataclasses.is_dataclass(inner):
        return tuple(f.name for f in dataclasses.fields(inner))
    return ()
