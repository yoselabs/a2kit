from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from a2kit.metadata import get_meta

if TYPE_CHECKING:
    from collections.abc import Callable


class Router:
    """Group of tools sharing dependencies and a slug.

    Every subclass MUST declare two class attributes:

    - ``slug: str`` — non-empty string literal identifying the router.
      Visible to type checkers and to ``grep``. Set as a class-level
      assignment in the subclass body (``slug = "x"``). The framework
      does NOT derive the slug from ``type(self).__name__``.
    - ``tools: ClassVar[tuple[Callable[..., Any], ...]]`` — every method
      decorated with ``@a2kit.read/write/list_/tool`` that this router
      exposes. The tuple is placed AFTER the method definitions in the
      class body so the names are bound when the tuple is evaluated.
      The framework does NOT walk ``dir(self)``.

    Optional class-level extension points (read by ``App.add_router``):

    - ``providers: ClassVar[tuple[type | tuple[type, Callable], ...]]`` —
      each entry is either a type (registered as its own factory) or a
      ``(type, factory)`` tuple. Installed onto the App during
      ``add_router``.
    - ``__aenter__`` / ``__aexit__`` instance methods (Python's
      async-CM protocol). Subclasses opt in by implementing both. When
      present, ``__aenter__`` runs lazily on first dispatch of any
      tool belonging to this Router; ``__aexit__`` runs at App
      ``__aexit__`` time in LIFO of enter order.

    The discovery surface is closed to these four attributes; no
    ``install(self, app)`` hook, no ``on_startup``/``on_shutdown``
    auto-bridge, no ``__init_subclass__`` registry, no ``dir()`` walk.
    """

    # Subclasses MUST override these two attributes; the base class does
    # NOT provide defaults so missing-attribute access raises a clear
    # ``TypeError`` in ``Router.__init__`` (with the subclass name in the
    # message). ``slug`` is annotated as plain ``str`` (not ``ClassVar``)
    # so reads via ``self.slug`` / ``router.slug`` type-check uniformly.
    # Subclass class-scope assignment ``slug = "x"`` continues to be the
    # documented form.
    slug: str
    tools: ClassVar[tuple[Callable[..., Any], ...]]

    #: Per-tool exception enrichers. Subclasses override with a class-level tuple
    #: (immutable). Empty tuple is the no-enricher default.
    enrichers: ClassVar[tuple[Callable[[Exception], str | None], ...]] = ()
    providers: ClassVar[tuple[Any, ...]] = ()

    #: Default visibility tier for this Router's tools. Per-tool ``visibility=``
    #: kwarg overrides this. Resolution: per-tool kwarg (if explicitly set)
    #: → Router class attr → ``"all"`` baseline. See ADR 0003 vs. visibility:
    #: ``"hidden"`` = CLI-invokable but absent from --help; ``"cli"`` =
    #: visible in --help, hidden from MCP/API/GraphQL; ``"all"`` =
    #: everywhere (default).
    visibility: ClassVar[str] = "all"

    def __init__(self) -> None:
        cls = type(self)
        # --- slug check ---------------------------------------------------- #
        slug = getattr(cls, "slug", None)
        if not isinstance(slug, str) or not slug:
            msg = f"Router subclass {cls.__name__!r} must define class attribute 'slug: str'. Example: `slug = \"{cls.__name__.lower()}\"`."
            raise TypeError(msg)

        # --- tools check --------------------------------------------------- #
        tools = getattr(cls, "tools", None)
        if not isinstance(tools, tuple):
            msg = (
                f"Router subclass {cls.__name__!r} must define class attribute "
                f"'tools: ClassVar[tuple[Callable, ...]]' listing every "
                f"verb-decorated method. Example: `tools = (fetch, update)`."
            )
            raise TypeError(msg)

        bound: list[Callable[..., Any]] = []
        for fn in tools:
            if not callable(fn):
                msg = f"Router subclass {cls.__name__!r}: every entry in `tools` must be a callable (method reference); got {fn!r}."
                raise TypeError(msg)
            name = getattr(fn, "__name__", None)
            if name is None:
                msg = (
                    f"Router subclass {cls.__name__!r}: tools entry {fn!r} has no __name__; only top-level method references are supported."
                )
                raise TypeError(msg)
            bound_method = getattr(self, name)
            meta = get_meta(bound_method)
            if meta is None:
                msg = (
                    f"Router subclass {cls.__name__!r}: method {name!r} listed "
                    f"in `tools` carries no @a2kit verb-decorator metadata. "
                    f"Decorate with @a2kit.read/write/list_/tool, or remove "
                    f"it from the `tools` tuple."
                )
                raise TypeError(msg)
            if meta.extras.router_slug is None:
                meta.extras.router_slug = self.slug
            # Resolve effective visibility: per-tool kwarg (if explicitly set)
            # → Router class attr → "all" baseline. Per-tool None means inherit.
            if meta.extras.visibility is None:
                meta.extras.visibility = type(self).visibility  # noqa: A2K-EXTRA-NAMESPACE
            bound.append(bound_method)

        self._tools: list[Callable[..., Any]] = bound

    def bound_tools(self) -> list[Callable[..., Any]]:
        """Return bound method references registered as tools on this instance."""
        return list(self._tools)


class RouterRegistry:
    def __init__(self) -> None:
        self._routers: list[Router] = []

    def add(self, router: Router) -> None:
        self._routers.append(router)

    def all(self) -> list[Router]:
        return list(self._routers)

    def bound_tools(self) -> list[Callable[..., Any]]:
        out: list[Callable[..., Any]] = []
        for r in self._routers:
            out.extend(r.bound_tools())
        return out
