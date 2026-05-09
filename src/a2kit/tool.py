from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypeVar

from mcp.types import ToolAnnotations

from a2kit.exceptions import InvalidToolReturnTypeError
from a2kit.metadata import A2KitMeta, EnricherFn, ListViewSettings, set_meta
from a2kit.signature import find_context_param

F = TypeVar("F", bound=Callable[..., Any])


def _check_return(fn: Callable[..., Any]) -> None:
    ret = fn.__annotations__.get("return")
    if ret is str:
        raise InvalidToolReturnTypeError(getattr(fn, "__name__", "<callable>"))


def _report_schema(report_type: type | None) -> dict[str, Any] | None:
    if report_type is None:
        return None
    try:
        from pydantic import TypeAdapter
    except ImportError:
        return None
    return TypeAdapter(report_type).json_schema()


def _stamp(
    fn: F,
    *,
    verb: Literal["read", "write", "list", "tool"],
    name: str | None,
    tags: frozenset[str],
    annotations: ToolAnnotations,
    enricher: EnricherFn | None,
    list_view: ListViewSettings | None,
    router_slug: str | None,
    report_type: type | None,
) -> F:
    _check_return(fn)
    meta = A2KitMeta(
        tool_name=name or getattr(fn, "__name__", "<callable>"),
        verb=verb,
        tags=tags,
        annotations=annotations,
        router_slug=router_slug,
        list_view=list_view,
        enricher=enricher,
        context_param_name=find_context_param(fn),
        report_type=report_type,
        report_schema=_report_schema(report_type),
    )
    set_meta(fn, meta)
    return fn


def tool(
    name: str | None = None,
    *,
    tags: set[str] | frozenset[str] | None = None,
    annotations: ToolAnnotations | None = None,
    enricher: EnricherFn | None = None,
    list_view: ListViewSettings | None = None,
    router_slug: str | None = None,
    report: type | None = None,
) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="tool",
            name=name,
            tags=frozenset(tags or ()),
            annotations=annotations or ToolAnnotations(),
            enricher=enricher,
            list_view=list_view,
            router_slug=router_slug,
            report_type=report,
        )

    return deco


def read(name: str | None = None, *, tags: set[str] | None = None, **kw: Any) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="read",
            name=name,
            tags=frozenset({"read", *(tags or set())}),
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
            enricher=kw.get("enricher"),
            list_view=kw.get("list_view"),
            router_slug=kw.get("router_slug"),
            report_type=kw.get("report"),
        )

    return deco


def write(name: str | None = None, *, tags: set[str] | None = None, **kw: Any) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="write",
            name=name,
            tags=frozenset({"write", *(tags or set())}),
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
            enricher=kw.get("enricher"),
            list_view=kw.get("list_view"),
            router_slug=kw.get("router_slug"),
            report_type=kw.get("report"),
        )

    return deco


def list_(name: str | None = None, *, tags: set[str] | None = None, **kw: Any) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        return _stamp(
            fn,
            verb="list",
            name=name,
            tags=frozenset({"read", "list", *(tags or set())}),
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
            enricher=kw.get("enricher"),
            list_view=kw.get("list_view"),
            router_slug=kw.get("router_slug"),
            report_type=kw.get("report"),
        )

    return deco
