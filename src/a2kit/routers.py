from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.metadata import get_meta

if TYPE_CHECKING:
    from collections.abc import Callable


_ROUTER_SUFFIX = "Router"


def _derive_slug(class_name: str) -> str:
    """Strip one trailing ``Router`` and lowercase: ``TasksRouter`` → ``tasks``.

    The suffix is case-sensitive; ``MyRouter`` becomes ``my`` but ``Myrouter``
    stays ``myrouter``. Collisions across routers in one app are caught by
    ``App.add_router``.
    """
    base = class_name
    if base.endswith(_ROUTER_SUFFIX) and len(base) > len(_ROUTER_SUFFIX):
        base = base[: -len(_ROUTER_SUFFIX)]
    return base.lower()


class Router:
    """Group of tools sharing dependencies and a slug.

    Slug resolution: ``name=`` constructor arg, then ``cls.name`` class
    attribute, then a derivation rule on ``type(self).__name__``: strip
    a single trailing ``Router`` suffix (case-sensitive), lowercase the
    rest. Collisions across routers in one ``App`` raise at build time.

    Optional extension points:

    - ``providers: tuple[type | tuple[type, Callable], ...]`` — class attribute.
      Each entry is either a type (registered as its own factory) or a
      ``(type, factory)`` tuple. Installed onto the App during ``add_router``.
    - ``on_startup`` / ``on_shutdown`` — async or sync methods. When defined
      on the subclass, they are registered as App lifecycle handlers during
      ``add_router``.
    """

    name: str | None = None
    #: Per-tool exception enrichers. Subclasses override with a class-level tuple
    #: (immutable). Empty tuple is the no-enricher default.
    enrichers: tuple[Callable[[Exception], str | None], ...] = ()
    providers: tuple[Any, ...] = ()

    def __init__(self, name: str | None = None) -> None:
        self.slug = name or self.name or _derive_slug(type(self).__name__)
        self._tools: list[Callable[..., Any]] = []
        for fn in self._collect_methods():
            meta = get_meta(fn)
            if meta is not None and meta.extras.router_slug is None:  # noqa: A2K-CORE-CLEAN
                meta.extras.router_slug = self.slug  # noqa: A2K-CORE-CLEAN
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
