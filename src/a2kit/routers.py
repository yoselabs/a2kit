from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.metadata import get_meta

if TYPE_CHECKING:
    from collections.abc import Callable


_ROUTER_SLUG_KEY = "a2kit.router_slug"


class Router:
    """Group of tools sharing dependencies and a slug.

    Slug resolution: ``name=`` constructor arg, then ``cls.name`` class
    attribute, then ``type(self).__name__`` verbatim. No string surgery.
    """

    name: str | None = None

    def __init__(self, name: str | None = None) -> None:
        self.slug = name or self.name or type(self).__name__
        self._tools: list[Callable[..., Any]] = []
        for fn in self._collect_methods():
            meta = get_meta(fn)
            if meta is not None:
                meta.extra.setdefault(_ROUTER_SLUG_KEY, self.slug)
            self._tools.append(fn)

    def _collect_methods(self) -> list[Callable[..., Any]]:
        out: list[Callable[..., Any]] = []
        for attr in dir(self):
            try:
                member = getattr(self, attr)
            except (AttributeError, ValueError, TypeError):
                continue
            if not callable(member):
                continue
            if get_meta(member) is not None:
                out.append(member)
        return out

    def tools(self) -> list[Callable[..., Any]]:
        return list(self._tools)


class RouterRegistry:
    def __init__(self) -> None:
        self._routers: list[Router] = []

    def add(self, router: Router) -> None:
        self._routers.append(router)

    def all(self) -> list[Router]:
        return list(self._routers)

    def tools(self) -> list[Callable[..., Any]]:
        out: list[Callable[..., Any]] = []
        for r in self._routers:
            out.extend(r.tools())
        return out
