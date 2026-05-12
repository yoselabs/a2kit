from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mcp.types import ToolAnnotations


_EMPTY_PARAM_DESCRIPTIONS: Mapping[str, str] = MappingProxyType({})


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
    """Per-tool metadata stamped by verb decorators.

    ``annotations`` is exposed as a property that lazily constructs the
    ``mcp.types.ToolAnnotations`` instance. The decorator path stores the
    kwargs in ``_annotations_kwargs`` (or an already-built explicit instance
    in ``_annotations_explicit``) so the mcp.types import is deferred until
    the consumer actually reads the annotation surface. This shaves ~90ms
    off cold-start for CLI flows that never touch annotations
    (``--help``, plain tool invocation).
    """

    tool_name: str
    verb: Verb
    tags: frozenset[str]
    _annotations_kwargs: dict[str, Any] | None = None
    _annotations_explicit: Any = None
    context_param_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    #: Per-parameter descriptions resolved from the tool's Google-style
    #: docstring at decoration time (``Args:`` block). Empty mapping when
    #: the docstring has no ``Args:`` section or no entry for a given
    #: param. Authoritative source for downstream readers (middleware,
    #: introspection tooling); the equivalent ``Annotated[T, Param(...)]``
    #: mutation on ``fn.__annotations__`` continues to feed FastMCP's
    #: schema generator.
    param_descriptions: Mapping[str, str] = field(default_factory=lambda: _EMPTY_PARAM_DESCRIPTIONS)

    @property
    def annotations(self) -> ToolAnnotations:
        """Lazy-construct ``ToolAnnotations`` from stored kwargs.

        First access pays the ``mcp.types`` import cost (~400ms cold-start).
        Callers that only need the JSON-shaped dict (schema dump, wire
        projection) should call :meth:`annotations_as_dict` instead — it
        skips the pydantic object entirely.
        """
        if self._annotations_explicit is not None:
            return self._annotations_explicit
        from mcp.types import ToolAnnotations

        kw = self._annotations_kwargs or {}
        return ToolAnnotations(**kw)

    def annotations_as_dict(self) -> dict[str, Any]:
        """Return the annotation kwargs in ``ToolAnnotations`` wire shape.

        Skips the pydantic object construction (and the ``mcp.types``
        import). For an explicit ``ToolAnnotations`` instance we still
        have to call ``model_dump`` — but that branch is rare (only when
        the consumer passed a full ``ToolAnnotations`` via the
        ``annotations=`` kwarg on a verb decorator).
        """
        if self._annotations_explicit is not None:
            dump = getattr(self._annotations_explicit, "model_dump", None)
            if callable(dump):
                return dump(exclude_none=True)
            return {}
        kw = self._annotations_kwargs or {}
        return {k: v for k, v in kw.items() if v is not None}


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
