from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict

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
    ``type`` object and ``list_view`` carries the frozen
    :class:`ListViewSettings` dataclass. Neither round-trips through
    pydantic's native validation pipeline.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    report_type: type | None = None
    report_schema: dict[str, Any] | None = None  # noqa: A2K-NO-DICT-STR-ANY -- JSON Schema dict shape (free-form by spec)
    router_slug: str | None = None
    visibility: str | None = None
    list_view: ListViewSettings | None = None
    timeout_seconds: float | None = None
    # Multi-surface authoring (ADR 0020). ``expose`` carries the
    # substrates the projection tool registers on; ``authorize``
    # captures the optional per-tool auth gate (enforcement lands in
    # ``add-auth``). Stored on extras (not the top-level frozen
    # dataclass) to avoid breaking the pinned shape of ``A2KitMeta``.
    expose: tuple[str, ...] = ("mcp", "api")
    # Surface projection matrix (ADR 0028 Wave 2). When the author wrote
    # ``surfaces=``, this holds the fully-resolved per-surface state
    # ({mcp,api,cli} → absent|listed|unlisted) and is authoritative.
    # ``None`` means "author used legacy expose=/visibility=" — the matrix
    # is then derived lazily via ``a2kit._surfaces.matrix_for``. ``expose``
    # is kept as the mounted-surfaces compat tuple for membership reads.
    surfaces: dict[str, str] | None = None
    # Verbatim canonical-name pin (ADR 0028 Wave 2). When set, it is the
    # tool's name on every surface with no slug prefix; otherwise the
    # canonical name auto-derives to ``f"{router_slug}_{leaf}"`` (router
    # verbs) or the bare ``leaf`` (app-level). Resolved via
    # ``a2kit._surfaces.resolve_canonical_name``.
    canonical_name_override: str | None = None
    authorize: Any = None


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
    _annotations_kwargs: dict[str, Any] | None = None  # noqa: A2K-NO-DICT-STR-ANY -- kwargs forwarded verbatim to mcp.types.ToolAnnotations
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


def _get_meta(fn: Any) -> A2KitMeta | None:
    return getattr(fn, META_ATTR, None)


def _set_meta(fn: Any, meta: A2KitMeta) -> None:
    object.__setattr__(fn, META_ATTR, meta)


_PRIVATE_HINT = (
    "a2kit.metadata.{name} is private since privatize-tool-metadata. "
    "Read tool data via ToolDescriptor (runtime.descriptor_for(name).metadata_view) "
    "or its projected fields (annotations_view, ctx_param_name, timeout)."
)


def get_meta(*_a: Any, **_kw: Any) -> A2KitMeta | None:
    raise AttributeError(_PRIVATE_HINT.format(name="get_meta"))


def set_meta(*_a: Any, **_kw: Any) -> None:
    raise AttributeError(_PRIVATE_HINT.format(name="set_meta"))
