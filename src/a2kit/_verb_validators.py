"""Return-annotation validators and reserved-name guards for verb decorators.

Extracted from ``a2kit._verbs`` per ``tidy-review-followups`` so
``_verbs.py`` stays comfortably under the A2K014 SLOC budget. These
helpers all run at decoration time and may either raise (return-type
discipline violations, reserved-name conflicts) or degrade observably
via WARN (unresolvable forward refs).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from a2kit.exceptions import InvalidToolReturnTypeError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

_log = logging.getLogger("a2kit.tool")
_WARN_ONCE_RESOLVE_RETURN: set[str] = set()

_PRIMITIVE_RETURN_TYPES: tuple[type, ...] = (str, int, float, bool, bytes, type(None))

_RESERVED_TOOL_NAME_PREFIX = "_meta."
_BUILTIN_RESERVED_TOOL_NAMES = frozenset({"_meta.health"})


def _check_return(fn: Callable[..., Any]) -> None:
    ret = fn.__annotations__.get("return")
    if ret is None and "return" in fn.__annotations__:
        ret = type(None)
    if ret in _PRIMITIVE_RETURN_TYPES:
        name = getattr(fn, "__name__", "<callable>")
        type_name = ret.__name__ if isinstance(ret, type) else str(ret)
        raise InvalidToolReturnTypeError(
            name,
            message=(f"tool {name!r} returns `{type_name}`; antipattern #1 — return a Pydantic model, dict, or list/Page of either"),
        )
    _check_return_scope(fn)


def _resolve_return_annotation(fn: Callable[..., Any]) -> Any:
    import typing

    ret = fn.__annotations__.get("return")
    if ret is None or not isinstance(ret, str):
        return ret
    try:
        return typing.get_type_hints(fn).get("return")
    except Exception as exc:  # noqa: BLE001 -- decoration must not raise; degrade observably
        name = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
        if name not in _WARN_ONCE_RESOLVE_RETURN:
            _WARN_ONCE_RESOLVE_RETURN.add(name)
            _log.warning("_resolve_return_annotation: get_type_hints failed for %s: %s", name, exc)
        return None


def _walk_return_classes(ret: Any) -> Iterable[type]:
    import typing

    seen: set[Any] = set()
    stack: list[Any] = [ret]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(typing.get_args(cur))
        if isinstance(cur, type):
            yield cur


def _check_return_scope(fn: Callable[..., Any]) -> None:
    """A2K-LOCAL-RETURN-MODEL — reject return types defined in non-module scope."""
    ret = _resolve_return_annotation(fn)
    if ret is None:
        return
    try:
        from pydantic import BaseModel
    except ImportError:
        return
    for cls in _walk_return_classes(ret):
        qualname: str = getattr(cls, "__qualname__", "")
        if "<locals>" not in qualname:
            continue
        if not issubclass(cls, BaseModel):
            continue
        fn_name = getattr(fn, "__name__", "<callable>")
        msg = (
            f"Tool {fn_name!r} return type {qualname!r} is defined in non-module scope; "
            "FastMCP's signature.eval_str=True cannot resolve names from a function that "
            "has already returned. Hoist the class to module scope. "
            "See A2K-LOCAL-RETURN-MODEL."
        )
        raise InvalidToolReturnTypeError(fn_name, message=msg)


def _check_reserved_name(tool_name: str) -> None:
    if tool_name in _BUILTIN_RESERVED_TOOL_NAMES:
        return
    if tool_name.startswith(_RESERVED_TOOL_NAME_PREFIX):
        msg = (
            f"tool name {tool_name!r} uses reserved namespace {_RESERVED_TOOL_NAME_PREFIX!r}; "
            "this prefix is reserved for built-in protocol-meta tools (e.g. `_meta.health`)"
        )
        raise ValueError(msg)
