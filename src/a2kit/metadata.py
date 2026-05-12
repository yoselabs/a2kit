from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict

from a2kit.surface import Surface  # noqa: TC001 — runtime ref for pydantic model field

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


class A2KitMetaExtras(BaseModel):
    """Typed open-extension slot on :class:`A2KitMeta`.

    Verb decorators and routers stamp these fields directly via attribute
    access. The names match what consumers used to read by string-key off
    the legacy ``meta.extra`` dict (with the ``a2kit.`` prefix dropped).

    ``arbitrary_types_allowed`` is required because ``report_type`` carries a
    ``type`` object, ``surfaces`` carries the ``Surface`` flag-enum, and
    ``list_view`` carries the frozen :class:`ListViewSettings` dataclass.
    None of those round-trip through pydantic's native validation pipeline.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    report_type: type | None = None  # noqa: A2K-CORE-CLEAN
    report_schema: dict[str, Any] | None = None  # noqa: A2K-CORE-CLEAN
    router_slug: str | None = None  # noqa: A2K-CORE-CLEAN
    surfaces: Surface | None = None  # noqa: A2K-CORE-CLEAN
    list_view: ListViewSettings | None = None  # noqa: A2K-CORE-CLEAN


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
    extras: A2KitMetaExtras = field(default_factory=A2KitMetaExtras)

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


def get_meta(fn: Any) -> A2KitMeta | None:
    return getattr(fn, META_ATTR, None)


def set_meta(fn: Any, meta: A2KitMeta) -> None:
    object.__setattr__(fn, META_ATTR, meta)
