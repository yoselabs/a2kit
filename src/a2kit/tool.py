from __future__ import annotations  # noqa: A2K014

import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeVar

from a2kit.exceptions import InvalidToolReturnTypeError
from a2kit.metadata import A2KitMeta, A2KitMetaExtras, set_meta
from a2kit.signature import find_context_param

Visibility = Literal["hidden", "cli", "all"]

_log = logging.getLogger(__name__)
_WARN_ONCE_RESOLVE_RETURN: set[str] = set()
_WARN_ONCE_SELECTABLE: set[str] = set()
_WARN_ONCE_BARE_COLLECTION: set[str] = set()

if TYPE_CHECKING:
    from mcp.types import ToolAnnotations

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


_RESERVED_TOOL_NAME_PREFIX = "_meta."
_BUILTIN_RESERVED_TOOL_NAMES = frozenset({"_meta.health"})

_COLLECTION_ORIGINS: tuple[type, ...] = (list, tuple, set, frozenset)


def _check_reserved_name(tool_name: str) -> None:
    if tool_name in _BUILTIN_RESERVED_TOOL_NAMES:
        return
    if tool_name.startswith(_RESERVED_TOOL_NAME_PREFIX):
        msg = (
            f"tool name {tool_name!r} uses reserved namespace {_RESERVED_TOOL_NAME_PREFIX!r}; "
            "this prefix is reserved for built-in protocol-meta tools (e.g. `_meta.health`)"
        )
        raise ValueError(msg)


def _parse_timeout(value: float | int | str | None) -> float | None:
    """Parse a ``timeout=`` kwarg into canonical float seconds.

    Accepts ``None`` (no timeout), ``int``/``float`` (seconds), or a
    string with unit suffix ``"ms"``/``"s"``/``"m"`` (or a bare
    numeric string treated as seconds). Raises ``TypeError`` on any
    unparseable string at decoration time per
    ``dispatcher-timeout-decorator`` D-PARSE.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        msg = f"timeout= must be a number or unit string, got bool {value!r}"
        raise TypeError(msg)
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        msg = f"timeout= must be a number, unit string, or None; got {type(value).__name__}"
        raise TypeError(msg)
    s = value.strip().lower()
    if not s:
        msg = "timeout= string is empty"
        raise TypeError(msg)
    try:
        for suffix, mult in (("ms", 0.001), ("s", 1.0), ("m", 60.0)):
            if s.endswith(suffix):
                return float(s[: -len(suffix)]) * mult
        return float(s)
    except ValueError as exc:
        msg = f"timeout={value!r} is not a valid number or unit string (e.g. '60s', '2m', '500ms', 0.5)"
        raise TypeError(msg) from exc


def _stamp(
    fn: F,
    *,
    verb: Literal["read", "write", "list"],
    name: str | None,
    tags: frozenset[str],
    annotations_kwargs: dict[str, Any] | None = None,
    annotations_explicit: Any = None,
    visibility: Visibility | None = None,
    reports: type | None = None,
    list_view: Any | None = None,
    timeout: float | int | str | None = None,
) -> F:
    _check_return(fn)
    resolved_name = name or getattr(fn, "__name__", "<callable>")
    _check_reserved_name(resolved_name)
    extras_kwargs: dict[str, Any] = {"visibility": visibility}
    if reports is not None:
        extras_kwargs["report_type"] = reports
        schema = _compute_report_schema(reports)
        if schema is not None:
            extras_kwargs["report_schema"] = schema
    if list_view is not None:
        extras_kwargs["list_view"] = list_view
    parsed_timeout = _parse_timeout(timeout)
    if parsed_timeout is not None:
        extras_kwargs["timeout_seconds"] = parsed_timeout
    extras = A2KitMetaExtras(**extras_kwargs)
    meta = A2KitMeta(
        tool_name=resolved_name,
        verb=verb,
        tags=tags,
        _annotations_kwargs=annotations_kwargs,
        _annotations_explicit=annotations_explicit,
        context_param_name=find_context_param(fn),
        extras=extras,
    )
    set_meta(fn, meta)
    return fn


_WARN_ONCE_REPORT_SCHEMA: set[str] = set()


def _compute_report_schema(report_type: type) -> dict[str, Any] | None:
    """Best-effort JSON schema for a report type, used by adapters.

    Decoration must not raise (per the @a2kit.read/write footgun
    discipline), so failures here log at WARN and return None. The
    _WARN_ONCE pattern bounds log noise across repeated decorations
    of the same unschemable report type.
    """
    try:
        from pydantic import TypeAdapter
    except ImportError:
        return None
    try:
        return TypeAdapter(report_type).json_schema()
    except Exception as exc:  # noqa: BLE001 -- decoration must not raise; observe and degrade
        qual = getattr(report_type, "__qualname__", repr(report_type))
        if qual not in _WARN_ONCE_REPORT_SCHEMA:
            _WARN_ONCE_REPORT_SCHEMA.add(qual)
            logging.getLogger("a2kit").warning(
                "_compute_report_schema(%s) failed: %s: %s",
                qual,
                type(exc).__name__,
                exc,
            )
        return None


def _kwargs_for(pair: tuple[dict[str, Any] | None, Any | None]) -> dict[str, Any]:
    kwargs, explicit = pair
    return {"annotations_kwargs": kwargs, "annotations_explicit": explicit}


def _reject_read_shaped_kwargs(verb: str, *, idempotent: bool | None, destructive: bool | None) -> None:
    """Enforce MCP spec on read-shaped verbs: idempotent + destructive rejected."""
    if destructive is not None:
        raise TypeError(
            f"`destructive=` is not valid on `@a2kit.{verb}` — read tools are "
            "non-destructive by MCP spec. Use `@a2kit.write(destructive=...)` "
            "if you intended a destructive write."
        )
    if idempotent is not None:
        raise TypeError(
            f"`idempotent=` is not valid on `@a2kit.{verb}` — read tools are "
            "spec-idempotent by definition (MCP `idempotentHint` is meaningful "
            "only when `readOnlyHint=false`). Use `@a2kit.write(idempotent=...)` "
            "for a repeat-safe write."
        )


def _reject_annotations_flag_conflict(
    *,
    idempotent: bool | None,
    open_world: bool | None,
    destructive: bool | None,
    title: str | None,
) -> None:
    """Enforce: `annotations=` cannot be combined with any flag kwarg.

    All four flags use ``None`` as the "not-passed" sentinel, so the conflict
    check is symmetric — even ``open_world=False`` (explicit) trips the guard
    when paired with ``annotations=``. No silent winners.
    """
    conflicts: list[str] = []
    if idempotent is not None:
        conflicts.append("idempotent")
    if open_world is not None:
        conflicts.append("open_world")
    if destructive is not None:
        conflicts.append("destructive")
    if title is not None:
        conflicts.append("title")
    if conflicts:
        raise TypeError(
            "`annotations=` is the full-escape-hatch path and cannot be mixed "
            f"with flag kwargs ({', '.join(conflicts)}). Pick one: either compose "
            "via flag kwargs OR pass an explicit `ToolAnnotations(...)` object."
        )


def _build_annotation_kwargs(
    *,
    verb: str,
    base_read_only: bool,
    base_destructive: bool,
    idempotent: bool | None,
    open_world: bool | None,
    destructive: bool | None,
    title: str | None,
    explicit: ToolAnnotations | None,
) -> tuple[dict[str, Any] | None, Any | None]:
    """Return ``(kwargs, explicit)`` for the deferred annotation builder.

    Spec-derived rules (MCP):
    - ``destructiveHint`` and ``idempotentHint`` are meaningful only when
      ``readOnlyHint=false`` — i.e. on write-shaped verbs. Read-shaped verbs
      (``read``, ``list``) reject both kwargs at decoration time.
    - ``annotations=`` (explicit ``ToolAnnotations``) is the escape hatch.
      It MUST NOT be combined with the flag kwargs — silent winners are
      bugs waiting to happen.
    """
    if verb in ("read", "list"):
        _reject_read_shaped_kwargs(verb, idempotent=idempotent, destructive=destructive)
    if explicit is not None:
        _reject_annotations_flag_conflict(
            idempotent=idempotent,
            open_world=open_world,
            destructive=destructive,
            title=title,
        )
        return None, explicit
    is_destructive = base_destructive if destructive is None else destructive
    is_idempotent = False if idempotent is None else idempotent
    is_open_world = False if open_world is None else open_world
    kwargs: dict[str, Any] = {
        "readOnlyHint": base_read_only,
        "destructiveHint": is_destructive,
        "idempotentHint": is_idempotent,
        "openWorldHint": is_open_world,
    }
    if title is not None:
        kwargs["title"] = title
    return kwargs, None


def read(
    *,
    open_world: bool | None = None,
    title: str | None = None,
    visibility: Visibility | None = None,
    reports: type | None = None,
    annotations: ToolAnnotations | None = None,
    idempotent: bool | None = None,
    destructive: bool | None = None,
    timeout: float | int | str | None = None,
) -> Callable[[F], F]:
    """Read-shaped tool decorator. Sets ``readOnlyHint=True``.

    Read tools are spec-idempotent and non-destructive by definition;
    passing ``idempotent=`` or ``destructive=`` raises ``TypeError``.

    ``timeout=`` (per ``dispatcher-timeout-decorator``): None for no
    timeout, number for seconds, or string with unit suffix
    (``"60s"``, ``"2m"``, ``"500ms"``).
    """

    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="read",
            name=None,
            tags=frozenset({"read"}),
            **_kwargs_for(
                _build_annotation_kwargs(
                    verb="read",
                    base_read_only=True,
                    base_destructive=False,
                    idempotent=idempotent,
                    open_world=open_world,
                    destructive=destructive,
                    title=title,
                    explicit=annotations,
                )
            ),
            visibility=visibility,
            reports=reports,
            timeout=timeout,
        )

    return deco


def write(
    *,
    idempotent: bool | None = None,
    open_world: bool | None = None,
    destructive: bool | None = None,
    title: str | None = None,
    visibility: Visibility | None = None,
    reports: type | None = None,
    annotations: ToolAnnotations | None = None,
    timeout: float | int | str | None = None,
) -> Callable[[F], F]:
    """Write-shaped tool decorator. Sets ``readOnlyHint=False, destructiveHint=True`` by default.

    ``idempotent=`` and ``destructive=`` may be overridden. ``annotations=``
    is the full escape hatch — must not be mixed with flag kwargs.

    ``timeout=`` (per ``dispatcher-timeout-decorator``): None for no
    timeout, number for seconds, or string with unit suffix
    (``"60s"``, ``"2m"``, ``"500ms"``).
    """

    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="write",
            name=None,
            tags=frozenset({"write"}),
            **_kwargs_for(
                _build_annotation_kwargs(
                    verb="write",
                    base_read_only=False,
                    base_destructive=True,
                    idempotent=idempotent,
                    open_world=open_world,
                    destructive=destructive,
                    title=title,
                    explicit=annotations,
                )
            ),
            visibility=visibility,
            reports=reports,
            timeout=timeout,
        )

    return deco


def list_(
    *default_fields: str,
    page_size: int | None = None,
    selectable_fields: tuple[str, ...] | None = None,
    visibility: Visibility | None = None,
    reports: type | None = None,
    open_world: bool | None = None,
    title: str | None = None,
    annotations: ToolAnnotations | None = None,
    idempotent: bool | None = None,
    destructive: bool | None = None,
    timeout: float | int | str | None = None,
) -> Callable[[F], F]:
    """List-shaped tool decorator. Read-shaped; requires ``list[T]`` return.

    Positional ``*default_fields`` is the row-projection default. When
    ``selectable_fields`` is omitted, it is derived from the tool's
    return-type annotation (``list[T]`` → fields of ``T``) at stamp time.

    Like ``@read``, ``idempotent=`` and ``destructive=`` are rejected at
    decoration time. ``page_size`` must be a positive integer or ``None``.
    """
    from a2kit.metadata import ListViewSettings

    if page_size is not None and page_size <= 0:
        raise ValueError(f"@a2kit.list_: `page_size` must be a positive integer or None; got {page_size!r}")

    def deco(fn: F) -> F:
        _check_list_return_annotation(fn)
        derived_selectable = selectable_fields
        if derived_selectable is None:
            derived_selectable = _derive_selectable_fields(fn)
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
        return _stamp(
            fn,
            verb="list",
            name=None,
            tags=frozenset({"read", "list"}),
            **_kwargs_for(
                _build_annotation_kwargs(
                    verb="list",
                    base_read_only=True,
                    base_destructive=False,
                    idempotent=idempotent,
                    open_world=open_world,
                    destructive=destructive,
                    title=title,
                    explicit=annotations,
                )
            ),
            visibility=visibility,
            reports=reports,
            list_view=settings,
            timeout=timeout,
        )

    return deco


def _check_list_return_annotation(fn: Callable[..., Any]) -> None:
    """Validate ``@a2kit.list_`` return is ``list[T]`` / ``tuple[T,...]`` / ``set[T]`` / ``frozenset[T]``.

    Raises ``TypeError`` at decoration time if origin is not a supported
    collection or if no return annotation is declared. Bare collections
    (no type parameter) emit a one-time ``RuntimeWarning``.
    """
    import typing
    import warnings

    fn_name = getattr(fn, "__name__", "<callable>")
    ret = _resolve_return_annotation(fn)
    if ret is None and "return" not in fn.__annotations__:
        raise TypeError(
            f"@a2kit.list_: function {fn_name!r} has no return annotation; "
            f"list tools require a `list[T]` (or tuple/set/frozenset of T) return annotation."
        )
    origin = typing.get_origin(ret)
    if origin in _COLLECTION_ORIGINS:
        args = typing.get_args(ret)
        if not args:
            key = getattr(fn, "__qualname__", fn_name)
            if key not in _WARN_ONCE_BARE_COLLECTION:
                _WARN_ONCE_BARE_COLLECTION.add(key)
                warnings.warn(
                    f"@a2kit.list_: function {fn_name!r} return annotation lacks a type parameter; "
                    f"selectable-field derivation will be empty.",
                    RuntimeWarning,
                    stacklevel=3,
                )
        return
    if isinstance(ret, type) and ret in _COLLECTION_ORIGINS:
        # bare `list` / `tuple` / `set` / `frozenset` without subscript
        key = getattr(fn, "__qualname__", fn_name)
        if key not in _WARN_ONCE_BARE_COLLECTION:
            _WARN_ONCE_BARE_COLLECTION.add(key)
            warnings.warn(
                f"@a2kit.list_: function {fn_name!r} return annotation lacks a type parameter; selectable-field derivation will be empty.",
                RuntimeWarning,
                stacklevel=3,
            )
        return
    raise TypeError(
        f"@a2kit.list_: function {fn_name!r} return annotation is {ret!r}; "
        f"expected `list[T]` (or `tuple[T, ...]` / `set[T]` / `frozenset[T]`)."
    )


def _derive_selectable_fields(fn: Callable[..., Any]) -> tuple[str, ...]:
    """Walk ``list[T]`` return annotation; return ``T``'s fields, or ()."""
    import typing
    from typing import get_type_hints

    try:
        hints = get_type_hints(fn)
    except Exception as exc:  # noqa: BLE001 -- decoration must not raise; degrade observably
        name = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
        if name not in _WARN_ONCE_SELECTABLE:
            _WARN_ONCE_SELECTABLE.add(name)
            _log.warning("_derive_selectable_fields: get_type_hints failed for %s: %s", name, exc)
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


# ---------------------------------------------------------------------------
# Internal helpers — NOT part of the public surface.
# ---------------------------------------------------------------------------


def _read_internal(
    name: str,
    *,
    title: str | None = None,
    visibility: Visibility | None = None,
) -> Callable[[F], F]:
    """Private read-decorator variant that accepts a custom tool name.

    Reserved for framework-internal use (e.g. registering ``_meta.health``).
    Not exported via ``a2kit.__getattr__`` and not part of the public API.
    """

    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="read",
            name=name,
            tags=frozenset({"read"}),
            **_kwargs_for(
                _build_annotation_kwargs(
                    verb="read",
                    base_read_only=True,
                    base_destructive=False,
                    idempotent=None,
                    open_world=False,
                    destructive=None,
                    title=title,
                    explicit=None,
                )
            ),
            visibility=visibility,
            reports=None,
        )

    return deco
