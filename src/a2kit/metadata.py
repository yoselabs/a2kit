from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from mcp.types import ToolAnnotations


EnricherFn = Callable[[Exception, str], Exception]
Verb = Literal["read", "write", "list", "tool"]


@dataclass(frozen=True, slots=True)
class ListViewSettings:
    default_fields: tuple[str, ...] = ()
    page_size: int | None = None
    selectable_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class A2KitMeta:
    tool_name: str
    verb: Verb
    tags: frozenset[str]
    annotations: ToolAnnotations
    router_slug: str | None = None
    list_view: ListViewSettings | None = None
    enricher: EnricherFn | None = None
    context_param_name: str | None = None
    report_type: type | None = None
    report_schema: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


META_ATTR = "_a2kit"


def get_meta(fn: Any) -> A2KitMeta | None:
    return getattr(fn, META_ATTR, None)


def set_meta(fn: Any, meta: A2KitMeta) -> None:
    object.__setattr__(fn, META_ATTR, meta)
