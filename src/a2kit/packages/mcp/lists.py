"""Stacked ``@lists(...)`` decorator and ``ListViewSettings`` shape.

Moved out of core ``a2kit.metadata`` so the verb decorator carries no
list-view kwarg. Tool authors stack ``@lists(...)`` on top of the verb
decorator to attach settings; the listview MCP middleware reads them
from ``A2KitMeta.extra["a2kit.list_view"]``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from a2kit.metadata import stage_extra

EXTRA_KEY = "a2kit.list_view"

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True, slots=True)
class ListViewSettings:
    default_fields: tuple[str, ...] = ()
    page_size: int | None = None
    selectable_fields: tuple[str, ...] = ()


def lists(
    *,
    default_fields: tuple[str, ...] = (),
    page_size: int | None = None,
    selectable_fields: tuple[str, ...] = (),
) -> Callable[[F], F]:
    """Attach list-view projection / pagination settings to a list-shaped tool."""
    settings = ListViewSettings(
        default_fields=default_fields,
        page_size=page_size,
        selectable_fields=selectable_fields,
    )

    def deco(fn: F) -> F:
        stage_extra(fn, EXTRA_KEY, settings)
        return fn

    return deco


__all__ = ["EXTRA_KEY", "ListViewSettings", "lists"]
