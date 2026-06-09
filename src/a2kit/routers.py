from __future__ import annotations

import typing
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from a2kit.metadata import _get_meta

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2effect import AppError

    EnricherFn = Callable[[BaseException], AppError | None]
    EnricherEntry = tuple[type[BaseException], EnricherFn]

#: Exception TypeVar bound by ``BaseException`` so narrow enricher forms
#: (``def f(exc: BoomError) -> ...``) type-check against the decorator's
#: argument slot. Without this, ``Callable[[BoomError], ...]`` is not
#: assignable to ``Callable[[BaseException], ...]`` under contravariance.
_E = TypeVar("_E", bound=BaseException)


def _resolve_enricher_filter(fn: Callable[..., Any]) -> type[BaseException]:
    """Read the first parameter's annotation to decide narrow vs wide dispatch.

    Wide form (Exception / BaseException) returns BaseException; narrow form
    returns the specific exception type. Unannotated parameter defaults to
    BaseException (wide), matching the wide-form ergonomics.
    """
    try:
        hints = typing.get_type_hints(fn)
    except Exception:  # noqa: BLE001 — forward refs / unresolved typing fall back wide
        return BaseException
    import inspect

    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    if not params:
        msg = f"enricher {fn!r} must accept at least one positional parameter (the exception)"
        raise TypeError(msg)
    first = params[0]
    annotation = hints.get(first.name, BaseException)
    if not (isinstance(annotation, type) and issubclass(annotation, BaseException)):
        msg = f"enricher {fn!r} first parameter annotation must be a BaseException subclass, got {annotation!r}"
        raise TypeError(msg)
    return annotation


def _collect_marked_tool_names(cls: type) -> tuple[str, ...]:
    """Collect the names of every ``@a2kit`` verb-decorated method on ``cls``.

    Walks the MRO base-first so inherited verbs precede subclass-added
    ones, deduping by name (a subclass override keeps the base position
    but the override is what ``getattr`` later resolves). Only methods
    carrying the ``_a2kit`` metadata marker are collected — plain helper
    methods are invisible. This is marker-collection, deliberately NOT a
    ``dir()`` / attribute walk (ADR 0028 decision 7; ADR 0002 still
    rejects the dir() walk).
    """
    names: dict[str, None] = {}
    for klass in reversed(cls.__mro__):
        if klass in (object, Router):
            continue
        for name, value in vars(klass).items():
            if _get_meta(value) is not None:
                names[name] = None
    return tuple(names)


class Router:
    """Group of tools sharing dependencies and a slug.

    Every subclass MUST declare:

    - ``slug: str`` — non-empty string literal identifying the router.
      Visible to type checkers and to ``grep``. Set as a class-level
      assignment in the subclass body (``slug = "x"``). The framework
      does NOT derive the slug from ``type(self).__name__``.

    Tools are **auto-collected** (ADR 0028 decision 7): every method
    decorated with ``@a2kit.read/write/list_/tool`` is collected by
    ``__init_subclass__`` via its ``_a2kit`` marker. The legacy
    ``tools = (...)`` tuple is gone; if one is still present it is
    ignored (auto-collect is authoritative) during the migration window.
    Helper methods carry no marker and are never collected; this is
    marker-collection, NOT a ``dir()`` walk.

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

    The discovery surface is closed; no ``install(self, app)`` hook, no
    ``on_startup``/``on_shutdown`` auto-bridge, no ``dir()`` walk.
    """

    # Subclasses MUST override ``slug``; the base class does NOT provide a
    # default so missing-attribute access raises a clear ``TypeError`` in
    # ``Router.__init__`` (with the subclass name in the message).
    # ``slug`` is annotated as plain ``str`` (not ``ClassVar``) so reads
    # via ``self.slug`` / ``router.slug`` type-check uniformly.
    slug: str

    #: Auto-collected verb-method names, populated by ``__init_subclass__``.
    _a2kit_tool_names: ClassVar[tuple[str, ...]] = ()

    providers: ClassVar[tuple[Any, ...]] = ()

    #: Default visibility tier for this Router's tools. Per-tool ``visibility=``
    #: kwarg overrides this. Resolution: per-tool kwarg (if explicitly set)
    #: → Router class attr → ``"all"`` baseline. See ADR 0003 vs. visibility:
    #: ``"hidden"`` = CLI-invokable but absent from --help; ``"cli"`` =
    #: visible in --help, hidden from MCP/API/GraphQL; ``"all"`` =
    #: everywhere (default).
    visibility: ClassVar[str] = "all"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._a2kit_tool_names = _collect_marked_tool_names(cls)
        if "enrichers" in cls.__dict__ or "enrich" in cls.__dict__:
            raise TypeError(
                f"Router subclass {cls.__name__!r} defines a class-level "
                f"`enrichers` / `enrich` attribute; that surface was replaced "
                f"by the instance decorator. Construct the router, then write:\n"
                f"    router = {cls.__name__}()\n"
                f"    @router.enricher\n"
                f"    def my_enricher(exc: SpecificException) -> NotFound | None: ...\n"
                f"See a2effect-foundation for details."
            )

    def __init__(self, **_kw: Any) -> None:
        if _kw:
            cls_name = type(self).__name__
            msg = (
                f"{cls_name}.__init__ received unexpected keyword "
                f"arguments: {sorted(_kw)}. The base ``Router.__init__`` "
                "accepts no kwargs; subclasses with their own __init__ "
                "may take any args. See CHANGELOG.md for removals."
            )
            raise TypeError(msg)
        cls = type(self)
        # --- slug check ---------------------------------------------------- #
        slug = getattr(cls, "slug", None)
        if not isinstance(slug, str) or not slug:
            msg = f"Router subclass {cls.__name__!r} must define class attribute 'slug: str'. Example: `slug = \"{cls.__name__.lower()}\"`."
            raise TypeError(msg)

        # --- tools: auto-collected from @a2kit-marked methods -------------- #
        # Names are gathered in ``__init_subclass__`` via the ``_a2kit``
        # marker (no ``tools=`` tuple). Bind each to this instance and
        # stamp the per-tool router_slug / visibility.
        bound: list[Callable[..., Any]] = []
        for name in cls._a2kit_tool_names:
            bound_method = getattr(self, name)
            meta = _get_meta(bound_method)
            if meta is None:  # pragma: no cover -- collection only keeps marked methods
                continue
            if meta.extras.router_slug is None:
                meta.extras.router_slug = self.slug
            # Resolve effective visibility: per-tool kwarg (if explicitly set)
            # → Router class attr → "all" baseline. Per-tool None means inherit.
            if meta.extras.visibility is None:
                meta.extras.visibility = type(self).visibility  # noqa: AK208
            bound.append(bound_method)

        self._tools: list[Callable[..., Any]] = bound
        self._enrichers: list[EnricherEntry] = []

    def bound_tools(self) -> list[Callable[..., Any]]:
        """Return bound method references registered as tools on this instance."""
        return list(self._tools)

    def enricher(self, fn: Callable[[_E], AppError | None]) -> Callable[[_E], AppError | None]:
        """Register an exception → AppError|None translator on this router.

        The first parameter's annotation chooses dispatch shape:
          - ``def f(exc: Exception) -> ...``: wide — called for every raise.
          - ``def f(exc: SpecificException) -> ...``: narrow — only on isinstance.

        The return annotation MUST be ``AppError | None`` (or a subclass union
        thereof); the runtime validates the returned object at call time.
        """
        filter_type = _resolve_enricher_filter(fn)
        # The runtime treats `fn` as `Callable[[BaseException], ...]` once
        # registered — the narrow-form TypeVar only constrains the decorator
        # boundary so callers' typed-param functions are accepted.
        self._enrichers.append((filter_type, fn))  # ty: ignore[invalid-argument-type]
        return fn


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
