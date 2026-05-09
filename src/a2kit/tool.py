from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypeVar

from mcp.types import ToolAnnotations

from a2kit.exceptions import InvalidToolReturnTypeError
from a2kit.metadata import PENDING_EXTRA_ATTR, A2KitMeta, set_meta
from a2kit.signature import find_context_param

F = TypeVar("F", bound=Callable[..., Any])


def _check_return(fn: Callable[..., Any]) -> None:
    ret = fn.__annotations__.get("return")
    if ret is str:
        raise InvalidToolReturnTypeError(getattr(fn, "__name__", "<callable>"))


def _stamp(
    fn: F,
    *,
    verb: Literal["read", "write", "list", "tool"],
    name: str | None,
    tags: frozenset[str],
    annotations: ToolAnnotations,
) -> F:
    _check_return(fn)
    pending: dict[str, Any] = dict(getattr(fn, PENDING_EXTRA_ATTR, None) or {})
    meta = A2KitMeta(
        tool_name=name or getattr(fn, "__name__", "<callable>"),
        verb=verb,
        tags=tags,
        annotations=annotations,
        context_param_name=find_context_param(fn),
        extra=pending,
    )
    set_meta(fn, meta)
    if hasattr(fn, PENDING_EXTRA_ATTR):
        import contextlib

        with contextlib.suppress(AttributeError):
            delattr(fn, PENDING_EXTRA_ATTR)
    return fn


def tool(
    name: str | None = None,
    *,
    tags: set[str] | frozenset[str] | None = None,
    annotations: ToolAnnotations | None = None,
) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="tool",
            name=name,
            tags=frozenset(tags or ()),
            annotations=annotations or ToolAnnotations(),
        )

    return deco


def read(name: str | None = None, *, tags: set[str] | None = None) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="read",
            name=name,
            tags=frozenset({"read", *(tags or set())}),
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )

    return deco


def write(name: str | None = None, *, tags: set[str] | None = None) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="write",
            name=name,
            tags=frozenset({"write", *(tags or set())}),
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
        )

    return deco


def list_(name: str | None = None, *, tags: set[str] | None = None) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="list",
            name=name,
            tags=frozenset({"read", "list", *(tags or set())}),
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )

    return deco
