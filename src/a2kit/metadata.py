from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from mcp.types import ToolAnnotations


Verb = Literal["read", "write", "list", "tool"]


@dataclass(frozen=True, slots=True)
class ListViewSettings:
    """Carrier for ``@a2kit.list_(...)`` projection / pagination settings.

    Lives in core (read by ``packages/mcp/listview.py`` middleware) but
    holds no domain feature names — just the shape of list-view config.
    """

    default_fields: tuple[str, ...] = ()
    page_size: int | None = None
    selectable_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class A2KitMeta:
    tool_name: str
    verb: Verb
    tags: frozenset[str]
    annotations: ToolAnnotations
    context_param_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


META_ATTR = "_a2kit"
PENDING_EXTRA_ATTR = "_a2kit_pending_extra"


def get_meta(fn: Any) -> A2KitMeta | None:
    return getattr(fn, META_ATTR, None)


def set_meta(fn: Any, meta: A2KitMeta) -> None:
    object.__setattr__(fn, META_ATTR, meta)


def stage_extra(fn: Any, key: str, value: Any) -> None:
    """Stage an extra key for the verb decorator to consume, or write directly if meta exists."""
    meta = get_meta(fn)
    if meta is not None:
        meta.extra[key] = value
        return
    pending: dict[str, Any] | None = getattr(fn, PENDING_EXTRA_ATTR, None)
    if pending is None:
        pending = {}
        object.__setattr__(fn, PENDING_EXTRA_ATTR, pending)
    pending[key] = value
