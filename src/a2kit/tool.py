from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol, TypeVar

from mcp.types import ToolAnnotations

from a2kit.exceptions import InvalidToolReturnTypeError
from a2kit.metadata import PENDING_EXTRA_ATTR, A2KitMeta, set_meta
from a2kit.signature import find_context_param

F = TypeVar("F", bound=Callable[..., Any])


class DispatchHook(Protocol):
    """Hook called before invoking a tool method.

    Given the tool function and the wire-supplied kwargs, return the
    kwargs to pass to ``fn``. The default identity hook returns the
    input unchanged. Apps with registered providers install a non-identity
    hook that resolves typed dependencies.
    """

    def __call__(
        self,
        fn: Callable[..., Any],
        wire_kwargs: dict[str, Any],
    ) -> dict[str, Any] | Awaitable[dict[str, Any]]: ...


def identity_dispatch_hook(
    fn: Callable[..., Any],
    wire_kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Default dispatch hook — pass kwargs through unchanged."""
    del fn
    return wire_kwargs


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


def list_(
    *default_fields: str,
    name: str | None = None,
    tags: set[str] | None = None,
    page_size: int | None = None,
    selectable_fields: tuple[str, ...] | None = None,
) -> Callable[[F], F]:
    """List-shaped tool decorator. Absorbs list-view projection/pagination.

    Positional ``*default_fields`` is the row-projection default. When
    ``selectable_fields`` is omitted, it is derived from the tool's
    return-type annotation (``list[T]`` → fields of ``T``) at stamp time.
    """
    from a2kit.metadata import ListViewSettings

    def deco(fn: F) -> F:
        derived_selectable = selectable_fields
        if derived_selectable is None:
            derived_selectable = _derive_selectable_fields(fn)
        # Validate: every default field must appear in selectable (when
        # selectable was derivable; otherwise we trust the author).
        if derived_selectable and default_fields:
            extras = [f for f in default_fields if f not in derived_selectable]
            if extras:
                msg = (
                    f"@a2kit.list_: default field(s) {extras!r} not in selectable "
                    f"set {list(derived_selectable)!r} for {getattr(fn, '__name__', '<callable>')!r}"
                )
                raise ValueError(msg)
        settings = ListViewSettings(
            default_fields=tuple(default_fields),
            page_size=page_size,
            selectable_fields=tuple(derived_selectable or ()),
        )
        from a2kit.metadata import stage_extra

        stage_extra(fn, "a2kit.list_view", settings)
        return _stamp(
            fn,
            verb="list",
            name=name,
            tags=frozenset({"read", "list", *(tags or set())}),
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )

    return deco


def _derive_selectable_fields(fn: Callable[..., Any]) -> tuple[str, ...]:
    """Walk ``list[T]`` return annotation; return ``T``'s fields, or ()."""
    import contextlib
    import typing
    from typing import get_type_hints

    try:
        hints = get_type_hints(fn)
    except Exception:  # noqa: BLE001
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
    with contextlib.suppress(Exception):
        import dataclasses

        if dataclasses.is_dataclass(inner):
            return tuple(f.name for f in dataclasses.fields(inner))
    return ()
