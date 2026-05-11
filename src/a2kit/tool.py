from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeVar

from mcp.types import ToolAnnotations

from a2kit.exceptions import InvalidToolReturnTypeError
from a2kit.metadata import PENDING_EXTRA_ATTR, A2KitMeta, set_meta
from a2kit.signature import find_context_param
from a2kit.surface import SURFACE_META_KEY, Surface

if TYPE_CHECKING:
    from a2kit.routers import Router

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class ToolDescriptor:
    """Typed introspection record for a registered tool.

    Materialized by ``App.add_router`` once per tool. ``format_hint`` is
    pre-computed from the tool's resolved return type so the CLI runtime can
    skip per-call format heuristics — see
    ``a2kit.packages.formatter.inference.infer_format_hint``.
    """

    name: str
    router: Router
    fn: Callable[..., Any]
    return_type: Any | None
    format_hint: Literal["tsv", "json", "page-tsv"]


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


_PRIMITIVE_RETURN_TYPES: tuple[type, ...] = (str, int, float, bool, bytes, type(None))


def _check_return(fn: Callable[..., Any]) -> None:
    ret = fn.__annotations__.get("return")
    # ``-> None`` annotation becomes the literal ``None`` (not ``type(None)``);
    # normalize so the membership check below catches it.
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
    """Return the function's return annotation as a runtime value, or ``None``.

    Prefers ``fn.__annotations__["return"]`` (carries the actual class when
    annotations are not stringified). Falls back to ``typing.get_type_hints``
    for stringified PEP 563 annotations; returns ``None`` if resolution fails
    (the lint rule will catch the issue pre-run anyway).
    """
    import typing

    ret = fn.__annotations__.get("return")
    if ret is None or not isinstance(ret, str):
        return ret
    try:
        return typing.get_type_hints(fn).get("return")
    except Exception:  # noqa: BLE001
        return None


def _walk_return_classes(ret: Any) -> Iterable[type]:
    """Yield every concrete class reachable from ``ret``, peeling generic args."""
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
    """A2K-LOCAL-RETURN-MODEL — reject return types defined in non-module scope.

    Presence of ``<locals>`` in ``cls.__qualname__`` is the authoritative CPython
    signal that the class was defined inside a function body. Only flags
    ``pydantic.BaseModel`` subclasses (the actual FastMCP failure mode).
    """
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


_RESERVED_TOOL_NAME_PREFIX = "_meta."
_BUILTIN_RESERVED_TOOL_NAMES = frozenset({"_meta.health"})


def _check_reserved_name(tool_name: str) -> None:
    if tool_name in _BUILTIN_RESERVED_TOOL_NAMES:
        return
    if tool_name.startswith(_RESERVED_TOOL_NAME_PREFIX):
        msg = (
            f"tool name {tool_name!r} uses reserved namespace {_RESERVED_TOOL_NAME_PREFIX!r}; "
            "this prefix is reserved for built-in protocol-meta tools (e.g. `_meta.health`)"
        )
        raise ValueError(msg)


def _stamp(
    fn: F,
    *,
    verb: Literal["read", "write", "list", "tool"],
    name: str | None,
    tags: frozenset[str],
    annotations: ToolAnnotations,
    surfaces: Surface = Surface.ALL,
) -> F:
    _check_return(fn)
    resolved_name = name or getattr(fn, "__name__", "<callable>")
    _check_reserved_name(resolved_name)
    pending: dict[str, Any] = dict(getattr(fn, PENDING_EXTRA_ATTR, None) or {})
    pending[SURFACE_META_KEY] = surfaces
    meta = A2KitMeta(
        tool_name=resolved_name,
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


def _build_annotations(
    *,
    verb: str,
    base_read_only: bool,
    base_destructive: bool,
    idempotent: bool,
    open_world: bool,
    destructive: bool | None,
    title: str | None,
    explicit: ToolAnnotations | None,
) -> ToolAnnotations:
    """Compose ``ToolAnnotations`` honoring per-decorator defaults + kwargs.

    - ``destructive`` only valid on ``write`` / ``tool``; raising on ``read``
      keeps the API self-documenting (read tools are non-destructive by spec).
    - ``explicit`` (full ``ToolAnnotations``) wins entirely when provided —
      escape hatch for advanced users.
    """
    if explicit is not None:
        return explicit
    if verb == "read" and destructive is not None:
        raise TypeError("`destructive` is not valid on `@a2kit.read`; use `@a2kit.write` or `@a2kit.tool`")
    is_destructive = base_destructive if destructive is None else destructive
    return ToolAnnotations(
        readOnlyHint=base_read_only,
        destructiveHint=is_destructive,
        idempotentHint=idempotent,
        openWorldHint=open_world,
        title=title,
    )


def tool(
    name: str | None = None,
    *,
    tags: set[str] | frozenset[str] | None = None,
    annotations: ToolAnnotations | None = None,
    idempotent: bool = False,
    open_world: bool = False,
    destructive: bool | None = None,
    title: str | None = None,
    surfaces: Surface = Surface.ALL,
) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="tool",
            name=name,
            tags=frozenset(tags or ()),
            annotations=_build_annotations(
                verb="tool",
                base_read_only=False,
                base_destructive=False,
                idempotent=idempotent,
                open_world=open_world,
                destructive=destructive,
                title=title,
                explicit=annotations,
            ),
            surfaces=surfaces,
        )

    return deco


def read(
    name: str | None = None,
    *,
    tags: set[str] | None = None,
    idempotent: bool = False,
    open_world: bool = False,
    destructive: bool | None = None,
    title: str | None = None,
    surfaces: Surface = Surface.ALL,
) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="read",
            name=name,
            tags=frozenset({"read", *(tags or set())}),
            annotations=_build_annotations(
                verb="read",
                base_read_only=True,
                base_destructive=False,
                idempotent=idempotent,
                open_world=open_world,
                destructive=destructive,
                title=title,
                explicit=None,
            ),
            surfaces=surfaces,
        )

    return deco


def write(
    name: str | None = None,
    *,
    tags: set[str] | None = None,
    idempotent: bool = False,
    open_world: bool = False,
    destructive: bool | None = None,
    title: str | None = None,
    surfaces: Surface = Surface.ALL,
) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="write",
            name=name,
            tags=frozenset({"write", *(tags or set())}),
            annotations=_build_annotations(
                verb="write",
                base_read_only=False,
                base_destructive=True,
                idempotent=idempotent,
                open_world=open_world,
                destructive=destructive,
                title=title,
                explicit=None,
            ),
            surfaces=surfaces,
        )

    return deco


def list_(
    *default_fields: str,
    name: str | None = None,
    tags: set[str] | None = None,
    page_size: int | None = None,
    selectable_fields: tuple[str, ...] | None = None,
    surfaces: Surface = Surface.ALL,
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
            surfaces=surfaces,
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
